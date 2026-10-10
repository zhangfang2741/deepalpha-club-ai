"""SMC（Smart Money Concepts）结构识别：纯函数，输入原始 K 线，输出图上要画的结构事实。

口径参照最常用的两份开源实现（LuxAlgo「Smart Money Concepts」与 joshyattridge/smart-money-concepts），
只保留其中有明确规则、能由 K 线直接算出的部分：

1. 摆动高 / 低点：左右各 `length` 根内的极值，**右侧确认后才生效**（`idx + length`），不看未来；
2. 结构突破 BOS / 结构转变 CHoCH：收盘越过最近一个**已确认**的摆动高 / 低点；顺着当前结构方向是 BOS，
   逆着是 CHoCH，每个摆动点只被突破一次；
3. 订单块：突破发生时，从被突破的摆动点到突破前，取反向极值那一根 K 线（向上突破取最低一根，向下取最高一根）
   的整根 K 线区间；收盘反向穿过它即失效（mitigated）；
4. 公允价值缺口 FVG：三根 K 线里第一根与第三根之间没被覆盖的缺口，中间那根实体须明显大于此前平均实体；
   价格回到缺口远端即被填补；
5. 等高点 / 等低点：相邻两个小级别摆动点之差小于 0.1 × ATR；
6. 流动性扫荡：影线越过一个还没被收盘突破的摆动点，但收盘回到它的这一侧；
7. 溢价 / 折价区：最近摆动高、低点（随新高新低延伸）之间的 50% 位置以上 / 以下；
8. 强 / 弱高低点：同一组极值，结构向下时高点为强、低点为弱，结构向上时相反（LuxAlgo 口径）；
9. 前日 / 周 / 月高低点：上一个已走完的周期的最高 / 最低。

只陈列位置与事实：不打分、不给方向建议；文案由 overlay / App 负责且不含买卖导向措辞。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# 摆动点长度（左右各 N 根），按周期取。2026-10 在 8 只美股 / 港股 / A 股的近三年日线上校准：
# 长度 3~5 时两年里有 25~40 次突破（一屏全是线），10 时每只约 9~15 次，手机上读得过来；
# LuxAlgo 默认的「主结构 50 / 内部结构 5」在两年日线上要么太稀要么太密，这里只取一级。
SWING_LEN_BY_FREQ = {"daily": 10, "weekly": 5, "30min": 10}
SWING_LEN = SWING_LEN_BY_FREQ["daily"]
# 等高 / 等低点用的小级别摆动长度与容差（× ATR）。
EQ_SWING_LEN = 3
EQ_ATR_MULT = 0.1
EQ_ATR_PERIOD = 200
# FVG：中间那根的实体须大于此前平均实体的这个倍数（LuxAlgo 自动阈值）。
FVG_BODY_MULT = 2.0


@dataclass
class Swing:
    """摆动高 / 低点。"""

    kind: str          # "high" | "low"
    idx: int
    price: float


@dataclass
class Break:
    """一次结构突破（BOS）或结构转变（CHoCH）。"""

    kind: str          # "bos" | "choch"
    direction: str     # "bull"（向上突破）| "bear"（向下突破）
    level: float       # 被突破的摆动点价位
    level_idx: int     # 摆动点所在 K 线
    break_idx: int     # 第一根收盘越过它的 K 线


@dataclass
class OrderBlock:
    """订单块：突破前的反向极值那一根 K 线的区间。"""

    direction: str     # "bull"（向上突破前的最后下探那根）| "bear"
    idx: int
    top: float
    bottom: float
    break_idx: int     # 产生它的那次突破
    mitigated_idx: int | None
    volume_ratio: float  # 这根 K 线成交量 ÷ 平均成交量


@dataclass
class Fvg:
    """公允价值缺口：三根 K 线里没被覆盖的价格空档。"""

    direction: str     # "bull" | "bear"
    idx: int           # 中间那根（缺口的起点）
    top: float
    bottom: float
    filled_idx: int | None


@dataclass
class EqualLevel:
    """等高点 / 等低点。"""

    kind: str          # "eqh" | "eql"
    price: float       # 两点均价
    idx1: int
    idx2: int


@dataclass
class Sweep:
    """流动性扫荡：影线越过摆动点但收盘回到原侧。"""

    side: str          # "high"（越过高点）| "low"
    level: float
    level_idx: int
    idx: int


@dataclass
class Zone:
    """溢价 / 折价区的边界（含 50% 中位）。"""

    top: float
    bottom: float
    equilibrium: float
    start_idx: int
    end_idx: int


@dataclass
class Extreme:
    """强 / 弱高低点之一。"""

    price: float
    idx: int
    strength: str      # "strong" | "weak"


@dataclass
class Extremes:
    """最近的一组高、低极值。"""

    high: Extreme
    low: Extreme


@dataclass
class KeyLevel:
    """前一个已走完周期的最高 / 最低价。"""

    code: str          # PDH / PDL / PWH / PWL / PMH / PML
    price: float
    start_idx: int     # 当前周期第一根 K 线


@dataclass
class SmcResult:
    """一次分析的全部结构结果。"""

    swing_len: int = SWING_LEN
    trend: str = "none"            # bull | bear | none
    breaks: list[Break] = field(default_factory=list)
    order_blocks: list[OrderBlock] = field(default_factory=list)
    fvgs: list[Fvg] = field(default_factory=list)
    equal_levels: list[EqualLevel] = field(default_factory=list)
    sweeps: list[Sweep] = field(default_factory=list)
    zone: Zone | None = None
    extremes: Extremes | None = None
    key_levels: list[KeyLevel] = field(default_factory=list)


# ── 摆动点 ──────────────────────────────────────────────────────────────

def find_swings(bars: list[dict], length: int) -> list[Swing]:
    """左右各 `length` 根内的局部极值（左含等、右取严，平顶 / 平底不重复）。"""
    out: list[Swing] = []
    n = len(bars)
    for i in range(length, n - length):
        hi, lo = bars[i]["high"], bars[i]["low"]
        if (all(bars[j]["high"] <= hi for j in range(i - length, i))
                and all(bars[j]["high"] < hi for j in range(i + 1, i + length + 1))):
            out.append(Swing("high", i, hi))
        elif (all(bars[j]["low"] >= lo for j in range(i - length, i))
                and all(bars[j]["low"] > lo for j in range(i + 1, i + length + 1))):
            out.append(Swing("low", i, lo))
    return out


def _by_confirm(swings: list[Swing], length: int) -> dict[int, list[Swing]]:
    """摆动点在 `idx + length` 那根 K 线收盘时才被确认。"""
    d: dict[int, list[Swing]] = {}
    for s in swings:
        d.setdefault(s.idx + length, []).append(s)
    return d


# ── 结构突破 ────────────────────────────────────────────────────────────

def detect_breaks(bars: list[dict], swings: list[Swing], length: int) -> tuple[list[Break], str]:
    """收盘越过最近一个已确认的摆动点：顺着当前结构方向是 BOS，逆着是 CHoCH；每个摆动点只被突破一次。"""
    confirm = _by_confirm(swings, length)
    hi: Swing | None = None
    lo: Swing | None = None
    hi_open = lo_open = False
    trend = 0
    breaks: list[Break] = []
    for i, b in enumerate(bars):
        for s in confirm.get(i, []):
            if s.kind == "high":
                hi, hi_open = s, True
            else:
                lo, lo_open = s, True
        c = b["close"]
        if hi is not None and hi_open and c > hi.price:
            breaks.append(Break("choch" if trend == -1 else "bos", "bull", hi.price, hi.idx, i))
            hi_open, trend = False, 1
        elif lo is not None and lo_open and c < lo.price:
            breaks.append(Break("choch" if trend == 1 else "bos", "bear", lo.price, lo.idx, i))
            lo_open, trend = False, -1
    return breaks, {1: "bull", -1: "bear", 0: "none"}[trend]


# ── 订单块 ──────────────────────────────────────────────────────────────

def _mean_volume(bars: list[dict]) -> float:
    vols = [float(b.get("volume") or 0) for b in bars]
    return sum(vols) / len(vols) if vols else 0.0


def detect_order_blocks(bars: list[dict], breaks: list[Break]) -> list[OrderBlock]:
    """每次突破对应一个订单块；收盘反向穿过它即失效。"""
    mean_vol = _mean_volume(bars)
    n = len(bars)
    seen: set[tuple[str, int]] = set()
    out: list[OrderBlock] = []
    for b in breaks:
        rng = range(b.level_idx, b.break_idx)
        if not rng:
            continue
        if b.direction == "bull":
            idx = min(rng, key=lambda i: (bars[i]["low"], -i))      # 最低一根；并列取更晚的
        else:
            idx = max(rng, key=lambda i: (bars[i]["high"], i))      # 最高一根；并列取更晚的
        if (b.direction, idx) in seen:
            continue
        seen.add((b.direction, idx))
        top, bottom = bars[idx]["high"], bars[idx]["low"]
        if top <= bottom:
            continue
        mit: int | None = None
        for j in range(b.break_idx + 1, n):
            c = bars[j]["close"]
            if (b.direction == "bull" and c < bottom) or (b.direction == "bear" and c > top):
                mit = j
                break
        vol = float(bars[idx].get("volume") or 0)
        out.append(OrderBlock(b.direction, idx, top, bottom, b.break_idx, mit,
                              round(vol / mean_vol, 2) if mean_vol > 0 else 1.0))
    return out


# ── 公允价值缺口 ────────────────────────────────────────────────────────

def detect_fvgs(bars: list[dict]) -> list[Fvg]:
    """三根 K 线的缺口，中间那根实体须明显大于此前平均实体；价格回到缺口远端即填补。"""
    out: list[Fvg] = []
    n = len(bars)
    body_sum = 0.0   # 前面各根的 |实体%| 之和
    for i in range(n):
        o = bars[i]["open"]
        body = abs(bars[i]["close"] - o) / o * 100 if o else 0.0
        if i >= 2:
            m = bars[i - 1]
            mo = m["open"]
            mbody = (m["close"] - mo) / mo * 100 if mo else 0.0
            thr = FVG_BODY_MULT * (body_sum / (i - 1)) if i > 1 else 0.0   # 不含第 i 根本身
            first, third = bars[i - 2], bars[i]
            if mbody > thr and third["low"] > first["high"] and m["close"] > first["high"]:
                out.append(Fvg("bull", i - 1, third["low"], first["high"], None))
            elif mbody < -thr and third["high"] < first["low"] and m["close"] < first["low"]:
                out.append(Fvg("bear", i - 1, first["low"], third["high"], None))
        body_sum += body
    for g in out:
        for j in range(g.idx + 2, n):
            if (g.direction == "bull" and bars[j]["low"] <= g.bottom) or \
                    (g.direction == "bear" and bars[j]["high"] >= g.top):
                g.filled_idx = j
                break
    return out


# ── 等高点 / 等低点 ─────────────────────────────────────────────────────

def _atr(bars: list[dict], end: int, period: int = EQ_ATR_PERIOD) -> float:
    lo = max(1, end - period + 1)
    trs = []
    for i in range(lo, end + 1):
        hi, low, pc = bars[i]["high"], bars[i]["low"], bars[i - 1]["close"]
        trs.append(max(hi - low, abs(hi - pc), abs(low - pc)))
    return sum(trs) / len(trs) if trs else 0.0


def detect_equal_levels(bars: list[dict]) -> list[EqualLevel]:
    """相邻两个小级别摆动点之差小于 0.1 × ATR。"""
    out: list[EqualLevel] = []
    sw = find_swings(bars, EQ_SWING_LEN)
    for kind, name in (("high", "eqh"), ("low", "eql")):
        pts = [s for s in sw if s.kind == kind]
        for a, b in zip(pts, pts[1:], strict=False):
            atr = _atr(bars, b.idx)
            if atr > 0 and abs(a.price - b.price) < EQ_ATR_MULT * atr:
                out.append(EqualLevel(name, (a.price + b.price) / 2, a.idx, b.idx))
    out.sort(key=lambda e: e.idx2)
    return out


# ── 流动性扫荡 ──────────────────────────────────────────────────────────

def detect_sweeps(bars: list[dict], swings: list[Swing], length: int) -> list[Sweep]:
    """每个摆动点最多记一次：确认之后、被收盘突破之前，第一根影线越过它但收盘回到这一侧的 K 线。"""
    n = len(bars)
    out: list[Sweep] = []
    for s in swings:
        for j in range(s.idx + length + 1, n):
            b = bars[j]
            if s.kind == "high":
                if b["close"] > s.price:
                    break
                if b["high"] > s.price:
                    out.append(Sweep("high", s.price, s.idx, j))
                    break
            else:
                if b["close"] < s.price:
                    break
                if b["low"] < s.price:
                    out.append(Sweep("low", s.price, s.idx, j))
                    break
    out.sort(key=lambda x: x.idx)
    return out


# ── 溢价 / 折价、强弱高低点 ────────────────────────────────────────────

def trailing_extremes(bars: list[dict], swings: list[Swing], length: int) -> tuple[tuple[float, int] | None, tuple[float, int] | None]:
    """最近确认的摆动高 / 低点，之后被更高的高点 / 更低的低点延伸（LuxAlgo 的 trailing top / bottom）。"""
    confirm = _by_confirm(swings, length)
    top: tuple[float, int] | None = None
    bot: tuple[float, int] | None = None
    for i, b in enumerate(bars):
        for s in confirm.get(i, []):
            if s.kind == "high":
                top = (s.price, s.idx)
            else:
                bot = (s.price, s.idx)
        if top is not None and b["high"] > top[0]:
            top = (b["high"], i)
        if bot is not None and b["low"] < bot[0]:
            bot = (b["low"], i)
    return top, bot


# ── 前日 / 周 / 月高低点 ───────────────────────────────────────────────

def _period_key(t: str, kind: str) -> tuple:
    """K 线时间所属的日 / 周 / 月（用来分组）。"""
    d = date.fromisoformat(t[:10])
    if kind == "D":
        return (d.toordinal(),)
    if kind == "W":
        return d.isocalendar()[:2]
    return (d.year, d.month)


_KEY_PERIODS = {"daily": ("W", "M"), "30min": ("D", "W"), "weekly": ("M",)}


def key_levels(bars: list[dict], freq: str) -> list[KeyLevel]:
    """上一个已走完的周期（日 / 周 / 月，随图表周期）的最高 / 最低价，线从当前周期第一根画起。"""
    out: list[KeyLevel] = []
    if not bars:
        return out
    for kind in _KEY_PERIODS.get(freq, ()):
        keys = [_period_key(str(b["time"]), kind) for b in bars]
        cur = keys[-1]
        start = next(i for i, k in enumerate(keys) if k == cur)   # 当前周期第一根
        if start == 0:
            continue                                               # 没有上一个周期
        prev_key = keys[start - 1]
        prev = [b for b, k in zip(bars, keys, strict=True) if k == prev_key]
        out.append(KeyLevel(f"P{kind}H", max(b["high"] for b in prev), start))
        out.append(KeyLevel(f"P{kind}L", min(b["low"] for b in prev), start))
    return out


# ── 汇总 ────────────────────────────────────────────────────────────────

def analyze(bars: list[dict], *, swing_len: int | None = None, freq: str = "daily") -> SmcResult:
    """识别全部 SMC 结构；K 线不足时返回空结果。"""
    if swing_len is None:
        swing_len = SWING_LEN_BY_FREQ.get(freq, SWING_LEN)
    res = SmcResult(swing_len=swing_len)
    n = len(bars)
    if n < 2 * swing_len + 2:
        return res
    swings = find_swings(bars, swing_len)
    res.breaks, res.trend = detect_breaks(bars, swings, swing_len)
    res.order_blocks = detect_order_blocks(bars, res.breaks)
    res.fvgs = detect_fvgs(bars)
    res.equal_levels = detect_equal_levels(bars)
    res.sweeps = detect_sweeps(bars, swings, swing_len)
    top, bot = trailing_extremes(bars, swings, swing_len)
    if top and bot and top[0] > bot[0]:
        res.zone = Zone(top[0], bot[0], (top[0] + bot[0]) / 2, min(top[1], bot[1]), n - 1)
        if res.trend != "none":
            res.extremes = Extremes(
                high=Extreme(top[0], top[1], "strong" if res.trend == "bear" else "weak"),
                low=Extreme(bot[0], bot[1], "strong" if res.trend == "bull" else "weak"),
            )
    try:
        res.key_levels = key_levels(bars, freq)
    except ValueError:
        res.key_levels = []   # 时间格式异常：只是少画几条线，不影响其余结构
    return res
