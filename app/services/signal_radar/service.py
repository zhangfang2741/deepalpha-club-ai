"""信号雷达服务：扫描科技 ETF 成分股跑缠论，按日重建「市场买卖点全景」。

分层：
- 纯聚合函数（signal_strength / build_signal_history / build_days）无 IO，单测覆盖；
- compute_market 负责编排（并发拉行情 + 缠论 + Redis 缓存）。

按日重建口径（核心，别写回「只存最新一条」的旧模型）：
每只股票在缠论分析里可能有一串历史买卖点（result.signals），不是只有一条。
过去的实现只取每只股票的「最新一条」信号按其诞生日期分桶，越往前翻的日子能配
上「诞生日恰好是那天」的股票越少，越翻越稀疏——那根本不是「某天全市场快照」，
只是「各股票最新信号的日期分布尾巴」。
现在改成：先拿到每只股票的完整信号历史，再对每一个要展示的交易日 D，取每只
股票「D 当天或之前最近一条」信号作为它在 D 这天的「在场」信号，直到被更新的
信号覆盖为止。这样任意展示日期都能看到当时全市场有效的买卖点全景。

强度口径：形态技术面强度统一使用信号自带的 strong/medium/weak 标签折算
（signal_strength），不用 recommendation.score——score 是分析当下对整条序列
算出的即时加权净值，对着几周前的历史信号回填没有意义，会导致同一个信号在
被翻看的不同日子里强度/深浅忽深忽浅。方向由买卖点决定（buy=红 / sell=绿）。
"""
from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import logger
from app.schemas.signal_radar import (
    RadarDayOut,
    RadarSignalOut,
    RadarUniverseOut,
    SignalRadarResponse,
)
from app.services.chan.analyzer import ChanAnalysisResult, ChanAnalyzer
from app.services.chan.pivot_phase import PivotPhase
from app.services.chan.replay import pivot_phase_as_of
from app.services.chan.sub_level_service import current_sub_level
from app.services.chan.bias import UNCONFIRMED_DISCOUNT
from app.services.signal_radar.constituents import resolve_constituents
from app.services.signal_radar.universe import get_universe, list_universes
from app.services.skills.kline import fetch_kline

DEFAULT_TOP_N = 10

_analyzer = ChanAnalyzer()

# 缠论窗口锚定所需的 warmup 天数（与 chan.py 的日线口径一致）
_WARMUP_DAYS = 180
# 详情页日线默认预热天数（app/api/v1/chan.py 的 _WARMUP_DAYS['daily']）。雷达取数起点额外前移
# 这么多天，使「从雷达点进详情」时详情页的取数区间与雷达完全一致。
_DETAIL_WARMUP_DAYS = 180
# 并发扫描的信号量：控制对行情源的压力
_SCAN_CONCURRENCY = 8
# 次级别补算（美股每只要分段请求 FMP 30 分钟）并发上限，避免撞限流
_SUB_LEVEL_CONCURRENCY = 4
# 命中限流后单个任务自我冷却的时长：不缩并发槽位数，而是让占着槽位的这个任务
# 多蹲一会儿再放行——变相拉低后续请求打过去的频率，给数据源喘息空间。
_RATE_LIMIT_BACKOFF_SECONDS = 5
# 单次扫描失败率超过这个比例，就认为这次扫描本身出了问题（数据源大面积不可用），
# 不能拿它覆盖已有的好缓存——宁可继续服务旧数据，也不要用残缺结果污染 6 小时。
_MAX_ACCEPTABLE_FAILURE_RATE = 0.5

# 买卖点自身强弱标签 → 形态技术面强度（0~1）。见模块 docstring：不用 score 是
# 因为要跨很多天复用同一把尺子，只有信号自己在诞生时就确定的标签才不会变。
_SIGNAL_STRENGTH = {"strong": 0.8, "medium": 0.55, "weak": 0.35}

# 买卖点级别（一/二/三类）→ 确定性分值（0~1）。一类只是背驰迹象，尚待验证，
# 确定性最低；二类是回踩不破中枢的初步确认；三类是回踩完全不回中枢的最强确认，
# 确定性最高。前端气泡以大小表达类型（ios SignalRadarView.diameter(forLevel:)）。
_LEVEL_CERTAINTY = {1: 0.4, 2: 0.7, 3: 1.0}

# 入榜综合分权重：类型确认程度 + 强弱 + 新鲜度（最新一天再加共振）。
# 新鲜度与类型同权：用户最关心最近几天的新信号，25 天前的旧信号不该与今天的平起平坐。
_SCORE_CERTAINTY_WEIGHT = 0.35
_SCORE_STRENGTH_WEIGHT = 0.30
_SCORE_FRESHNESS_WEIGHT = 0.35
# 共振（日线与 30 分钟同向）加分：只对最新一天、在候选池内补算次级别后重排。
_RESONANCE_BONUS = 0.15
_RESONANCE_POOL = 20
# 多样性弱约束：每类买卖点最多保底这么多名额，其余全部按综合分取。
_MIN_PER_LEVEL = 2

_CACHE_PREFIX = "signal_radar"

# 「自选」股票池：按用户各自的自选股计算（universe=watchlist）；缓存按用户隔离、30 分钟。
# 不列入指数切换菜单（产品决定），接口能力保留。
WATCHLIST_KEY = "watchlist"
WATCHLIST_CACHE_TTL = 1800

