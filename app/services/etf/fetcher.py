"""ETF OHLCV 数据抓取与资金流计算（Financial Modeling Prep API）。

资金流计算：
  CLV = (2×adjClose - high - low) / (high - low + 1e-9)
  Flow = CLV × adjClose × volume
  Intensity = Z-score(Flow)  跨全部 ETF × 全部交易日标准化
"""

import datetime
import math
from typing import Dict, List, Optional, Tuple

import httpx
import yfinance as yf

from app.core.config import settings
from app.core.logging import logger
from app.schemas.etf import (
    Candle,
    CandleResponse,
    ETFSummary,
    FlowDataPoint,
    HeatmapCell,
    HeatmapETFRow,
    HeatmapResponse,
    HeatmapSectorGroup,
)

# ── ETF 数据集 ─────────────────────────────────────────────────────────────────

CHINESE_NAMES: Dict[str, str] = {
    "XLK": "科技行业精选指数ETF-SPDR",
    "SOXX": "iShares半导体指数ETF",
    "AIQ": "Global X人工智能与科技ETF",
    "SKYY": "First Trust云计算指数ETF",
    "QTUM": "Defiance量子计算与机器学习ETF",
    "BUG": "Global X网络安全指数ETF",
    "IGV": "iShares扩张科技软件行业ETF",
    "XLV": "医疗保健行业精选指数ETF-SPDR",
    "XHE": "SPDR标普健康医疗设备ETF",
    "IHF": "iShares美国医疗保健提供商ETF",
    "XBI": "SPDR标普生物技术ETF",
    "PJP": "Invesco动力制药ETF",
    "XLF": "金融行业精选指数ETF-SPDR",
    "KBE": "SPDR标普银行指数ETF",
    "IYG": "iShares美国金融服务ETF",
    "KIE": "SPDR标普保险ETF",
    "BLOK": "Amplify转型数据共享ETF(区块链)",
    "KCE": "SPDR标普资本Market ETF",
    "REM": "iShares抵押贷款地产投资信托ETF",
    "XLY": "可选消费行业精选指数ETF-SPDR",
    "CARZ": "First Trust纳斯达克全球汽车指数ETF",
    "XRT": "SPDR标普零售业ETF",
    "XHB": "SPDR标普家居建设ETF",
    "PEJ": "Invesco休闲娱乐ETF",
    "XLP": "必需消费行业精选指数ETF-SPDR",
    "PBJ": "Invesco动力食品饮料ETF",
    "MOO": "VanEck全球农产品ETF",
    "XLI": "工业行业精选指数ETF-SPDR",
    "ITA": "iShares美国航空航天与国防ETF",
    "PKB": "Invesco动力住宅建设ETF",
    "PAVE": "Global X美国基础设施发展ETF",
    "IYT": "iShares交通运输ETF",
    "JETS": "U.S. Global Jets航空业ETF",
    "BOAT": "SonicShares全球航运ETF",
    "IFRA": "iShares美国基础设施ETF",
    "UFO": "Procure太空ETF",
    "SHLD": "Strive美国国防与航空航天ETF",
    "XLE": "能源行业精选指数ETF-SPDR",
    "IEZ": "iShares美国石油设备与服务ETF",
    "XOP": "SPDR标普石油天然气开采ETF",
    "FAN": "First Trust全球风能ETF",
    "TAN": "Invesco太阳能ETF",
    "NLR": "VanEck铀及核能ETF",
    "XLB": "原材料行业精选指数ETF-SPDR",
    "XME": "SPDR标普金属与采矿ETF",
    "WOOD": "iShares全球林业ETF",
    "COPX": "Global X铜矿股ETF",
    "GLD": "SPDR黄金ETF",
    "GLTR": "Aberdeen标准实物贵金属篮子ETF",
    "SLV": "iShares白银ETF",
    "SLX": "VanEck矢量钢铁ETF",
    "BATT": "Amplify锂电池及关键材料ETF",
    "XLC": "通信服务行业精选指数ETF-SPDR",
    "IYZ": "iShares美国电信ETF",
    "PNQI": "Invesco纳斯达克互联网ETF",
    "XLRE": "房地产行业精选指数ETF-SPDR",
    "INDS": "Pacer工业地产ETF",
    "REZ": "iShares住宅与多户家庭地产投资信托ETF",
    "SRVR": "Pacer数据基础设施与房地产ETF",
    "XLU": "公用事业行业精选指数ETF-SPDR",
    "ICLN": "iShares全球清洁能源ETF",
    "PHO": "Invesco水资源ETF",
    "GRID": "First Trust纳斯达克智能电网基础设施ETF",
    "QQQ": "Invesco纳斯达克100指数ETF",
    "SPY": "SPDR标普500指数ETF",
    "TLT": "iShares 20年期以上美国国债ETF",
    "EEM": "iShares MSCI新兴市场ETF",
    "VEA": "Vanguard FTSE发达市场ETF",
    "FXI": "iShares中国大盘股ETF",
    "ARKK": "ARK创新ETF",
    "BITO": "ProShares比特币策略ETF",
    "MSOS": "AdvisorShares纯大麻ETF",
    "IPO": "Renaissance IPO ETF",
    "GBTC": "灰度比特币现货ETF",
    "ETHE": "灰度以太坊现货ETF",
}

