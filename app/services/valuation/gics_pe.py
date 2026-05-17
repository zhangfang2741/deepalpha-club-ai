"""GICS 两层行业 PE 估值服务。

数据来源：
  一级板块：FMP v4 /sector_price_earning_ratio（11 大类，付费端点）
  细粒度行业：FMP v4 /industry_price_earning_ratio（60+ 子行业，付费端点）

批量拉取 5 年 × 20 季度末数据，构建带 z-score 的估值层级树。
"""

import asyncio
import statistics
from datetime import date
from typing import Dict, List, Tuple

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.schemas.valuation import GICSValuationResponse, IndustryValuation, SectorWithIndustries
from app.services.valuation.sector_pe import (
    SECTOR_CN_MAP,
    _quarter_end_dates,
    compute_z_score,
    get_valuation_label,
)

_FMP_V4_BASE = "https://financialmodelingprep.com/api/v4"
_BATCH_SIZE = 10
_YEARS = 5

# FMP 行业英文名 → 中文
INDUSTRY_CN_MAP: Dict[str, str] = {
    "Semiconductors": "半导体",
    "Semiconductor Equipment & Materials": "半导体设备与材料",
    "Software - Application": "应用软件",
    "Software - Infrastructure": "基础设施软件",
    "Information Technology Services": "IT 服务",
    "Computer Hardware": "计算机硬件",
    "Electronic Components": "电子元件",
    "Consumer Electronics": "消费电子",
    "Electronic Gaming & Multimedia": "电子游戏与多媒体",
    "Scientific & Technical Instruments": "科学与技术仪器",
    "Solar": "太阳能",
    "Biotechnology": "生物科技",
    "Drug Manufacturers - General": "大型制药",
    "Drug Manufacturers - Specialty & Generic": "特种/仿制药",
    "Healthcare Plans": "医疗保险",
    "Medical Devices": "医疗设备",
    "Medical Instruments & Supplies": "医疗器械与耗材",
    "Diagnostics & Research": "诊断与研究",
    "Health Information Services": "医疗信息服务",
    "Medical Care Facilities": "医疗机构",
    "Pharmaceutical Retailers": "药品零售",
    "Banks - Diversified": "多元化银行",
    "Banks - Regional": "区域性银行",
    "Insurance - Diversified": "多元化保险",
    "Insurance - Life": "人寿保险",
    "Insurance - Property & Casualty": "财产险/意外险",
    "Insurance - Specialty": "专业保险",
    "Insurance - Reinsurance": "再保险",
    "Investment Banking & Investment Services": "投行与投资服务",
    "Capital Markets": "资本市场",
    "Asset Management": "资产管理",
    "Credit Services": "信贷服务",
    "Mortgage Finance": "房贷金融",
    "Financial - Data & Stock Exchanges": "金融数据与交易所",
    "Financial Conglomerates": "金融集团",
    "Advertising Agencies": "广告代理",
    "Broadcasting": "广播",
    "Entertainment": "娱乐",
    "Internet Content & Information": "互联网内容与信息",
    "Publishing": "出版",
    "Telecom Services": "电信服务",
    "Telecommunications": "电信",
    "Auto Manufacturers": "汽车制造",
    "Auto Parts": "汽车零部件",
    "Apparel Manufacturing": "服装制造",
    "Apparel Retail": "服装零售",
    "Department Stores": "百货商场",
    "Specialty Retail": "专业零售",
    "Home Improvement Retail": "家装零售",
    "Furnishings, Fixtures & Appliances": "家具与家电",
    "Residential Construction": "住宅建设",
    "Luxury Goods": "奢侈品",
    "Footwear & Accessories": "鞋类与配饰",
    "Internet Retail": "电商零售",
    "Restaurants": "餐饮",
    "Recreational Vehicles": "休闲车辆",
    "Travel Services": "旅行服务",
    "Hotels & Motels": "酒店与汽车旅馆",
    "Resorts & Casinos": "度假村与赌场",
    "Gambling": "博彩",
    "Leisure": "休闲",
    "Beverages - Non-Alcoholic": "无酒精饮料",
    "Beverages - Alcoholic": "含酒精饮料",
    "Beverages - Brewers": "啤酒",
    "Beverages - Wineries & Distilleries": "葡萄酒与烈酒",
    "Confectioners": "糖果与零食",
    "Discount Stores": "折扣商店",
    "Education & Training Services": "教育与培训",
    "Food Distribution": "食品配送",
    "Grocery Stores": "超市",
    "Household & Personal Products": "家居与个人用品",
    "Packaged Foods": "包装食品",
    "Tobacco": "烟草",
    "Farm Products": "农产品",
    "Aerospace & Defense": "航空航天与国防",
    "Airlines": "航空公司",
    "Airports & Air Services": "机场与航空服务",
    "Business Equipment & Supplies": "商业设备与用品",
    "Conglomerates": "综合企业",
    "Consulting Services": "咨询服务",
    "Electrical Equipment & Parts": "电气设备与零件",
    "Engineering & Construction": "工程与建设",
    "Farm & Heavy Construction Machinery": "农业与重型机械",
    "Industrial Distribution": "工业品分销",
    "Infrastructure Operations": "基础设施运营",
    "Integrated Freight & Logistics": "综合物流",
    "Marine Shipping": "海运",
    "Metal Fabrication": "金属加工",
    "Pollution & Treatment Controls": "污染控制与处理",
    "Railroads": "铁路",
    "Rental & Leasing Services": "租赁服务",
    "Security & Protection Services": "安防服务",
    "Specialty Business Services": "专业商业服务",
    "Specialty Industrial Machinery": "专用工业机械",
    "Staffing & Employment Services": "人力资源服务",
    "Tools & Accessories": "工具与配件",
    "Trucking": "公路货运",
    "Waste Management": "废物处理",
    "Oil & Gas E&P": "石油天然气勘探开发",
    "Oil & Gas Integrated": "综合石油",
    "Oil & Gas Midstream": "石油中游",
    "Oil & Gas Refining & Marketing": "炼油与销售",
    "Oil & Gas Equipment & Services": "油气设备与服务",
    "Oil & Gas Drilling": "石油钻探",
    "Thermal Coal": "动力煤",
    "Uranium": "铀",
    "Utilities - Regulated Electric": "受监管电力",
    "Utilities - Regulated Gas": "受监管燃气",
    "Utilities - Regulated Water": "受监管水务",
    "Utilities - Renewable": "可再生能源",
    "Utilities - Independent Power Producers": "独立发电商",
    "Utilities - Diversified": "多元化公用事业",
    "REIT - Diversified": "多元化 REITs",
    "REIT - Healthcare Facilities": "医疗设施 REITs",
    "REIT - Hotel & Motel": "酒店 REITs",
    "REIT - Industrial": "工业 REITs",
    "REIT - Mortgage": "抵押贷款 REITs",
    "REIT - Office": "办公室 REITs",
    "REIT - Residential": "住宅 REITs",
    "REIT - Retail": "零售 REITs",
    "REIT - Specialty": "特种 REITs",
    "Real Estate Services": "房地产服务",
    "Real Estate - Development": "房地产开发",
    "Real Estate - Diversified": "多元化房地产",
    "Aluminum": "铝",
    "Building Materials": "建筑材料",
    "Chemicals": "化工",
    "Specialty Chemicals": "特种化工",
    "Agricultural Inputs": "农业投入品",
    "Coking Coal": "焦煤",
    "Copper": "铜",
    "Gold": "黄金",
    "Lumber & Wood Production": "木材与林木",
    "Other Industrial Metals & Mining": "其他工业金属与矿业",
    "Other Precious Metals & Mining": "其他贵金属与矿业",
    "Paper & Paper Products": "纸张与纸制品",
    "Silver": "白银",
    "Steel": "钢铁",
    "Industrial Metals & Mining": "工业金属与矿业",
}

