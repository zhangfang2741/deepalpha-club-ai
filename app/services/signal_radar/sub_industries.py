"""基本面名单的子行业标签（只用来在名单里按子行业细分，不进雷达快照、不筛雷达画布）。

- 美股：标普 1500 维基成分表的「GICS Sub-Industry」列（与一级行业同一来源，`quant_research.universe` 只解析了一级），
  中文界面按 `GICS_SUB_ZH` 显示中文名。
- A 股：东财行业名本身就是申万二级（`cnhk/sectors.CN_INDUSTRY_TO_SW` 的键），显示时去掉「Ⅱ」后缀。
- 港股：东财行业名即恒生二级（`HK_INDUSTRY_TO_HS` 的键）。
标签存原名（{代码: 子行业原名}），Redis 缓存 24 小时；取回过少视为残缺、不缓存；取数失败返回空（名单照常，只是没有子行业）。
"""
from __future__ import annotations

import asyncio
import io
import json
import re
from datetime import UTC, datetime

import httpx
import pandas as pd
from redis.asyncio import Redis

from app.core.logging import logger

CACHE_PREFIX = "signal_radar:sub_tags:v1"
CACHE_TTL = 24 * 3600
# 取回少于这个只数视为残缺（维基任一页失败 / 东财限流），不缓存
_MIN_TAGS = {"us": 1200, "cn": 1000, "hk": 200}
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z\-]{0,6}$")
_UA = "Mozilla/5.0 (compatible; DeepAlphaQuant/1.0; +https://deepalpha.club)"
_WIKI_PAGES = (
    "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
    "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
)