# 免费预览快照（未订阅用户在雷达上能点开的唯一一天）：缓存键按目标日期区分，
# 45 天足够跨过一个月 + 缓冲，键随目标日期变化不会无限累积，符合「所有 key
# 必须设置 TTL」的规则；这一天已经过去，end_date=该日算出的结果是确定性的，
# 不需要像滚动窗口那样每天重算。
_DEMO_CACHE_TTL = 3600 * 24 * 45


def watchlist_cache_key(market: str, user_id: int, watchlist: list[tuple[str, str]]) -> str:
    """按用户 + 自选清单摘要隔离：清单增删后键自然变化，旧结果不会被读到。"""
    import hashlib

    digest = hashlib.sha1(",".join(sorted(s.upper() for s, _ in watchlist)).encode()).hexdigest()[:10]
    return f"{_CACHE_PREFIX}:{market}:{WATCHLIST_KEY}:u{user_id}:{digest}"
# 缓存 TTL 的下限：预热已改成按各市场收盘触发（见 scheduler.py），正常间隔是
# ~24h（每个市场一天一次），周末则是 ~72h（周五收盘触发到下周一收盘触发之间跨了
# 周六周日）。下限按周末缺口 + 一天余量给到 4 天，否则周一开盘前缓存就先过期了，
# 第一个访问的用户会被迫触发同步慢扫描——不识别节假日，国庆/春节等连续多日休市
# 期间调度仍会每个工作日空转触发一次（扫不到新数据，无害），不会比周末缺口更长。
_CACHE_TTL_FLOOR = 3600 * 24 * 4  # 4 天


def _cache_ttl() -> int:
    """缓存存活时间（秒）：取预热间隔的 2 倍，并以 4 天兜底（覆盖周末缺口）。

    关键在于 TTL 必须明显长于两次预热之间的最大间隔，这样下一轮预热总能在缓存
    过期之前把它覆盖重写，永远不会出现「缓存刚过期、下一轮预热还没到」的空窗——
    正是那个空窗让第一个撞上的用户被迫触发慢扫描、干等十几秒。
    """
    return max(_CACHE_TTL_FLOOR, settings.SIGNAL_RADAR_PREWARM_INTERVAL_SECONDS * 2)


def _cache_stale_after() -> int:
    """缓存「陈旧」阈值（秒）：写入至今超过此时长即视为陈旧。

    取 SIGNAL_RADAR_PREWARM_INTERVAL_SECONDS（现在只作为这个阈值的换算基数，
    不再是实际预热间隔——预热已改成按各市场收盘触发）的 1.5 倍。正常情况下每个
    市场一天最多一次新日线，缓存年龄够不到这个阈值；只有当收盘触发确实迟到或
    停摆（比如被关掉、异常、容器刚重启还没轮到）时缓存年龄才会涨过阈值——此时
    由用户访问顺带触发一次后台刷新，既不与正常预热重复抢扫，又能在预热失灵时自愈。
    """
    return int(settings.SIGNAL_RADAR_PREWARM_INTERVAL_SECONDS * 1.5)

# 在场信号的过期上限（交易日，见 trading_age）：一条买卖点即使一直没被新信号覆盖，
# 亮起超过这个交易日数后也不再显示。信号雷达的定位是「看当前市场的买卖点」，不是
# 「翻出几个月前仍未失效的老信号」。5 个交易日 = 一周，与前端最外「一周内」环对齐；
# 按交易日而不是自然日数，周末和休市不会让信号平白变老。新鲜度评分也按这个窗口衰减。
_MAX_SIGNAL_AGE_DAYS = 5


@dataclass
class RawSignal:
    """单只股票的一条买卖点（聚合前的中间结构）。"""

    symbol: str
    name: str
    side: str            # buy / sell
    label: str
    signal_type: str
    date: str
    price: float
    strength: float      # 形态技术面强度 0~1（决定气泡淘汰排序；气泡深浅按 signal_strength）
    bias: str
    signal_strength: str
    confirmed: bool
    pivot_stage_depth: float  # 该信号发生当天的中枢阶段深浅 0~1（旧版 App 的气泡深浅）
    # 价格失效日：亮起后首个收盘价跌破买点价位（卖点：涨破）的交易日；从这天起不再在场
    invalidated_on: str | None = None


def signal_strength(label: str) -> float:
    """买卖点自身强弱标签（strong/medium/weak）→ 形态技术面强度（0~1）。"""
    return _SIGNAL_STRENGTH.get(label, 0.5)


# 中枢生命周期阶段（见 app/services/chan/pivot_phase.py）→ 气泡深浅 0~1。
# 形成/震荡两档区分"还没离开中枢"的程度；一旦离开中枢（leaving/回抽确认/
# 背驰转折），不管具体哪个子阶段，都算"已突破"给最深档——三档对应用户要的
# "中枢形成=浅、中枢震荡=中、中枢突破=深"。取不到阶段（比如结构还没成形）
# 时退回中间档，不假装知道处于哪个阶段。
_PIVOT_STAGE_DEPTH = {
    "pivot_forming": 0.3,
    "pivot_oscillating": 0.55,
    "leaving": 0.85,
    "retrace_confirmed": 0.85,
    "divergence_turn": 0.85,
}
_DEFAULT_STAGE_DEPTH = 0.55