# FMP industry 名 → 归属的 FMP sector 名
INDUSTRY_TO_SECTOR: Dict[str, str] = {
    "Semiconductors": "Technology",
    "Semiconductor Equipment & Materials": "Technology",
    "Software - Application": "Technology",
    "Software - Infrastructure": "Technology",
    "Information Technology Services": "Technology",
    "Computer Hardware": "Technology",
    "Electronic Components": "Technology",
    "Consumer Electronics": "Technology",
    "Electronic Gaming & Multimedia": "Technology",
    "Scientific & Technical Instruments": "Technology",
    "Solar": "Technology",
    "Biotechnology": "Healthcare",
    "Drug Manufacturers - General": "Healthcare",
    "Drug Manufacturers - Specialty & Generic": "Healthcare",
    "Healthcare Plans": "Healthcare",
    "Medical Devices": "Healthcare",
    "Medical Instruments & Supplies": "Healthcare",
    "Diagnostics & Research": "Healthcare",
    "Health Information Services": "Healthcare",
    "Medical Care Facilities": "Healthcare",
    "Pharmaceutical Retailers": "Healthcare",
    "Banks - Diversified": "Financial Services",
    "Banks - Regional": "Financial Services",
    "Insurance - Diversified": "Financial Services",
    "Insurance - Life": "Financial Services",
    "Insurance - Property & Casualty": "Financial Services",
    "Insurance - Specialty": "Financial Services",
    "Insurance - Reinsurance": "Financial Services",
    "Investment Banking & Investment Services": "Financial Services",
    "Capital Markets": "Financial Services",
    "Asset Management": "Financial Services",
    "Credit Services": "Financial Services",
    "Mortgage Finance": "Financial Services",
    "Financial - Data & Stock Exchanges": "Financial Services",
    "Financial Conglomerates": "Financial Services",
    "Advertising Agencies": "Communication Services",
    "Broadcasting": "Communication Services",
    "Entertainment": "Communication Services",
    "Internet Content & Information": "Communication Services",
    "Publishing": "Communication Services",
    "Telecom Services": "Communication Services",
    "Telecommunications": "Communication Services",
    "Auto Manufacturers": "Consumer Cyclical",
    "Auto Parts": "Consumer Cyclical",
    "Apparel Manufacturing": "Consumer Cyclical",
    "Apparel Retail": "Consumer Cyclical",
    "Department Stores": "Consumer Cyclical",
    "Specialty Retail": "Consumer Cyclical",
    "Home Improvement Retail": "Consumer Cyclical",
    "Furnishings, Fixtures & Appliances": "Consumer Cyclical",
    "Residential Construction": "Consumer Cyclical",
    "Luxury Goods": "Consumer Cyclical",
    "Footwear & Accessories": "Consumer Cyclical",
    "Internet Retail": "Consumer Cyclical",
    "Restaurants": "Consumer Cyclical",
    "Recreational Vehicles": "Consumer Cyclical",
    "Travel Services": "Consumer Cyclical",
    "Hotels & Motels": "Consumer Cyclical",
    "Resorts & Casinos": "Consumer Cyclical",
    "Gambling": "Consumer Cyclical",
    "Leisure": "Consumer Cyclical",
    "Beverages - Non-Alcoholic": "Consumer Defensive",
    "Beverages - Alcoholic": "Consumer Defensive",
    "Beverages - Brewers": "Consumer Defensive",
    "Beverages - Wineries & Distilleries": "Consumer Defensive",
    "Confectioners": "Consumer Defensive",
    "Discount Stores": "Consumer Defensive",
    "Education & Training Services": "Consumer Defensive",
    "Food Distribution": "Consumer Defensive",
    "Grocery Stores": "Consumer Defensive",
    "Household & Personal Products": "Consumer Defensive",
    "Packaged Foods": "Consumer Defensive",
    "Tobacco": "Consumer Defensive",
    "Farm Products": "Consumer Defensive",
    "Aerospace & Defense": "Industrials",
    "Airlines": "Industrials",
    "Airports & Air Services": "Industrials",
    "Business Equipment & Supplies": "Industrials",
    "Conglomerates": "Industrials",
    "Consulting Services": "Industrials",
    "Electrical Equipment & Parts": "Industrials",
    "Engineering & Construction": "Industrials",
    "Farm & Heavy Construction Machinery": "Industrials",
    "Industrial Distribution": "Industrials",
    "Infrastructure Operations": "Industrials",
    "Integrated Freight & Logistics": "Industrials",
    "Marine Shipping": "Industrials",
    "Metal Fabrication": "Industrials",
    "Pollution & Treatment Controls": "Industrials",
    "Railroads": "Industrials",
    "Rental & Leasing Services": "Industrials",
    "Security & Protection Services": "Industrials",
    "Specialty Business Services": "Industrials",
    "Specialty Industrial Machinery": "Industrials",
    "Staffing & Employment Services": "Industrials",
    "Tools & Accessories": "Industrials",
    "Trucking": "Industrials",
    "Waste Management": "Industrials",
    "Oil & Gas E&P": "Energy",
    "Oil & Gas Integrated": "Energy",
    "Oil & Gas Midstream": "Energy",
    "Oil & Gas Refining & Marketing": "Energy",
    "Oil & Gas Equipment & Services": "Energy",
    "Oil & Gas Drilling": "Energy",
    "Thermal Coal": "Energy",
    "Uranium": "Energy",
    "Utilities - Regulated Electric": "Utilities",
    "Utilities - Regulated Gas": "Utilities",
    "Utilities - Regulated Water": "Utilities",
    "Utilities - Renewable": "Utilities",
    "Utilities - Independent Power Producers": "Utilities",
    "Utilities - Diversified": "Utilities",
    "REIT - Diversified": "Real Estate",
    "REIT - Healthcare Facilities": "Real Estate",
    "REIT - Hotel & Motel": "Real Estate",
    "REIT - Industrial": "Real Estate",
    "REIT - Mortgage": "Real Estate",
    "REIT - Office": "Real Estate",
    "REIT - Residential": "Real Estate",
    "REIT - Retail": "Real Estate",
    "REIT - Specialty": "Real Estate",
    "Real Estate Services": "Real Estate",
    "Real Estate - Development": "Real Estate",
    "Real Estate - Diversified": "Real Estate",
    "Aluminum": "Basic Materials",
    "Building Materials": "Basic Materials",
    "Chemicals": "Basic Materials",
    "Specialty Chemicals": "Basic Materials",
    "Agricultural Inputs": "Basic Materials",
    "Coking Coal": "Basic Materials",
    "Copper": "Basic Materials",
    "Gold": "Basic Materials",
    "Lumber & Wood Production": "Basic Materials",
    "Other Industrial Metals & Mining": "Basic Materials",
    "Other Precious Metals & Mining": "Basic Materials",
    "Paper & Paper Products": "Basic Materials",
    "Silver": "Basic Materials",
    "Steel": "Basic Materials",
    "Industrial Metals & Mining": "Basic Materials",
}