# GICS 子行业 → 中文名（覆盖 2026-10-09 标普 1500 维基成分表出现的全部 154 个；新出现的没有对照时显示英文原名）
GICS_SUB_ZH: dict[str, str] = {
    # 通讯服务
    "Advertising": "广告", "Alternative Carriers": "替代电信运营商", "Broadcasting": "广播",
    "Cable & Satellite": "有线与卫星电视", "Integrated Telecommunication Services": "综合电信服务",
    "Interactive Home Entertainment": "互动家庭娱乐", "Interactive Media & Services": "互动媒体与服务",
    "Movies & Entertainment": "电影与娱乐", "Publishing": "出版", "Wireless Telecommunication Services": "无线电信服务",
    # 可选消费
    "Apparel Retail": "服装零售", "Apparel, Accessories & Luxury Goods": "服装、配饰与奢侈品",
    "Automobile Manufacturers": "汽车制造", "Automotive Parts & Equipment": "汽车零部件", "Automotive Retail": "汽车零售",
    "Broadline Retail": "综合零售", "Casinos & Gaming": "博彩", "Computer & Electronics Retail": "电脑与电子产品零售",
    "Consumer Electronics": "消费电子", "Distributors": "分销商", "Education Services": "教育服务", "Footwear": "鞋类",
    "Home Furnishings": "家居装饰", "Home Improvement Retail": "家装零售", "Homebuilding": "住宅建筑",
    "Homefurnishing Retail": "家居零售", "Hotels, Resorts & Cruise Lines": "酒店、度假村与邮轮",
    "Household Appliances": "家用电器", "Housewares & Specialties": "家居用品", "Leisure Facilities": "休闲设施",
    "Leisure Products": "休闲用品", "Motorcycle Manufacturers": "摩托车制造", "Other Specialty Retail": "其他专业零售",
    "Restaurants": "餐饮", "Specialized Consumer Services": "专业消费服务", "Specialty Stores": "专卖店",
    "Tires & Rubber": "轮胎与橡胶",
    # 必需消费
    "Agricultural Products & Services": "农产品与服务", "Consumer Staples Merchandise Retail": "日用品零售",
    "Distillers & Vintners": "酿酒", "Food Distributors": "食品分销", "Food Retail": "食品零售",
    "Household Products": "家庭用品", "Packaged Foods & Meats": "包装食品与肉类", "Personal Care Products": "个人护理用品",
    "Soft Drinks & Non-alcoholic Beverages": "软饮料", "Tobacco": "烟草", "Brewers": "啤酒",
    "Drug Retail": "药品零售",
    # 能源
    "Coal & Consumable Fuels": "煤炭与消费用燃料", "Integrated Oil & Gas": "综合油气", "Oil & Gas Drilling": "油气钻井",
    "Oil & Gas Equipment & Services": "油气设备与服务", "Oil & Gas Exploration & Production": "油气勘探与开采",
    "Oil & Gas Refining & Marketing": "油气炼化与销售", "Oil & Gas Storage & Transportation": "油气储运",
    # 金融
    "Asset Management & Custody Banks": "资产管理与托管银行", "Commercial & Residential Mortgage Finance": "商业与住房抵押贷款",
    "Consumer Finance": "消费金融", "Diversified Banks": "综合性银行", "Diversified Capital Markets": "综合资本市场",
    "Diversified Financial Services": "综合金融服务", "Financial Exchanges & Data": "金融交易所与数据",
    "Insurance Brokers": "保险经纪", "Investment Banking & Brokerage": "投资银行与经纪", "Life & Health Insurance": "人寿与健康保险",
    "Mortgage REITs": "抵押房地产信托", "Multi-Sector Holdings": "多元控股", "Multi-line Insurance": "多元保险",
    "Property & Casualty Insurance": "财产与意外险", "Regional Banks": "区域银行", "Reinsurance": "再保险",
    "Specialized Finance": "专业金融", "Transaction & Payment Processing Services": "交易与支付处理",
    # 医疗
    "Biotechnology": "生物科技", "Health Care Distributors": "医疗分销", "Health Care Equipment": "医疗设备",
    "Health Care Facilities": "医疗机构", "Health Care Services": "医疗服务", "Health Care Supplies": "医疗用品",
    "Health Care Technology": "医疗科技", "Life Sciences Tools & Services": "生命科学工具与服务",
    "Managed Health Care": "管理式医疗", "Pharmaceuticals": "制药",
    # 工业
    "Aerospace & Defense": "航空航天与国防", "Air Freight & Logistics": "航空货运与物流", "Building Products": "建筑产品",
    "Cargo Ground Transportation": "陆路货运", "Commercial Printing": "商业印刷", "Construction & Engineering": "建筑与工程",
    "Construction Machinery & Heavy Transportation Equipment": "工程机械与重型运输设备",
    "Data Processing & Outsourced Services": "数据处理与外包服务", "Diversified Support Services": "综合支持服务",
    "Electrical Components & Equipment": "电气部件与设备", "Environmental & Facilities Services": "环境与设施服务",
    "Heavy Electrical Equipment": "重型电气设备", "Human Resource & Employment Services": "人力资源与就业服务",
    "Industrial Conglomerates": "工业集团", "Industrial Machinery & Supplies & Components": "工业机械与零部件",
    "Marine Transportation": "海运", "Office Services & Supplies": "办公服务与用品", "Passenger Airlines": "客运航空",
    "Passenger Ground Transportation": "陆路客运", "Rail Transportation": "铁路运输", "Research & Consulting Services": "研究与咨询服务",
    "Security & Alarm Services": "安保服务", "Trading Companies & Distributors": "贸易与分销",
    "Agricultural & Farm Machinery": "农业机械", "Airport Services": "机场服务", "Marine Ports & Services": "港口与服务",
    "Highways & Railtracks": "公路与铁路设施",
    # 信息技术
    "Application Software": "应用软件", "Communications Equipment": "通信设备", "Electronic Components": "电子元件",
    "Electronic Equipment & Instruments": "电子设备与仪器", "Electronic Manufacturing Services": "电子制造服务",
    "IT Consulting & Other Services": "IT 咨询与其他服务", "Internet Services & Infrastructure": "互联网服务与基础设施",
    "Semiconductor Materials & Equipment": "半导体材料与设备", "Semiconductors": "半导体", "Systems Software": "系统软件",
    "Technology Distributors": "科技产品分销", "Technology Hardware, Storage & Peripherals": "电脑硬件、存储与外设",
    # 原材料
    "Aluminum": "铝", "Commodity Chemicals": "基础化工", "Construction Materials": "建筑材料", "Copper": "铜",
    "Diversified Chemicals": "综合化工", "Diversified Metals & Mining": "综合金属与采矿",
    "Fertilizers & Agricultural Chemicals": "化肥与农用化学品", "Gold": "黄金", "Industrial Gases": "工业气体",
    "Metal, Glass & Plastic Containers": "金属、玻璃与塑料容器",
    "Paper & Plastic Packaging Products & Materials": "纸质与塑料包装", "Paper Products": "纸制品", "Silver": "白银",
    "Specialty Chemicals": "特种化工", "Steel": "钢铁", "Forest Products": "林产品",
    "Precious Metals & Minerals": "贵金属与矿物",
    # 房地产
    "Data Center REITs": "数据中心房地产信托", "Diversified REITs": "综合房地产信托", "Health Care REITs": "医疗房地产信托",
    "Hotel & Resort REITs": "酒店与度假村房地产信托", "Industrial REITs": "工业房地产信托",
    "Multi-Family Residential REITs": "多户住宅房地产信托", "Office REITs": "写字楼房地产信托",
    "Other Specialized REITs": "其他专业房地产信托", "Real Estate Development": "房地产开发", "Real Estate Services": "房地产服务",
    "Retail REITs": "零售房地产信托", "Self-Storage REITs": "自助仓储房地产信托",
    "Single-Family Residential REITs": "单户住宅房地产信托", "Telecom Tower REITs": "通信塔房地产信托",
    "Timber REITs": "林地房地产信托", "Diversified Real Estate Activities": "综合房地产业务",
    "Real Estate Operating Companies": "房地产运营",
    # 公用事业
    "Electric Utilities": "电力公用事业", "Gas Utilities": "燃气公用事业",
    "Independent Power Producers & Energy Traders": "独立发电与能源交易", "Multi-Utilities": "综合公用事业",
    "Renewable Electricity": "可再生能源发电", "Water Utilities": "水务",
}