def pivot_stage_depth(phase: PivotPhase | None) -> float:
    """把 pivot_phase 的 5 个阶段折成气泡深浅三档，取不到阶段时退回中间档。"""
    if phase is None:
        return _DEFAULT_STAGE_DEPTH
    return _PIVOT_STAGE_DEPTH.get(phase.phase, _DEFAULT_STAGE_DEPTH)


def _signal_level(signal_type: str) -> int:
    """从 signal_type（buy1/sell2…）末位取买卖点级别 1/2/3，与前端 RadarSignal.level 一致。"""
    tail = signal_type[-1:]
    return int(tail) if tail.isdigit() else 1


def trading_age(sig_date: str, day: str, calendar: list[str]) -> int:
    """sig_date 之后、day 当天及之前隔了几个交易日（同一天为 0）。

    calendar 为已知交易日（扫描时从成分股K线得到，含节假日休市的真实缺口）；日历覆盖
    不到的更早区间按工作日近似（跳过周六日）。
    """
    if sig_date >= day:
        return 0
    cal = sorted({d for d in calendar if d <= day})
    first = cal[0] if cal else None
    exact = sum(1 for d in cal if d > sig_date)
    approx_end = date.fromisoformat(first) if first else date.fromisoformat(day) + timedelta(days=1)
    approx = 0
    d = date.fromisoformat(sig_date) + timedelta(days=1)
    while d < approx_end:
        if d.weekday() < 5:
            approx += 1
        d += timedelta(days=1)
    return exact + approx


def radar_score(level: int, strength: float, age_days: int, resonance: bool = False,
                *, confirmed: bool = True, max_age_days: int = _MAX_SIGNAL_AGE_DAYS) -> float:
    """入榜综合分：类型确认程度 + 强弱 + 新鲜度（当天 1 → max_age_days 天 0），共振另加分。

    未确认信号（落在最后一笔上的左侧预判）的质量部分（类型确认程度 + 强弱）按
    UNCONFIRMED_DISCOUNT 打折，与多空倾向同一口径；新鲜度不打折。
    """
    certainty = _LEVEL_CERTAINTY.get(level, _LEVEL_CERTAINTY[1])
    freshness = 1.0 - min(max(age_days, 0), max_age_days) / max(max_age_days, 1)
    quality = _SCORE_CERTAINTY_WEIGHT * certainty + _SCORE_STRENGTH_WEIGHT * strength
    if not confirmed:
        quality *= UNCONFIRMED_DISCOUNT
    score = quality + _SCORE_FRESHNESS_WEIGHT * freshness
    return score + (_RESONANCE_BONUS if resonance else 0.0)


def display_rank(signal: RawSignal, age_days: int = 0) -> float:
    """信号在看板上的综合分（见 radar_score）；age_days 为相对展示日的天数。"""
    return radar_score(_signal_level(signal.signal_type), signal.strength, age_days,
                       confirmed=signal.confirmed)


def _select_top_n(items: list, top_n: int, *, level_of, score_of) -> list:
    """先给每类买卖点保底（最多 _MIN_PER_LEVEL 个，按类轮流、类内按分数），其余按综合分取。

    以前是三类严格轮流各取一个，结果弱一类也能挤掉强三类；现在多样性只做弱约束。
    结果按综合分从高到低返回。
    """
    buckets: dict[int, list] = {}
    for it in items:
        buckets.setdefault(level_of(it), []).append(it)
    for b in buckets.values():
        b.sort(key=score_of, reverse=True)
    picked: list = []
    for rank in range(_MIN_PER_LEVEL):
        for lv in sorted(buckets):
            if len(picked) >= top_n:
                break
            if len(buckets[lv]) > rank:
                picked.append(buckets[lv][rank])
    chosen = {id(x) for x in picked}
    rest = sorted((x for x in items if id(x) not in chosen), key=score_of, reverse=True)
    picked.extend(rest[: max(0, top_n - len(picked))])
    return sorted(picked, key=score_of, reverse=True)[:top_n]


def is_aligned_resonance(side: str, verdict: str | None) -> bool:
    """气泡方向与次级别共振方向一致才算共振：买点配共振买、卖点配共振卖。

    一买常出现在下跌末端（日线形态偏弱），会碰上「共振卖点」——那不是对这个买点的确认，
    反而是相反信号，不能给它挂共振、也不能加分。
    """
    return (side == "buy" and verdict == "resonance_buy") or (side == "sell" and verdict == "resonance_sell")


def rerank_with_resonance(day: RadarDayOut, top_n: int) -> RadarDayOut:
    """最新一天：候选池（已补算次级别）按综合分 + 共振加分重排，取前 top_n。"""
    day_date = date.fromisoformat(day.date)

    def score_of(s: RadarSignalOut) -> float:
        # 优先用构建时算好的交易日龄；旧缓存没有该字段时退回自然日
        age = s.age_days if s.age_days is not None else (day_date - date.fromisoformat(s.date)).days
        resonance = is_aligned_resonance(s.side, s.sub_level_verdict)
        return radar_score(_signal_level(s.signal_type), s.strength, age, resonance,
                           confirmed=s.confirmed)

    items = _select_top_n(list(day.signals), top_n, level_of=lambda s: _signal_level(s.signal_type),
                          score_of=score_of)
    return RadarDayOut(date=day.date, buy_count=sum(s.side == "buy" for s in items),
                       sell_count=sum(s.side == "sell" for s in items), signals=items)