ETF_LIBRARY: Dict[str, List[str]] = {
    "01 信息技术": ["XLK", "SOXX", "AIQ", "SKYY", "QTUM", "BUG", "IGV"],
    "02 医疗保健": ["XLV", "XHE", "IHF", "XBI", "PJP"],
    "03 金融": ["XLF", "KBE", "IYG", "KIE", "BLOK", "KCE", "REM"],
    "04 可选消费": ["XLY", "CARZ", "XRT", "XHB", "PEJ"],
    "05 必需消费": ["XLP", "PBJ", "MOO"],
    "06 工业": ["XLI", "ITA", "PKB", "PAVE", "IYT", "JETS", "BOAT", "IFRA", "UFO", "SHLD"],
    "07 能源": ["XLE", "IEZ", "XOP", "FAN", "TAN", "NLR"],
    "08 原材料": ["XLB", "PKB", "XME", "WOOD", "COPX", "GLD", "GLTR", "SLV", "SLX", "BATT"],
    "09 通信服务": ["XLC", "IYZ", "PNQI"],
    "10 房地产": ["XLRE", "INDS", "REZ", "SRVR"],
    "11 公用事业": ["XLU", "ICLN", "PHO", "GRID"],
    "12 全球宏观/另类": ["TLT", "EEM", "VEA", "FXI", "ARKK", "BITO", "MSOS", "IPO", "UFO", "GBTC", "ETHE"],
}

# 保留原有数据以兼容旧端点
TRACKED_ETFS: List[dict] = [
    {"symbol": sym, "name": CHINESE_NAMES.get(sym, sym), "category": sector}
    for sector, symbols in ETF_LIBRARY.items()
    for sym in symbols
]

_FMP_BASE = "https://financialmodelingprep.com/stable"

_TIMESERIES_MAP = {
    "1w": 7,
    "1mo": 31,
    "3mo": 92,
    "1y": 365,
}


# ── 计算函数 ──────────────────────────────────────────────────────────────────

def compute_clv(adj_close: float, high: float, low: float) -> float:
    """计算 Close Location Value。

    CLV = (2×adjClose - high - low) / (high - low + 1e-9)
    范围 [-1, 1]，1e-9 避免 high=low 时除零。
    """
    return (2 * adj_close - high - low) / (high - low + 1e-9)


def compute_flow(clv: float, adj_close: float, volume: int) -> float:
    """计算资金流原始值：Flow = CLV × adjClose × volume。"""
    return clv * adj_close * volume


def z_score_normalize(flows: List[float]) -> List[float]:
    """对 flows 列表做 Z-score 标准化。

    标准差为 0（常数序列）时返回全零列表。
    """
    if not flows:
        return []
    n = len(flows)
    mean = sum(flows) / n
    variance = sum((f - mean) ** 2 for f in flows) / n
    std = math.sqrt(variance)
    if std < 1e-9 or not math.isfinite(std):
        return [0.0] * n
    return [(f - mean) / std for f in flows]


# ── FMP 数据抓取 ──────────────────────────────────────────────────────────────

def _date_range(calendar_days: int) -> tuple[str, str]:
    """返回 (from_date, to_date) 字符串，to_date 为今天，from_date 为 calendar_days 天前。"""
    today = datetime.date.today()
    from_date = today - datetime.timedelta(days=calendar_days)
    return from_date.isoformat(), today.isoformat()


def _build_url(symbol: str, period: str) -> str:
    """构造 FMP historical-price-eod 请求 URL（兼容旧接口调用）。"""
    api_key = settings.FMP_API_KEY
    if period == "ytd":
        from_date = datetime.date(datetime.date.today().year, 1, 1).isoformat()
        to_date = datetime.date.today().isoformat()
    else:
        calendar_days = _TIMESERIES_MAP.get(period, 31)
        from_date, to_date = _date_range(calendar_days)
    return f"{_FMP_BASE}/historical-price-eod/full?symbol={symbol}&from={from_date}&to={to_date}&apikey={api_key}"