# FMP sector_price_earning_ratio 可能返回的别名 → 统一名
_SECTOR_ALIASES: Dict[str, str] = {
    "Health Care": "Healthcare",
    "Financials": "Financial Services",
    "Consumer Discretionary": "Consumer Cyclical",
    "Consumer Staples": "Consumer Defensive",
    "Materials": "Basic Materials",
}

# 一级板块固定排序（与 SECTOR_CN_MAP 保持一致）
_SECTOR_ORDER = [
    "Technology", "Healthcare", "Financial Services", "Consumer Cyclical",
    "Communication Services", "Industrials", "Consumer Defensive",
    "Energy", "Utilities", "Real Estate", "Basic Materials",
]


async def _fetch_pe_snapshot(
    client: httpx.AsyncClient,
    endpoint: str,
    name_field: str,
    dt: str,
) -> Dict[str, float]:
    """拉取单个日期的 PE 快照，返回 {name: pe}。"""
    try:
        resp = await client.get(
            f"{_FMP_V4_BASE}/{endpoint}",
            params={"date": dt, "exchange": "NYSE", "apikey": settings.FMP_API_KEY},
            timeout=20,
        )
        if resp.status_code != 200:
            logger.warning(
                "gics_pe_http_error",
                endpoint=endpoint, date=dt,
                status=resp.status_code, body=resp.text[:300],
            )
            return {}
        data = resp.json()
        if not isinstance(data, list):
            # 非 list 通常是 FMP 返回的错误/权限提示，记录以便诊断
            logger.warning(
                "gics_pe_non_list_response",
                endpoint=endpoint, date=dt,
                response_type=type(data).__name__,
                body=str(data)[:300],
            )
            return {}
        if not data:
            logger.warning("gics_pe_empty_list", endpoint=endpoint, date=dt)
            return {}
        result: Dict[str, float] = {}
        for rec in data:
            name = rec.get(name_field, "")
            # 兼容 FMP 不同版本字段名：pe / peRatio / pe_ratio
            pe_raw = rec.get("pe") or rec.get("peRatio") or rec.get("pe_ratio")
            if not name or pe_raw is None:
                continue
            try:
                pe_f = float(pe_raw)
                if pe_f > 0:
                    result[name] = round(pe_f, 2)
            except (TypeError, ValueError):
                pass
        return result
    except Exception as e:
        logger.warning("gics_pe_fetch_failed", endpoint=endpoint, date=dt, error=str(e))
        return {}


