"""ETF OHLCV 数据抓取与资金流计算（Financial Modeling Prep API + yfinance）。

此模块负责：
- 从 FMP API 和 yfinance 抓取 ETF 数据
- 构建热力图数据
- 获取 K 线数据

计算逻辑已拆分到 calculator.py，常量已拆分到 constants.py。
"""

import datetime
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

from .calculator import compute_clv, compute_flow, date_label, z_score_normalize
from .constants import (
    CANDLE_CALENDAR_DAYS,
    CHINESE_NAMES,
    ETF_LIBRARY,
    FMP_BASE_URL,
    RESAMPLE_RULE,
    TIMESERIES_MAP,
    TRACKED_ETFS,
)


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
        calendar_days = TIMESERIES_MAP.get(period, 31)
        from_date, to_date = _date_range(calendar_days)
    return f"{FMP_BASE_URL}/historical-price-eod/full?symbol={symbol}&from={from_date}&to={to_date}&apikey={api_key}"



def fetch_etf_flows(symbol: str, period: str) -> List[FlowDataPoint]:
    """抓取单只 ETF 的 OHLCV 历史数据并计算资金流指标（兼容旧接口）。"""
    url = _build_url(symbol, period)
    try:
        resp = httpx.get(
            url,
            timeout=15,
            proxy=settings.HTTP_PROXY or settings.HTTPS_PROXY or None,
        )
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
            threads=False,
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
            label = date_label(date_str, granularity)
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


def fetch_candles(symbol: str, granularity: str = "day") -> CandleResponse:
    """抓取单只 ETF K 线数据，按 granularity 聚合为日/周/月 K。"""
    calendar_days = CANDLE_CALENDAR_DAYS.get(granularity, 365)
    today = datetime.date.today()
    from_date = today - datetime.timedelta(days=calendar_days)

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
        # 多 ticker 下载时 columns 可能为 MultiIndex，取单层
        if hasattr(df.columns, "levels"):
            df = df.xs(symbol, axis=1, level=1) if symbol in df.columns.get_level_values(1) else df

        # 按粒度聚合
        rule = RESAMPLE_RULE.get(granularity)
        if rule:
            try:
                df = df.resample(rule).agg({
                    "Open": "first",
                    "High": "max",
                    "Low": "min",
                    "Close": "last",
                    "Volume": "sum",
                }).dropna(subset=["Open", "Close"])
            except Exception as e:
                logger.warning("candle_resample_failed", granularity=granularity, error=str(e))

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