def _invalidated_on(is_buy: bool, price: float, detected: str, bars: list[dict] | None) -> str | None:
    """亮起之后首个收盘价跌破买点价位（卖点：涨破）的日期；没有则 None。

    价位是信号所属那一笔的端点（买点=低点、卖点=高点）。一二三类统一按它判：一买/二买
    跌破即新低、结构被否定；三买的回踩低点本就在中枢上沿之上，跌回中枢之前必先跌破它。
    亮起之前（笔终点到亮起之间）的走势不算。
    """
    for b in bars or []:
        t = str(b.get("time", ""))[:10]
        close = b.get("close")
        if t <= detected or close is None:
            continue
        if (is_buy and close < price) or (not is_buy and close > price):
            return t
    return None


def build_signal_history(
    symbol: str, name: str, result: ChanAnalysisResult, bars: list[dict] | None = None,
) -> list[RawSignal]:
    """从一只股票的缠论结果里取出全部买卖点历史。

    不只是最新一条，按日期升序返回，供按日重建市场快照时找「某天为止最近一条」用。
    没有买卖点返回空列表。

    每条信号的中枢阶段深浅按它自己发生那天回溯（`pivot_phase_as_of`），不是
    统一套用"今天"的阶段——同一只股票在看板上可能同时展示好几天前的历史
    信号，深浅要反映那条信号发生当天中枢真实处于哪个阶段，不然同一只股票
    不同日期的气泡会被错误地画成同一个深浅。
    """
    history = [
        RawSignal(
            symbol=symbol,
            name=name,
            side="buy" if sig.is_buy else "sell",
            label=sig.label,
            signal_type=sig.type,
            # 按亮起日期算「几天前」：笔终点要等后续K线确认才出信号，按笔终点算会把今天
            # 刚出现的信号当成几天前的旧信号；翻看历史某天时也不会提前看到之后才亮起的信号。
            date=(sig.detected_time or sig.time)[:10],
            price=round(sig.price, 2),
            strength=signal_strength(sig.strength),
            bias="bullish" if sig.is_buy else "bearish",
            signal_strength=sig.strength,
            confirmed=sig.confirmed,
            pivot_stage_depth=pivot_stage_depth(pivot_phase_as_of(result, sig.time)),
            invalidated_on=_invalidated_on(
                sig.is_buy, sig.price, (sig.detected_time or sig.time)[:10], bars),
        )
        for sig in result.signals
    ]
    history.sort(key=lambda r: r.date)
    return history


def build_days(
    histories: list[list[RawSignal]], trading_days: list[str], *, top_n: int,
    max_age_days: int = _MAX_SIGNAL_AGE_DAYS, calendar: list[str] | None = None,
) -> list[RadarDayOut]:
    """按 trading_days（最新在前）逐日重建市场快照。

    histories 是「每只股票的信号历史」的列表（每条已按日期升序）。对每个展示日
    D，每只股票取它历史里日期 <= D 的最后一条作为「D 当天在场」的信号；股票数量
    很小（几十到上百），这里用线性扫描换清晰，不做二分。

    过期上限（max_age_days）：某只股票在 D 当天的在场信号，若其诞生日距离 D 已超过
    max_age_days 个自然日，则视为过期、当天不再展示（相对每个展示日各自判断，翻看
    历史某天时看到的仍是「截至那天 max_age_days 内有效」的信号）。见模块内
    _MAX_SIGNAL_AGE_DAYS 说明。
    """
    # 数交易日龄用的日历：调用方给了更长的日历就用它（覆盖到最老展示日之前），否则用展示日本身
    cal = calendar if calendar is not None else trading_days
    out: list[RadarDayOut] = []
    for day in trading_days:
        active: list[RawSignal] = []
        ages: dict[int, int] = {}
        for history in histories:
            candidate: RawSignal | None = None
            for r in history:
                if r.date > day:
                    break
                candidate = r
            if candidate is not None:
                if candidate.invalidated_on is not None and candidate.invalidated_on <= day:
                    continue  # 价格已走坏（跌破买点 / 涨破卖点），当天起退场
                age = trading_age(candidate.date, day, cal)
                if age > max_age_days:
                    continue
                active.append(candidate)
                ages[id(candidate)] = age

        items = _select_top_n(
            active, top_n, level_of=lambda r: _signal_level(r.signal_type),
            score_of=lambda r, ages=ages: display_rank(r, ages[id(r)]),
        )
        out.append(RadarDayOut(
            date=day,
            buy_count=sum(1 for r in items if r.side == "buy"),
            sell_count=sum(1 for r in items if r.side == "sell"),
            signals=[
                RadarSignalOut(
                    symbol=r.symbol, name=r.name, side=r.side, label=r.label,
                    signal_type=r.signal_type, date=r.date, price=r.price,
                    strength=r.strength, bias=r.bias,
                    signal_strength=r.signal_strength, confirmed=r.confirmed,
                    pivot_stage_depth=r.pivot_stage_depth,
                    age_days=ages[id(r)],
                )
                for r in items
            ],
        ))
    return out