def fetch_etf_flows(symbol: str, period: str) -> List[FlowDataPoint]:
    """抓取单只 ETF 的 OHLCV 历史数据并计算资金流指标（兼容旧接口）。"""
    url = _build_url(symbol, period)
    try:
        resp = httpx.get(url, timeout=15)
        resp.raise_for_status()
        body = resp.json()
        historical = body if isinstance(body, list) else body.get("historical", [])
    except Exception as e:
        logger.exception("fmp_fetch_failed", symbol=symbol, period=period, error=str(e))
        return []

    if not historical:
        logger.warning("fmp_empty_data", symbol=symbol, period=period)
        return []

    historical = list(reversed(historical))
    points: List[FlowDataPoint] = []
    prev_close: Optional[float] = None

    for row in historical:
        close = float(row["close"])
        volume = int(row.get("volume") or 0)
        dollar_volume = close * volume
        return_pct = 0.0 if prev_close is None else (close - prev_close) / prev_close * 100

        points.append(
            FlowDataPoint(
                symbol=symbol,
                date=datetime.date.fromisoformat(row["date"]),
                close=round(close, 4),
                volume=volume,
                dollar_volume=round(dollar_volume, 2),
                return_pct=round(return_pct, 4),
            )
        )
        prev_close = close

    return points


def fetch_etf_list_summary(period: str) -> List[ETFSummary]:
    """抓取所有跟踪 ETF 在指定周期内的汇总数据（兼容旧接口）。"""
    summaries: List[ETFSummary] = []
    for etf_meta in TRACKED_ETFS:
        symbol = etf_meta["symbol"]
        flows = fetch_etf_flows(symbol, period)
        if not flows:
            continue
        current_price = flows[-1].close
        first_close = flows[0].close
        price_change_pct = (current_price - first_close) / first_close * 100 if first_close else 0.0
        period_dollar_volume = sum(p.dollar_volume for p in flows)
        summaries.append(
            ETFSummary(
                symbol=symbol,
                name=etf_meta["name"],
                category=etf_meta["category"],
                current_price=round(current_price, 4),
                price_change_pct=round(price_change_pct, 4),
                period_dollar_volume=round(period_dollar_volume, 2),
            )
        )
    return summaries


# ── 热力图数据构建 ────────────────────────────────────────────────────────────

def _date_label(date_str: str, granularity: str) -> str:
    """将 'YYYY-MM-DD' 转换为对应粒度的标签。"""
    d = datetime.date.fromisoformat(date_str)
    if granularity == "week":
        iso = d.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    if granularity == "month":
        return f"{d.year}-{d.month:02d}"
    return date_str  # day


