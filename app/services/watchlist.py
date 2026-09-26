"""自选股存取：直接对 watchlist_item 表做增删查，业务逻辑很薄不单独分层。"""
from __future__ import annotations

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.watchlist import WatchlistItem
from app.services.signal_radar.universe import resolve_name

# 各订阅档自选上限：未订阅 1 / 基础版 10 / 高级版不限（None）。定死在这里而非
# config.py：这是产品规则，不是环境相关配置。tier 由客户端按 StoreKit 本地判断后
# 随请求传入——本项目未接入服务端收据校验，跟 UsageTracker 的免费额度一样是端上
# 可信任模型（后续如需加固可在服务端做收据验证）。tier 非法或缺省一律按最保守的
# free 处理。
TIER_LIMITS: dict[str, int | None] = {"free": 1, "basic": 10, "premium": None}
DEFAULT_TIER = "free"


# 示例自选：每个用户默认送的三只（美/A/港市值龙头，A 股选贵州茅台而非市值第一的工商银行
# ——银行股波动小、缠论结构不明显，不适合当样例）。不占名额、可删、删了不再补；点进去
# 免额度、可看完整 30 分钟次级别（iOS 端 AppConfig.sampleSymbols 与此保持一致）。
SAMPLE_ITEMS: list[tuple[str, str, str]] = [
    ("us", "NVDA", "英伟达"),
    ("cn", "600519", "贵州茅台"),
    ("hk", "0700", "腾讯控股"),
]


def samples_to_seed(rows: list[WatchlistItem]) -> list[tuple[str, str, str]]:
    """该用户还需要补的示例自选。

    rows 是用户全部记录（含已隐藏的）。只要出现过任何一条示例记录就说明送过了，
    一条都不补——哪怕用户把它们全删了（删除只置 hidden）。用户自己已关注的同一只不重复送。
    """
    if any(r.is_sample for r in rows):
        return []
    owned = {(r.market, r.symbol) for r in rows}
    return [s for s in SAMPLE_ITEMS if (s[0], s[1]) not in owned]


async def ensure_samples(db: AsyncSession, user_id: int) -> None:
    """首次读自选列表时补上示例自选（每个用户只补一次）。"""
    rows = list((await db.execute(select(WatchlistItem).where(WatchlistItem.user_id == user_id))).scalars().all())
    seeds = samples_to_seed(rows)
    if not seeds:
        return
    for market, symbol, name in seeds:
        db.add(WatchlistItem(user_id=user_id, market=market, symbol=symbol, name=name, is_sample=True))
    await db.commit()


def max_items_for(tier: str) -> int | None:
    """某订阅档的自选上限，None 表示不限（高级版）。"""
    return TIER_LIMITS.get(tier, TIER_LIMITS[DEFAULT_TIER])


class WatchlistLimitExceeded(Exception):
    """加入自选时已达当前订阅档上限，供 API 层转换成 400 响应。"""

    def __init__(self, limit: int):
        """limit：触发异常时命中的上限值，供 API 层拼进错误提示。"""
        self.limit = limit
        super().__init__(f"watchlist limit exceeded: {limit}")


def display_name(market: str, symbol: str, stored: str) -> str:
    """自选条目的展示名：存的名字为空或就等于代码时补上中文名，否则原样保留。

    补名字复用信号雷达同一套 curated 成分清单（如 2015 → 理想汽车），补不到就回落
    代码本身。读列表和加入时都过一遍，既修好历史上「只存了代码」的老条目，也保证
    以后新增的条目直接带上名称。
    """
    name = (stored or "").strip()
    if name and name.upper() != symbol.strip().upper():
        return name
    return resolve_name(market, symbol) or name or symbol


async def list_items(db: AsyncSession, user_id: int) -> list[WatchlistItem]:
    """按加入时间倒序，最近加入的在前；不含用户删掉的示例股（hidden）。"""
    result = await db.execute(
        select(WatchlistItem)
        .where(WatchlistItem.user_id == user_id, col(WatchlistItem.hidden).is_(False))
        .order_by(col(WatchlistItem.created_at).desc())
    )
    return list(result.scalars().all())


async def add_item(
    db: AsyncSession, user_id: int, market: str, symbol: str, name: str, tier: str = DEFAULT_TIER,
) -> WatchlistItem:
    """加入自选：已存在同 (market, symbol) 则视为幂等成功，只更新展示名称。

    未存在且已达 tier 对应上限则抛 WatchlistLimitExceeded（幂等更新不受限，
    避免「已在自选里」的标的因为达到上限反而改不了名称）。
    """
    symbol = symbol.strip().upper()
    # 客户端只有代码没有真名时（name 传成了代码），用 curated 成分清单补中文名再落库，
    # 让存进去的就是「理想汽车」而不是「2015」。
    name = display_name(market, symbol, name)
    existing = (
        await db.execute(
            select(WatchlistItem).where(
                WatchlistItem.user_id == user_id,
                WatchlistItem.market == market,
                WatchlistItem.symbol == symbol,
            )
        )
    ).scalars().first()
    if existing and not existing.hidden:
        existing.name = name
        db.add(existing)
        await db.commit()
        await db.refresh(existing)
        return existing

    # 名额只算用户自己加的：示例股与已删的示例股都不计入
    limit = max_items_for(tier)
    if limit is not None:
        count = (
            await db.execute(
                select(func.count()).select_from(WatchlistItem).where(
                    WatchlistItem.user_id == user_id,
                    col(WatchlistItem.is_sample).is_(False),
                    col(WatchlistItem.hidden).is_(False),
                )
            )
        ).scalar_one()
        if count >= limit:
            raise WatchlistLimitExceeded(limit)

    if existing:
        # 删掉过的示例股又被用户自己加回来：转成普通自选（上面已按名额校验过）
        existing.hidden = False
        existing.is_sample = False
        existing.name = name
        db.add(existing)
        await db.commit()
        await db.refresh(existing)
        return existing

    item = WatchlistItem(user_id=user_id, market=market, symbol=symbol, name=name)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def remove_item(db: AsyncSession, user_id: int, market: str, symbol: str) -> bool:
    """移出自选。返回是否真的删到了一条（供 API 层决定是否 404）。

    示例股只置 hidden 不真删（见 WatchlistItem.is_sample），已隐藏的视为不存在。
    """
    symbol = symbol.strip().upper()
    existing = (
        await db.execute(
            select(WatchlistItem).where(
                WatchlistItem.user_id == user_id,
                WatchlistItem.market == market,
                WatchlistItem.symbol == symbol,
            )
        )
    ).scalars().first()
    if existing is None or existing.hidden:
        return False
    if existing.is_sample:
        existing.hidden = True
        db.add(existing)
    else:
        await db.delete(existing)
    await db.commit()
    return True