async def attach_sub_levels(
    day: RadarDayOut, *, end_date: str, user_id: int | None, redis: Redis | None,
) -> None:
    """给某一天的入榜气泡补算次级别结论（原地写入 sub_level_verdict/label）。

    走与详情页相同的唯一入口 current_sub_level（固定口径 + 结论缓存），refresh=True
    重算并覆盖缓存——点进详情读到的就是这一次的结论，气泡与详情不会各算各的。
    中英文各算一份写缓存（详情页按界面语言读取）。补算失败的候选留空，不影响榜单。
    """
    sem = asyncio.Semaphore(_SUB_LEVEL_CONCURRENCY)

    async def _one(sig: RadarSignalOut) -> None:
        async with sem:
            try:
                sub = await current_sub_level(sig.symbol, "daily", end_date=end_date, user_id=user_id,
                                              redis=redis, lang="zh", refresh=True)
                await current_sub_level(sig.symbol, "daily", end_date=end_date, user_id=user_id,
                                        redis=redis, lang="en", refresh=True)
            except Exception as e:  # noqa: BLE001 单只补算失败不影响榜单
                logger.warning("signal_radar_sub_level_failed", symbol=sig.symbol, error=str(e))
                return
        sig.sub_level_verdict = sub.verdict
        sig.sub_level_label = sub.verdict_label

    await asyncio.gather(*[_one(sig) for sig in day.signals])


# 各市场开盘时段（UTC，工作日），末端多留半小时拿到收盘那根 30 分钟K线。
# 美股按夏令时/冬令时取并集（13:30–21:00 UTC）；不识别节假日——休市日刷新只是空转。
_SESSIONS_UTC: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    "us": ((13, 30), (21, 30)),
    "cn": ((1, 30), (7, 30)),
    "hk": ((1, 30), (8, 30)),
}


def market_session_active(market: str, now: datetime) -> bool:
    """该市场此刻是否处于开盘时段（含收盘后半小时）。"""
    window = _SESSIONS_UTC.get(market)
    now = now.astimezone(UTC)
    if window is None or now.weekday() >= 5:
        return False
    (h1, m1), (h2, m2) = window
    minutes = now.hour * 60 + now.minute
    return h1 * 60 + m1 <= minutes <= h2 * 60 + m2


async def refresh_sub_levels(
    market: str, universe_key: str, *, redis: Redis, user_id: int | None = None,
    now: datetime | None = None, window: int = 45,
) -> bool:
    """只重算缓存快照里最新一天入榜气泡的次级别（共振）结论，写回并保留原 TTL。

    全量扫描 6 小时一轮，而 30 分钟级别盘中每半小时就可能变化，共振标记不能跟着
    快照一起放 6 小时——这里单独刷新，请求量只有入榜的十几只。
    写回前重新读取快照：若期间全量预热已写入新一天的快照，放弃本次写入，不用旧气泡
    覆盖新数据。返回是否写回。
    """
    snapshot = await _read_cache(redis, market, universe_key)
    if snapshot is None or not snapshot.days:
        return False
    day = snapshot.days[0]
    await attach_sub_levels(day, end_date=date.today().isoformat(), user_id=user_id, redis=redis)

    latest = await _read_cache(redis, market, universe_key)
    if latest is None or not latest.days or latest.days[0].date != day.date:
        logger.info("signal_radar_sub_level_refresh_skipped", market=market, universe=universe_key)
        return False
    fresh = {s.symbol: s for s in day.signals}
    for sig in latest.days[0].signals:
        if sig.symbol in fresh:
            sig.sub_level_verdict = fresh[sig.symbol].sub_level_verdict
            sig.sub_level_label = fresh[sig.symbol].sub_level_label
    latest.sub_level_as_of = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0).isoformat()
    try:
        await redis.set(_cache_key(market, universe_key), latest.model_dump_json(), keepttl=True)
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_sub_level_write_error", market=market, error=str(e))
        return False
    logger.info("signal_radar_sub_levels_refreshed", market=market, universe=universe_key,
                symbols=len(day.signals))
    return True


# 一个日期至少有这么多比例的成分股有K线，才算交易日（排除个别标的串日/错位）
_CALENDAR_MIN_SHARE = 0.3


def trading_days_from_constituents(
    per_symbol_dates: list[list[str]], *, etf_dates: list[str], cutoff: str, end_date: str, limit: int,
) -> list[str]:
    """交易日历：按扫描到的成分股日线确定（>=30% 成分股有K线的日期），并入参考 ETF 的日期。

    不再只看参考 ETF：ETF 的数据源可能比成分股慢一天（科创50 588000 在 Yahoo 只到前一日），
    指数代码（沪深300 000300）还可能取不到——时间轴会缺最近交易日。最新在前，最多 limit 个。
    """
    from collections import Counter

    counts: Counter[str] = Counter()
    for dates in per_symbol_dates:
        counts.update({d[:10] for d in dates if cutoff <= d[:10] <= end_date})
    need = max(1, int(len(per_symbol_dates) * _CALENDAR_MIN_SHARE + 0.9999)) if per_symbol_dates else 1
    days = {d for d, n in counts.items() if n >= need}
    days |= {d[:10] for d in etf_dates if cutoff <= d[:10] <= end_date}
    return sorted(days, reverse=True)[:limit]


def _trading_days_from_bars(bars: list[dict], *, cutoff: str, end_date: str, limit: int) -> list[str]:
    """从一串日线 bar 里提取 [cutoff, end_date] 内的交易日期，最新在前，最多取 limit 个。"""
    dates = sorted({b["time"][:10] for b in bars if cutoff <= b["time"][:10] <= end_date}, reverse=True)
    return dates[:limit]