def build_heatmap_data(granularity: str = "day", days: int = 30) -> HeatmapResponse:
    """构建热力图完整数据。

    步骤：
    1. 从 FMP 抓取全部 ETF 的 OHLCV
    2. 计算每日 CLV → Flow
    3. 跨全样本 Z-score 标准化得到 Intensity
    4. 按粒度聚合（day=直接使用，week/month=均值）
    5. 按 ETF_LIBRARY 分组，计算板块均值
    6. 返回 HeatmapResponse
    """
    # Step 1: 批量抓取所有 ETF 原始数据（去重，PKB/UFO 在多个板块出现）
    seen: set = set()
    unique_symbols = [
        sym
        for symbols in ETF_LIBRARY.values()
        for sym in symbols
        if not (sym in seen or seen.add(sym))  # type: ignore[func-returns-value]
    ]

    today = datetime.date.today()
    from_date = today - datetime.timedelta(days=days * 2)

    try:
        df = yf.download(
            unique_symbols,
            start=from_date.isoformat(),
            end=today.isoformat(),
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as e:
        logger.exception("yfinance_download_failed", error=str(e))
        df = None

    # raw_data[symbol] = [(date_str, close, high, low, volume), ...]（升序，最多 days 条）
    raw_data: Dict[str, List[Tuple[str, float, float, float, int]]] = {}

    if df is not None and not df.empty:
        for symbol in unique_symbols:
            try:
                # 多 symbol 时 columns 为 (field, symbol) 的 MultiIndex
                sym_close = df["Close"][symbol].dropna()
                sym_high = df["High"][symbol].dropna()
                sym_low = df["Low"][symbol].dropna()
                sym_volume = df["Volume"][symbol].dropna()
                # 取最近 days 个交易日
                sym_close = sym_close.tail(days)
                if sym_close.empty:
                    continue
                raw_data[symbol] = [
                    (
                        str(idx.date()),
                        float(sym_close.loc[idx]),
                        float(sym_high.loc[idx]) if idx in sym_high.index else 0.0,
                        float(sym_low.loc[idx]) if idx in sym_low.index else 0.0,
                        int(sym_volume.loc[idx]) if idx in sym_volume.index else 0,
                    )
                    for idx in sym_close.index
                ]
            except Exception as e:
                logger.warning("yfinance_parse_failed", symbol=symbol, error=str(e))
                continue

    # Step 2: 计算每个数据点的 CLV 和 Flow
    symbol_flows: Dict[str, Dict[str, float]] = {}
    all_flow_values: List[float] = []
    all_flow_keys: List[Tuple[str, str]] = []

    for symbol, rows in raw_data.items():
        symbol_flows[symbol] = {}
        for date_str, adj_close, high, low, volume in rows:
            clv = compute_clv(adj_close, high, low)
            flow = compute_flow(clv, adj_close, volume)
            symbol_flows[symbol][date_str] = flow
            all_flow_values.append(flow)
            all_flow_keys.append((symbol, date_str))

    # Step 3: 跨全样本 Z-score 标准化
    normalized = z_score_normalize(all_flow_values)
    symbol_intensity: Dict[str, Dict[str, float]] = {}
    for (symbol, date_str), intensity in zip(all_flow_keys, normalized):
        symbol_intensity.setdefault(symbol, {})[date_str] = intensity

    # Step 4: 按粒度聚合 → symbol_agg[symbol][label] = [intensity, ...]
    symbol_agg: Dict[str, Dict[str, List[float]]] = {}
    for symbol, date_intensity in symbol_intensity.items():
        symbol_agg[symbol] = {}
        for date_str, intensity in date_intensity.items():
            label = _date_label(date_str, granularity)
            symbol_agg[symbol].setdefault(label, []).append(intensity)

    # 有序 date_labels（所有 symbol 出现过的 label 并集，升序）
    all_labels: set = set()
    for sym_labels in symbol_agg.values():
        all_labels.update(sym_labels.keys())
    date_labels = sorted(all_labels)

    # Step 5: 按 ETF_LIBRARY 分组，构建 HeatmapSectorGroup
    sectors: List[HeatmapSectorGroup] = []

    for sector_name, sector_symbols in ETF_LIBRARY.items():
        etf_rows: List[HeatmapETFRow] = []

        for symbol in sector_symbols:
            if symbol not in symbol_agg:
                cells = [HeatmapCell(date=label, intensity=None) for label in date_labels]
            else:
                cells = [
                    HeatmapCell(
                        date=label,
                        intensity=round(
                            sum(symbol_agg[symbol][label]) / len(symbol_agg[symbol][label]),
                            4,
                        ) if symbol_agg[symbol].get(label) else None,
                    )
                    for label in date_labels
                ]
            etf_rows.append(
                HeatmapETFRow(
                    symbol=symbol,
                    name=CHINESE_NAMES.get(symbol, symbol),
                    cells=cells,
                )
            )

        # 板块均值：对每个 label，平均所有 ETF 的 intensity（跳过 None）
        avg_cells: List[HeatmapCell] = []
        for i, label in enumerate(date_labels):
            values = [
                row.cells[i].intensity
                for row in etf_rows
                if row.cells[i].intensity is not None
            ]
            avg_cells.append(
                HeatmapCell(
                    date=label,
                    intensity=round(sum(values) / len(values), 4) if values else None,
                )
            )

        sectors.append(
            HeatmapSectorGroup(
                sector=sector_name,
                avg_cells=avg_cells,
                etfs=etf_rows,
            )
        )

    return HeatmapResponse(
        granularity=granularity,
        days=days,
        date_labels=date_labels,
        sectors=sectors,
    )


# ── K 线数据抓取 ──────────────────────────────────────────────────────────────

def fetch_candles(symbol: str, days: int = 365) -> CandleResponse:
    """抓取单只 ETF 近 days 个交易日的 OHLCV K 线数据。"""
    today = datetime.date.today()
    from_date = today - datetime.timedelta(days=days)

    try:
        df = yf.download(
            symbol,
            start=from_date.isoformat(),
            end=today.isoformat(),
            auto_adjust=True,
            progress=False,
        )
    except Exception as e:
        logger.exception("yfinance_candle_download_failed", symbol=symbol, error=str(e))
        df = None

    candles: List[Candle] = []
    if df is not None and not df.empty:
        # 单 symbol 时 columns 为单层
        for idx, row in df.iterrows():
            try:
                candles.append(
                    Candle(
                        t=str(idx.date()),
                        o=round(float(row["Open"]), 4),
                        h=round(float(row["High"]), 4),
                        l=round(float(row["Low"]), 4),
                        c=round(float(row["Close"]), 4),
                        v=int(row["Volume"]),
                    )
                )
            except Exception:
                continue

    return CandleResponse(
        symbol=symbol,
        name=CHINESE_NAMES.get(symbol, symbol),
        candles=candles,
    )