def parse_sub_table(html: str) -> dict[str, str]:
    """解析维基成分表 → {代码: GICS 子行业英文名}。代码点号换连字符（BRK.B → BRK-B），丢弃异常代码。"""
    try:
        tables = pd.read_html(io.StringIO(html))
    except ValueError:
        return {}
    for tbl in tables:
        cols = [str(c) for c in tbl.columns]
        if "Symbol" in cols and "GICS Sub-Industry" in cols:
            out: dict[str, str] = {}
            for sym, sub in zip(tbl["Symbol"], tbl["GICS Sub-Industry"], strict=False):
                s = str(sym).strip().replace(".", "-")
                name = str(sub).strip()
                if _SYMBOL_RE.match(s) and name and name != "nan":
                    out[s] = name
            return out
    return {}


def display_name(market: str, raw: str, lang: str) -> str:
    """子行业展示名：美股中文界面查对照表（没有就用英文原名）；A 股去掉申万二级的「Ⅱ」后缀；港股原样。"""
    if market == "us":
        return GICS_SUB_ZH.get(raw, raw) if lang == "zh" else raw
    if market == "cn":
        return raw.rstrip("Ⅱ").strip()
    return raw


def cnhk_sub_tags(market: str, meta: dict[str, object]) -> dict[str, str]:
    """{代码: 东财元数据} → {代码: 子行业原名}；只收已映射到本土一级行业的东财行业名。"""
    from app.services.quant_research.cnhk.sectors import CN_INDUSTRY_TO_SW, HK_INDUSTRY_TO_HS

    known = CN_INDUSTRY_TO_SW if market == "cn" else HK_INDUSTRY_TO_HS
    out: dict[str, str] = {}
    for code, m in meta.items():
        industry = (getattr(m, "industry", None) or "").strip()
        if industry in known:
            out[code] = industry
    return out


async def _fetch_us() -> dict[str, str]:
    out: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": _UA}, follow_redirects=True) as c:
        for url in _WIKI_PAGES:
            resp = await c.get(url)
            if resp.status_code == 200:
                for sym, sub in (await asyncio.to_thread(parse_sub_table, resp.text)).items():
                    out.setdefault(sym, sub)
    return out


async def _fetch_cnhk(market: str) -> dict[str, str]:
    from app.services.quant_research.cnhk import cn_source, hk_source
    from app.services.quant_research.cnhk.http import _UA as CNHK_UA

    async with httpx.AsyncClient(timeout=60, headers={"User-Agent": CNHK_UA}, trust_env=False) as client:
        if market == "cn":
            meta = await cn_source.fetch_market_meta(client)
        else:
            meta = await hk_source.fetch_meta(client, datetime.now(UTC).date())
    return cnhk_sub_tags(market, meta)  # type: ignore[arg-type]


async def _fetch(market: str) -> dict[str, str]:
    return await _fetch_us() if market == "us" else await _fetch_cnhk(market)


async def load_sub_tags(market: str, redis: Redis | None) -> dict[str, str]:
    """{代码: 子行业原名}；不支持的市场或取数失败返回空。"""
    if market not in _MIN_TAGS:
        return {}
    key = f"{CACHE_PREFIX}:{market}"
    if redis is not None:
        try:
            raw = await redis.get(key)
            if raw:
                return json.loads(raw)
        except Exception as e:  # noqa: BLE001
            logger.warning("signal_radar_sub_tags_cache_read_failed", market=market, error=str(e))
    try:
        tags = await _fetch(market)
    except Exception as e:  # noqa: BLE001
        logger.warning("signal_radar_sub_tags_fetch_failed", market=market, error=str(e))
        return {}
    if len(tags) < _MIN_TAGS[market]:
        logger.warning("signal_radar_sub_tags_incomplete", market=market, count=len(tags))
        return tags
    if redis is not None:
        try:
            await redis.set(key, json.dumps(tags, ensure_ascii=False), ex=CACHE_TTL)
        except Exception as e:  # noqa: BLE001
            logger.warning("signal_radar_sub_tags_cache_write_failed", market=market, error=str(e))
    return tags