def _fallback_trading_days(*, end_date: str, limit: int) -> list[str]:
    """拿不到任何 K 线时的兜底。

    按自然日往前数、跳过周六周日（不识别节假日，只在行情源整体不可用时才会
    走到这里，凑合出个大致的交易日序列）。
    """
    out: list[str] = []
    d = date.fromisoformat(end_date)
    while len(out) < limit:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return out


async def _scan_symbol(
    symbol: str, name: str, *, user_id: int | None, start_date: str, end_date: str,
    redis: Redis,
) -> tuple[list[RawSignal], str | None, ChanAnalysisResult | None, list[str]]:
    """扫描单只股票：拉日线 → 缠论 → 取全部买卖点历史。

    返回 (信号历史, 失败分类, 日线分析结果, 最近的K线日期)。K线日期用来确定交易日历。失败分类为 None 表示这只股票本身就没有可用信号
    ——正常情况，不是故障；非 None 时 compute_market 据此汇总统计，别再让故障
    悄悄混进"这个市场最近确实没什么信号"里看不出来。
    """
    try:
        bars = await fetch_kline(
            user_id=user_id, symbol=symbol, start_date=start_date,
            end_date=end_date, freq="daily", redis=redis,
        )
    except Exception as e:  # noqa: BLE001 单只失败不影响整体扫描
        logger.warning("signal_radar_kline_failed", symbol=symbol, error=str(e))
        return [], _classify_failure(e), None, []

    if not bars:
        return [], None, None, []

    try:
        result = _analyzer.analyze(symbol, bars, lang="zh")
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_analyze_failed", symbol=symbol, error=str(e))
        return [], "analyze_failed", None, []

    return (build_signal_history(symbol, name, result, bars=bars), None, result,
            [b["time"][:10] for b in bars[-60:]])


def _classify_failure(exc: Exception) -> str:
    """按异常文案粗分类，供 compute_market 汇总「这次扫描到底卡在哪」。"""
    msg = str(exc)
    if "限流" in msg or "冷却" in msg or "429" in msg:
        return "rate_limited"
    if "不可用" in msg or "断连" in msg:
        return "unreachable"
    if "API_KEY" in msg or "未配置" in msg:
        return "config_missing"
    if "未获取到" in msg or "查无" in msg:
        return "no_data"
    return "other"


def _cache_key(market: str, universe_key: str) -> str:
    return f"{_CACHE_PREFIX}:{market}:{universe_key}"


def _universes_out(market: str) -> list[RadarUniverseOut]:
    """该市场可选 universe 列表（默认在前），用于响应里的切换器选项。"""
    return [
        RadarUniverseOut(key=u.key, name=u.etf_name, is_default=u.is_default)
        for u in list_universes(market)
    ]


async def read_watchlist_cache(
    redis: Redis, market: str, user_id: int, watchlist: list[tuple[str, str]],
) -> SignalRadarResponse | None:
    """读某用户某市场（当前自选清单）的自选雷达缓存。"""
    try:
        raw = await redis.get(watchlist_cache_key(market, user_id, watchlist))
        return SignalRadarResponse.model_validate_json(raw) if raw else None
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_watchlist_cache_read_error", market=market, error=str(e))
        return None


async def _read_cache(redis: Redis, market: str, universe_key: str) -> SignalRadarResponse | None:
    try:
        rawval = await redis.get(_cache_key(market, universe_key))
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_cache_read_error", market=market, error=str(e))
        return None
    if rawval is None:
        return None
    try:
        return SignalRadarResponse.model_validate_json(rawval)
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_cache_deserialize_error", market=market, error=str(e))
        return None