async def _fetch_all_pe(
    client: httpx.AsyncClient,
    endpoint: str,
    name_field: str,
    years: int = _YEARS,
) -> Dict[str, Dict[str, float]]:
    """批量拉取 years 年每季度末 PE，返回 {date: {name: pe}}。"""
    dates = _quarter_end_dates(years=years)
    date_to_pe: Dict[str, Dict[str, float]] = {}

    for i in range(0, len(dates), _BATCH_SIZE):
        batch = dates[i: i + _BATCH_SIZE]
        results = await asyncio.gather(
            *[_fetch_pe_snapshot(client, endpoint, name_field, dt) for dt in batch],
            return_exceptions=True,
        )
        for dt, recs in zip(batch, results):
            if isinstance(recs, Exception) or not recs:
                continue
            date_to_pe[dt] = recs  # type: ignore[assignment]

    logger.info("gics_pe_batch_done", endpoint=endpoint, dates_with_data=len(date_to_pe), total=len(dates))
    return date_to_pe


def _build_series(name: str, date_to_pe: Dict[str, Dict[str, float]]) -> List[Tuple[str, float]]:
    """提取单个名称的历史 PE 序列（降序）。"""
    series = []
    for dt, pe_map in date_to_pe.items():
        if name in pe_map:
            series.append((dt, pe_map[name]))
    return sorted(series, key=lambda x: x[0], reverse=True)