async def _write_cache(redis: Redis, data: SignalRadarResponse) -> None:
    try:
        await redis.set(
            _cache_key(data.market, data.universe), data.model_dump_json(), ex=_cache_ttl()
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_cache_write_error", market=data.market, error=str(e))


def _fetch_start(today: date, window: int) -> str:
    """雷达日线取数起点。

    在可见区间起点（today - warmup - window*2，即 iOS 点进详情用的 start）之前，再前移
    详情页的默认预热天数，保证与详情页取数区间一致，结构与买卖点一致。
    """
    return (today - timedelta(days=_WARMUP_DAYS + window * 2 + _DETAIL_WARMUP_DAYS)).isoformat()


async def compute_market(
    market: str, *, redis: Redis, user_id: int | None = None,
    universe_key: str | None = None,
    days: int = 30, window: int = 45, top_n: int = DEFAULT_TOP_N,
    max_age_days: int = _MAX_SIGNAL_AGE_DAYS,
    watchlist: list[tuple[str, str]] | None = None,
    refresh_constituents: bool = False,
) -> SignalRadarResponse:
    """全量扫描一个 (市场, universe) 并按日重建快照（不读缓存，计算完写入缓存）。

    watchlist 非 None 时扫用户自选股（「自选」股票池）：结果写入按用户隔离的缓存键，
    交易日历仍参考该市场默认 universe 的 ETF。
    """
    is_watchlist = watchlist is not None
    universe = get_universe(market, None if is_watchlist else universe_key)
    if universe is None:
        raise ValueError(f"unsupported market/universe: {market}/{universe_key}")

    # 成分股：自选用用户清单；否则按 universe 来源策略动态刷新，取不到回退 curated 静态清单。
    constituents = list(watchlist) if watchlist is not None else \
        await resolve_constituents(market, redis=redis, universe_key=universe.key,
                                   refresh=refresh_constituents)

    today = date.today()
    end_date = today.isoformat()
    # 取足够 warmup + 候选窗口的历史；缠论在完整序列上算以消除左边界漂移。
    start_date = _fetch_start(today, window)
    cutoff = (today - timedelta(days=window)).isoformat()

    sem = asyncio.Semaphore(_SCAN_CONCURRENCY)

    async def _one(symbol: str, name: str) -> tuple[list[RawSignal], str | None, list[str]]:
        async with sem:
            history, failure, _, dates = await _scan_symbol(
                symbol, name, user_id=user_id, start_date=start_date,
                end_date=end_date, redis=redis,
            )
            if failure == "rate_limited":
                # 命中限流别立刻放行下一个排队的任务抢同一个名额，攒着火上浇油——
                # 让这个名额歇一会儿，给数据源一点喘息时间再继续消费队列。
                await asyncio.sleep(_RATE_LIMIT_BACKOFF_SECONDS)
            return history, failure, dates

    scanned = await asyncio.gather(*[_one(sym, name) for sym, name in constituents])
    histories = [h for h, _, _ in scanned if h]
    failure_counts = Counter(f for _, f, _ in scanned if f)

    # 展示的交易日历：以成分股日线为准（>=30% 成分股有K线的日期），并入参考 ETF 的日期；
    # 都拿不到才退化成「跳过周末」的近似日历。
    try:
        etf_bars = await fetch_kline(
            user_id=user_id, symbol=universe.etf_symbol, start_date=cutoff,
            end_date=end_date, freq="daily", redis=redis,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_etf_kline_failed", market=market, error=str(e))
        etf_bars = []
    # 日历多取一段（最老展示日之前再往前 max_age_days 天），用来按交易日数信号年龄
    calendar = trading_days_from_constituents(
        [dates for _, _, dates in scanned if dates],
        etf_dates=[b["time"] for b in etf_bars], cutoff=cutoff, end_date=end_date,
        limit=days + max_age_days + 1,
    ) or _fallback_trading_days(end_date=end_date, limit=days + max_age_days + 1)
    trading_days = calendar[:days]

    resp = SignalRadarResponse(
        market=market,
        universe=WATCHLIST_KEY if is_watchlist else universe.key,
        universes=_universes_out(market),
        etf_name="自选" if is_watchlist else universe.etf_name,
        universe_size=len(constituents),
        as_of=end_date,
        top_n=top_n,
        days=build_days(histories, trading_days, top_n=top_n, max_age_days=max_age_days,
                        calendar=calendar),
        status="ready",
        computed_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
    )
    if resp.days:
        # 次级别结论描述的是「现在」，只对最新交易日：先取更大的候选池补算次级别，
        # 再按综合分 + 共振加分重排取前 top_n（共振参与排名）
        pool = build_days(histories, trading_days[:1], top_n=max(top_n, _RESONANCE_POOL),
                          max_age_days=max_age_days, calendar=calendar)[0]
        await attach_sub_levels(pool, end_date=end_date, user_id=user_id, redis=redis)
        resp.days[0] = rerank_with_resonance(pool, top_n)
        resp.sub_level_as_of = datetime.now(UTC).replace(microsecond=0).isoformat()
    failed_symbols = sum(failure_counts.values())
    failure_rate = failed_symbols / len(constituents) if constituents else 0.0
    logger.info(
        "signal_radar_computed", market=market,
        universe=len(universe.constituents), symbols_with_signals=len(histories),
        symbols_failed=failed_symbols, failure_rate=round(failure_rate, 2),
        failure_breakdown=dict(failure_counts), days=len(resp.days),
    )

    # 这次扫描大半个市场都请求不到（比如限流/熔断赶一起了），别让这坨残缺结果
    # 覆盖掉几分钟前还好好的缓存——那样用户接下来 6 小时看到的就是这次的烂摊子。
    # 只有「已经有一份旧缓存能保底」时才这么做；首次扫描没有旧缓存可保，再差也
    # 得写进去，不然用户永远看不到任何数据。
    if is_watchlist:
        # 自选结果按用户隔离缓存，不进共用键；也不做「保留旧缓存」保护（清单随时会变）
        if user_id is not None:
            try:
                await redis.set(watchlist_cache_key(market, user_id, constituents), resp.model_dump_json(),
                                ex=WATCHLIST_CACHE_TTL)
            except Exception as e:  # noqa: BLE001
                logger.warning("signal_radar_watchlist_cache_write_error", market=market, error=str(e))
        return resp

    if failure_rate > _MAX_ACCEPTABLE_FAILURE_RATE:
        stale = await _read_cache(redis, market, universe.key)
        if stale is not None:
            logger.warning(
                "signal_radar_scan_degraded_keep_stale_cache",
                market=market, failure_rate=round(failure_rate, 2),
                failure_breakdown=dict(failure_counts),
            )
            return stale

    await _write_cache(redis, resp)
    return resp


async def _cache_is_stale(redis: Redis, market: str, universe_key: str) -> bool:
    """按剩余 TTL 反推缓存年龄，判断是否已陈旧（超过 _cache_stale_after）。

    年龄 = 完整 TTL - 剩余 TTL。拿不到剩余 TTL（异常）时保守地当作「不陈旧」，
    避免因读 TTL 失败而无谓地反复触发后台刷新；剩余 TTL < 0（无过期时间/刚好过期）
    则当作陈旧，好让下一次刷新把带正常 TTL 的缓存重新建起来。
    """
    try:
        remaining = await redis.ttl(_cache_key(market, universe_key))
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_cache_ttl_error", market=market, error=str(e))
        return False
    if remaining < 0:
        return True
    age = _cache_ttl() - remaining
    return age >= _cache_stale_after()


async def peek_cache_entry(
    redis: Redis, market: str, universe_key: str | None = None
) -> tuple[SignalRadarResponse | None, bool]:
    """只读缓存并判断是否陈旧（不触发扫描），供 API 的 stale-while-revalidate 使用。

    返回 (响应, 是否陈旧)：命中且陈旧时 API 会先把旧数据返给用户、再在后台悄悄刷新，
    避免让用户看到 generating 空屏。无缓存返回 (None, False)。
    """
    universe = get_universe(market, universe_key)
    if universe is None:
        return None, False
    cached = await _read_cache(redis, market, universe.key)
    if cached is None:
        return None, False
    return cached, await _cache_is_stale(redis, market, universe.key)


async def get_market(
    market: str, *, redis: Redis, user_id: int | None = None,
    universe_key: str | None = None,
    days: int = 30, window: int = 45, top_n: int = DEFAULT_TOP_N, force: bool = False,
    max_age_days: int = _MAX_SIGNAL_AGE_DAYS,
) -> SignalRadarResponse:
    """读缓存优先；未命中则同步扫描（首访较慢，命中后走缓存）。"""
    universe = get_universe(market, universe_key)
    if universe is None:
        raise ValueError(f"unsupported market/universe: {market}/{universe_key}")
    if not force:
        cached = await _read_cache(redis, market, universe.key)
        if cached is not None:
            return cached
    return await compute_market(
        market, redis=redis, user_id=user_id, universe_key=universe.key,
        days=days, window=window, top_n=top_n, max_age_days=max_age_days,
    )


# ---------------------------------------------------------------------------
# 免费预览：未订阅用户在雷达上唯一能点开的一天——「上个月 1 号」的真实快照
# ---------------------------------------------------------------------------


def demo_snapshot_date() -> str:
    """免费预览锚定的日期：上个月 1 号，随当前月份自动往后走，不是钉死的某天。"""
    first_of_this_month = date.today().replace(day=1)
    last_month_end = first_of_this_month - timedelta(days=1)
    return last_month_end.replace(day=1).isoformat()


def _demo_cache_key(market: str, target: str) -> str:
    return f"{_CACHE_PREFIX}:demo:{market}:{target}"


async def read_demo_cache(redis: Redis, market: str) -> SignalRadarResponse | None:
    """读免费预览快照缓存（不触发计算），键按当前 demo_snapshot_date() 取。"""
    try:
        raw = await redis.get(_demo_cache_key(market, demo_snapshot_date()))
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_demo_cache_read_error", market=market, error=str(e))
        return None
    if raw is None:
        return None
    try:
        return SignalRadarResponse.model_validate_json(raw)
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_demo_cache_deserialize_error", market=market, error=str(e))
        return None


async def compute_demo_day(market: str, *, redis: Redis) -> SignalRadarResponse:
    """免费预览：只算「上个月 1 号」这一天的真实快照，用该市场默认 universe。

    不走标准滚动窗口（compute_market 默认只保留最近 30 个交易日），因为这个
    目标日期离「今天」通常已经超出那个窗口；也不需要像标准快照那样每天重算——
    这一天已经过去，用它做 end_date 算出的结果不会再随后续行情变化。
    """
    target = demo_snapshot_date()
    universe = get_universe(market, None)
    if universe is None:
        raise ValueError(f"unsupported market: {market}")
    constituents = await resolve_constituents(market, redis=redis, universe_key=universe.key)

    end_date = target
    start_date = _fetch_start(date.fromisoformat(target), window=45)
    sem = asyncio.Semaphore(_SCAN_CONCURRENCY)

    async def _one(symbol: str, name: str) -> tuple[list[RawSignal], list[str]]:
        async with sem:
            history, _, _, dates = await _scan_symbol(
                symbol, name, user_id=None, start_date=start_date, end_date=end_date, redis=redis,
            )
            return history, dates

    scanned = await asyncio.gather(*[_one(sym, name) for sym, name in constituents])
    histories = [h for h, _ in scanned if h]
    calendar = trading_days_from_constituents(
        [dates for _, dates in scanned if dates], etf_dates=[], cutoff=target, end_date=target,
        limit=_MAX_SIGNAL_AGE_DAYS + 1,
    ) or [target]
    if target not in calendar:
        calendar = sorted({*calendar, target}, reverse=True)

    resp = SignalRadarResponse(
        market=market,
        universe=universe.key,
        universes=_universes_out(market),
        etf_name=universe.etf_name,
        universe_size=len(constituents),
        as_of=target,
        top_n=DEFAULT_TOP_N,
        days=build_days(histories, [target], top_n=DEFAULT_TOP_N, calendar=calendar),
        status="ready",
        computed_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
    )
    try:
        await redis.set(_demo_cache_key(market, target), resp.model_dump_json(), ex=_DEMO_CACHE_TTL)
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_demo_cache_write_error", market=market, error=str(e))
    return resp