def _build_stats(series: List[Tuple[str, float]]) -> dict:
    """从 [(date, pe)] 列表计算统计指标。"""
    if not series:
        label, label_en = get_valuation_label(None)
        return dict(
            current_pe=None, hist_mean=None, hist_std=None,
            z_score=None, label=label, label_en=label_en,
            hist_pe=[], data_quarters=0,
        )
    all_pes = [pe for _, pe in series]
    current_pe = series[0][1]
    hist_mean = round(statistics.mean(all_pes), 4) if len(all_pes) >= 2 else None
    hist_std = round(statistics.stdev(all_pes), 4) if len(all_pes) >= 2 else None
    z_score = compute_z_score(all_pes, current_pe) if len(all_pes) >= 4 else None
    label, label_en = get_valuation_label(z_score)
    hist_pe = [{"date": d, "pe": pe} for d, pe in reversed(series)]
    return dict(
        current_pe=current_pe, hist_mean=hist_mean, hist_std=hist_std,
        z_score=z_score, label=label, label_en=label_en,
        hist_pe=hist_pe, data_quarters=len(series),
    )


async def compute_gics_valuations() -> GICSValuationResponse:
    """拉取 GICS 两层 PE 数据，构建带 z-score 的估值层级树。"""
    if not settings.FMP_API_KEY:
        logger.warning("gics_valuation_no_api_key")
        return GICSValuationResponse(as_of=str(date.today()), sectors=[])

    logger.info(
        "gics_valuation_start",
        api_key_suffix=settings.FMP_API_KEY[-4:] if len(settings.FMP_API_KEY) >= 4 else "***",
        years=_YEARS,
    )

    async with httpx.AsyncClient() as client:
        # 并行拉取一级板块 PE 和细粒度行业 PE
        sector_pe, industry_pe = await asyncio.gather(
            _fetch_all_pe(client, "sector_price_earning_ratio", "sector"),
            _fetch_all_pe(client, "industry_price_earning_ratio", "industry"),
        )  # FMP v4 付费端点，需 premium API key

    # 收集一级板块实际出现的名称（规范化别名）
    raw_sector_names: set = set()
    for pe_map in sector_pe.values():
        raw_sector_names.update(pe_map.keys())

    # 构建 sector 名称规范化映射（别名 → 标准名）
    def _norm_sector(name: str) -> str:
        return _SECTOR_ALIASES.get(name, name)

    # 规范化 sector_pe 数据：把别名统一
    norm_sector_pe: Dict[str, Dict[str, float]] = {}
    for dt, pe_map in sector_pe.items():
        norm_map: Dict[str, float] = {}
        for s, pe in pe_map.items():
            norm_map[_norm_sector(s)] = pe
        norm_sector_pe[dt] = norm_map

    # 对每个一级板块计算 z-score
    sector_results: Dict[str, SectorWithIndustries] = {}
    for sector in _SECTOR_ORDER:
        series = _build_series(sector, norm_sector_pe)
        stats = _build_stats(series)
        sector_cn = SECTOR_CN_MAP.get(sector, sector)
        sector_results[sector] = SectorWithIndustries(
            sector=sector,
            sector_cn=sector_cn,
            industries=[],
            **stats,
        )

    # 对每个细粒度行业计算 z-score，归入父 sector
    all_industries: set = set()
    for pe_map in industry_pe.values():
        all_industries.update(pe_map.keys())

    for industry in sorted(all_industries):
        parent_sector = INDUSTRY_TO_SECTOR.get(industry)
        if parent_sector not in sector_results:
            continue
        series = _build_series(industry, industry_pe)
        stats = _build_stats(series)
        industry_cn = INDUSTRY_CN_MAP.get(industry, industry)
        ind = IndustryValuation(
            industry=industry,
            industry_cn=industry_cn,
            **stats,
        )
        sector_results[parent_sector].industries.append(ind)

    # 行业按 z_score 升序（低估在前，None 排末尾）
    for sw in sector_results.values():
        sw.industries.sort(key=lambda x: (x.z_score is None, x.z_score or 0))

    sectors = [sector_results[s] for s in _SECTOR_ORDER if s in sector_results]
    as_of = _quarter_end_dates(years=1)[0] if _quarter_end_dates(years=1) else str(date.today())

    logger.info(
        "gics_valuations_done",
        sectors=len(sectors),
        industries=sum(len(s.industries) for s in sectors),
    )
    return GICSValuationResponse(as_of=as_of, sectors=sectors)
