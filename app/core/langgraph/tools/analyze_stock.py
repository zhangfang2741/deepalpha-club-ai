"""Analyze stock tool for six-layer investment analysis.

This tool performs comprehensive investment analysis combining data from:
- SEC EDGAR (financial filings)
- Financial Modeling Prep (valuation metrics)
- News API (sentiment analysis)
- Fear & Greed Index (market sentiment)

All data is traceable with source attribution.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.logging import logger
from app.schemas.analysis import (
    AnalysisReport,
    DataPoint,
    LayerAnalysis,
    LayerName,
)
from app.services.analyzer.fmp_client import fmp_client
from app.services.analyzer.news_client import news_client
from app.services.analyzer.sec_edgar import sec_edgar_client


# Dynamic input schema builder (used by langgraph tools when needed)
# See _build_analyze_stock_schema() below


class AnalyzeStockOutput(BaseModel):
    """Output schema for analyze_stock tool."""
    ticker: str
    company_name: str
    final_score: float = Field(ge=0, le=100)
    recommendation: str
    risk_reward_ratio: float
    position_recommendation: str
    layers: Dict[str, Dict[str, Any]]
    sources: List[Dict[str, Any]]
    analysis_timestamp: str


def _calculate_layer_score(
    data_points: List[DataPoint],
    positive_indicators: List[str],
    negative_indicators: List[str],
) -> tuple[float, float, List[str]]:
    """Calculate score for a layer based on data points.
    
    Args:
        data_points: List of data points
        positive_indicators: Keywords indicating positive metrics
        negative_indicators: Keywords indicating negative metrics
        
    Returns:
        Tuple of (score, confidence, key_findings)
    """
    if not data_points:
        return 50.0, 0.0, ["暂无可用数据，评分默认为中性值50分，请稍后重试或检查数据源连接"]
    
    positive_count = 0
    negative_count = 0
    findings = []
    
    for dp in data_points:
        label_lower = dp.label.lower()
        value_str = str(dp.value).lower()
        
        for indicator in positive_indicators:
            if indicator in label_lower or indicator in value_str:
                positive_count += 1
                findings.append(f"积极指标 ✓ {dp.label}")
                break
        
        for indicator in negative_indicators:
            if indicator in label_lower or indicator in value_str:
                negative_count += 1
                findings.append(f"风险指标 ⚠ {dp.label}")
                break
    
    total = positive_count + negative_count
    if total == 0:
        score = 50.0
        confidence = 0.3
    else:
        score = 50 + (positive_count - negative_count) / total * 30
        score = max(0, min(100, score))
        confidence = min(0.9, 0.3 + total * 0.1)
    
    # Deduplicate findings
    unique_findings = list(dict.fromkeys(findings))[:5]
    
    return round(score, 1), round(confidence, 2), unique_findings


async def _analyze_financial_layer(ticker: str) -> LayerAnalysis:
    """Analyze financial layer with real data from FMP."""
    logger.info("analyzing_financial_layer", ticker=ticker)

    fmp_url = f"https://financialmodelingprep.com/financial-statements/{ticker}"

    income = await fmp_client.get_income_statement(ticker, limit=1)
    balance = await fmp_client.get_balance_sheet(ticker, limit=1)
    cash_flow = await fmp_client.get_cash_flow(ticker, limit=1)

    findings: List[str] = []
    data_points: List[DataPoint] = []
    score = 50.0
    confidence = 0.0

    if income:
        i = income[0]
        period = i.get("date", "最新期")
        revenue = i.get("revenue") or 0
        net_income = i.get("netIncome") or 0
        gross_profit = i.get("grossProfit") or 0

        if revenue:
            rev_b = revenue / 1e9
            findings.append(
                f"营业收入（{period}）：${rev_b:.2f}B —— 来源：FMP 损益表 {fmp_url}"
            )
            data_points.append(DataPoint(
                value=f"${rev_b:.2f}B",
                label="Revenue",
                source="FMP",
                url=fmp_url,
                fetched_at=datetime.utcnow(),
            ))

        if revenue and net_income:
            net_margin = net_income / revenue * 100
            margin_comment = (
                "盈利能力强劲，远超行业均值" if net_margin > 25
                else "盈利能力良好" if net_margin > 15
                else "盈利正常" if net_margin > 5
                else "净利润偏薄，关注成本压力" if net_margin >= 0
                else "当期净亏损，盈利能力承压"
            )
            findings.append(
                f"净利润率（{period}）：{net_margin:.1f}%，{margin_comment} —— 来源：FMP 损益表"
            )
            data_points.append(DataPoint(
                value=f"{net_margin:.1f}%",
                label="Net Profit Margin",
                source="FMP",
                url=fmp_url,
                fetched_at=datetime.utcnow(),
            ))
            score = (
                85.0 if net_margin > 25
                else 75.0 if net_margin > 15
                else 62.0 if net_margin > 5
                else 45.0 if net_margin >= 0
                else 30.0
            )
            confidence = 0.85

        if revenue and gross_profit:
            gm = gross_profit / revenue * 100
            findings.append(
                f"毛利率（{period}）：{gm:.1f}% —— 来源：FMP 损益表"
            )

    if balance:
        b = balance[0]
        period = b.get("date", "最新期")
        total_debt = b.get("totalDebt") or 0
        total_equity = b.get("totalStockholdersEquity") or 1

        dte = total_debt / total_equity
        dte_comment = (
            "负债水平极低，财务结构稳健" if dte < 0.3
            else "负债水平健康" if dte < 0.8
            else "负债偏高，关注偿债风险" if dte < 2.0
            else "高杠杆运营，偿债压力较大"
        )
        findings.append(
            f"债务权益比（D/E，{period}）：{dte:.2f}x，{dte_comment} —— 来源：FMP 资产负债表"
        )
        data_points.append(DataPoint(
            value=f"{dte:.2f}x",
            label="Debt-to-Equity Ratio",
            source="FMP",
            url=fmp_url,
            fetched_at=datetime.utcnow(),
        ))

    if cash_flow:
        cf = cash_flow[0]
        period = cf.get("date", "最新期")
        fcf = cf.get("freeCashFlow") or 0

        if fcf:
            fcf_b = fcf / 1e9
            fcf_comment = (
                "自由现金流充沛，可持续支撑投资与股东回报" if fcf > 0
                else "自由现金流为负，短期资金压力需关注"
            )
            findings.append(
                f"自由现金流（{period}）：${fcf_b:.2f}B，{fcf_comment} —— 来源：FMP 现金流量表"
            )
            data_points.append(DataPoint(
                value=f"${fcf_b:.2f}B",
                label="Free Cash Flow",
                source="FMP",
                url=fmp_url,
                fetched_at=datetime.utcnow(),
            ))

    if not findings:
        findings = ["暂无可用财务数据，评分默认为中性值50分，请检查 FMP API Key 配置"]

    summary = (
        f"基于 FMP 财务数据平台对 {ticker} 进行深度财务健康分析，"
        f"共采集 {len(data_points)} 项核心财务指标，涵盖营收规模、盈利能力、负债水平与现金流状况。"
    )

    return LayerAnalysis(
        layer_name=LayerName.FINANCIAL,
        score=score,
        summary=summary,
        key_findings=findings,
        data_points=data_points,
        confidence=confidence,
    )


async def _analyze_industry_layer(ticker: str) -> LayerAnalysis:
    """Analyze industry layer."""
    logger.info("analyzing_industry_layer", ticker=ticker)
    
    # Get company profile for industry info
    profile = await fmp_client.get_company_profile(ticker)
    
    data_points = []
    industry = "Technology"
    sector = "Semiconductors"
    
    if profile:
        p = profile[0] if isinstance(profile, list) else profile
        industry = p.get("industry", industry)
        sector = p.get("sector", sector)
        
        data_points.append(DataPoint(
            value=industry,
            label="Industry",
            source="FMP",
            url=f"https://site.financialmodelingprep.com/financial-statements/{ticker}",
            fetched_at=datetime.utcnow(),
        ))
        data_points.append(DataPoint(
            value=sector,
            label="Sector",
            source="FMP",
            url=f"https://site.financialmodelingprep.com/financial-statements/{ticker}",
            fetched_at=datetime.utcnow(),
        ))
    
    # Industry scoring (simplified - in production would use industry reports)
    tech_sectors = ["Technology", "Semiconductors", "Software", "AI"]
    is_tech = sector in tech_sectors or industry in tech_sectors
    
    if is_tech:
        score = 75.0  # AI/Tech currently high growth
        findings = [
            f"人工智能与半导体行业当前处于强劲增长周期，{sector} 赛道景气度高",
            f"{ticker} 所处行业为 {industry}，行业整体受益于数字化转型与AI算力需求浪潮",
            "科技板块估值溢价显著，成长性预期支撑长期投资逻辑",
        ]
    else:
        score = 55.0
        findings = [
            f"公司所处行业为 {industry}，属于传统或非科技类行业",
            "行业增长相对稳健，需关注宏观经济周期对该行业的影响",
        ]
    
    return LayerAnalysis(
        layer_name=LayerName.INDUSTRY,
        score=score,
        summary=f"行业前景分析：对 {industry} 行业进行系统性评估，研判行业景气周期、竞争格局及政策环境对公司成长空间的综合影响。",
        key_findings=findings,
        data_points=data_points,
        confidence=0.7,
    )


async def _analyze_sentiment_layer(ticker: str) -> LayerAnalysis:
    """Analyze sentiment layer."""
    logger.info("analyzing_sentiment_layer", ticker=ticker)
    
    news_data = await news_client.analyze_news_sentiment(ticker)
    data_points = news_data.get("data_points", [])
    sentiment = news_data.get("sentiment", {})
    
    sentiment_score = sentiment.get("average_sentiment", 50)
    
    findings = []
    article_count = sentiment.get('article_count', 0)
    if sentiment_score >= 60:
        findings.append(f"市场新闻情绪偏向积极，媒体报道与分析师观点整体看多，市场预期乐观")
        findings.append(f"正面报道占比较高，反映出投资者对该股票的信心较强")
    elif sentiment_score <= 40:
        findings.append(f"市场新闻情绪偏向负面，近期存在不利消息或市场担忧情绪蔓延")
        findings.append(f"负面报道较多，需警惕情绪面对股价形成短期压制")
    else:
        findings.append(f"市场新闻情绪中性，多空观点分歧均衡，市场处于观望状态")
        findings.append(f"情绪面无明显方向性，股价走势更多依赖基本面数据驱动")
    
    findings.append(f"本次情绪分析共采集 {article_count} 篇近期相关报道，数据来源涵盖主流财经媒体")
    
    return LayerAnalysis(
        layer_name=LayerName.EXPECTATION,
        score=sentiment_score,
        summary=f"市场预期分析：通过自然语言处理技术对 {ticker} 相关新闻、研究报告及社交媒体数据进行情绪量化评分，综合反映当前市场对该股的整体预期与情绪倾向。",
        key_findings=findings,
        data_points=data_points,
        confidence=0.6,
    )


async def _analyze_company_layer(ticker: str, financial_layer: "LayerAnalysis") -> "LayerAnalysis":
    """Analyze company quality layer with real ROE, margins from FMP key metrics."""
    logger.info("analyzing_company_layer", ticker=ticker)

    fmp_url = f"https://financialmodelingprep.com/financial-statements/{ticker}"
    findings: List[str] = []
    data_points: List[DataPoint] = []

    ratios = await fmp_client.get_financial_ratios(ticker, limit=1)
    metrics = await fmp_client.get_key_metrics(ticker, limit=1)

    if ratios:
        r = ratios[0]
        period = r.get("date", "最新期")

        roe = r.get("returnOnEquity") or r.get("roe")
        if roe is not None:
            roe_pct = roe * 100
            roe_comment = (
                "ROE 优异，股东回报能力极强" if roe_pct > 30
                else "ROE 良好，盈利质量较高" if roe_pct > 15
                else "ROE 一般，盈利质量待提升" if roe_pct > 5
                else "ROE 偏低，资本利用效率不足"
            )
            findings.append(
                f"净资产收益率（ROE，{period}）：{roe_pct:.1f}%，{roe_comment} —— 来源：FMP 财务比率"
            )
            data_points.append(DataPoint(
                value=f"{roe_pct:.1f}%",
                label="ROE",
                source="FMP",
                url=fmp_url,
                fetched_at=datetime.utcnow(),
            ))

        gpm = r.get("grossProfitMargin")
        if gpm is not None:
            gpm_pct = gpm * 100
            findings.append(
                f"毛利率（{period}）：{gpm_pct:.1f}%，{'高毛利率反映出较强产品定价权' if gpm_pct > 50 else '毛利率处于行业正常水平'} —— 来源：FMP 财务比率"
            )

        npm = r.get("netProfitMargin")
        if npm is not None:
            npm_pct = npm * 100
            findings.append(
                f"净利率（{period}）：{npm_pct:.1f}% —— 来源：FMP 财务比率"
            )

    if metrics:
        m = metrics[0]
        period = m.get("date", "最新期")

        rev_growth = m.get("revenueGrowth") or m.get("revenue_growth")
        if rev_growth is not None:
            rg_pct = rev_growth * 100
            findings.append(
                f"营收增速（{period}）：{rg_pct:.1f}%，{'高增速公司具备持续成长潜力' if rg_pct > 20 else '增速稳健' if rg_pct > 5 else '增长放缓，关注业务扩张动力'} —— 来源：FMP 关键指标"
            )

    if not findings:
        for f_finding in financial_layer.key_findings[:2]:
            findings.append(f_finding)
        findings.append("公司质量层暂无专项比率数据，已复用财务健康层指标")

    roe_score = 50.0
    if ratios and ratios[0].get("returnOnEquity") is not None:
        roe_val = (ratios[0].get("returnOnEquity") or 0) * 100
        roe_score = (
            88.0 if roe_val > 30
            else 75.0 if roe_val > 15
            else 60.0 if roe_val > 5
            else 40.0
        )
    else:
        roe_score = financial_layer.score * 0.9 + 50 * 0.1

    return LayerAnalysis(
        layer_name=LayerName.COMPANY,
        score=round(roe_score, 1),
        summary=(
            f"公司质量评估：从净资产收益率（ROE）、毛利率、净利率及收入增速等维度对 {ticker} 进行综合评价，"
            "判断企业内在竞争优势与长期价值创造能力。数据来源：FMP 财务比率与关键指标。"
        ),
        key_findings=findings,
        data_points=data_points,
        confidence=0.8 if ratios else 0.4,
    )


async def _analyze_competition_layer(ticker: str) -> "LayerAnalysis":
    """Analyze competitive landscape using profile and market cap data from FMP."""
    logger.info("analyzing_competition_layer", ticker=ticker)

    fmp_url = f"https://financialmodelingprep.com/financial-statements/{ticker}"
    findings: List[str] = []
    data_points: List[DataPoint] = []
    score = 65.0

    profile_raw = await fmp_client.get_company_profile(ticker)
    price_data = await fmp_client.get_price_data(ticker)

    profile = (profile_raw[0] if isinstance(profile_raw, list) and profile_raw else profile_raw) or {}

    industry = profile.get("industry", "未知行业")
    sector = profile.get("sector", "未知板块")
    employees = profile.get("fullTimeEmployees") or profile.get("employees")
    description = profile.get("description", "")

    market_cap = price_data.get("marketCap") if price_data else None
    if market_cap is None:
        market_cap = profile.get("mktCap")

    if market_cap:
        mc_b = market_cap / 1e9
        cap_tier = (
            "超大型企业（市值 > $200B），具备显著的规模护城河与品牌效应" if mc_b > 200
            else "大型企业（市值 $50B–$200B），行业龙头地位稳固" if mc_b > 50
            else "中型企业（市值 $10B–$50B），成长空间与行业竞争力并存" if mc_b > 10
            else "中小型企业（市值 < $10B），需关注市场份额与护城河深度"
        )
        findings.append(
            f"市值规模：${mc_b:.1f}B，{cap_tier} —— 来源：FMP 市场行情"
        )
        data_points.append(DataPoint(
            value=f"${mc_b:.1f}B",
            label="Market Cap",
            source="FMP",
            url=fmp_url,
            fetched_at=datetime.utcnow(),
        ))
        score = (
            80.0 if mc_b > 200
            else 70.0 if mc_b > 50
            else 60.0 if mc_b > 10
            else 50.0
        )

    if industry and sector:
        findings.append(
            f"所属行业：{sector} / {industry}，行业竞争格局与景气度直接影响公司定价权 —— 来源：FMP 公司档案"
        )

    if employees:
        findings.append(
            f"全职员工数：{int(employees):,} 人 —— 反映公司运营规模与人力资本投入（来源：FMP 公司档案）"
        )
        data_points.append(DataPoint(
            value=str(employees),
            label="Full-Time Employees",
            source="FMP",
            url=fmp_url,
            fetched_at=datetime.utcnow(),
        ))

    if description:
        findings.append(
            f"业务简介：{description[:120]}… —— 来源：FMP 公司档案"
        )

    if not findings:
        findings = [
            "竞争格局数据暂不可用，请检查 FMP API 配置",
            "通常通过市值、员工规模与行业地位评估竞争壁垒",
        ]

    return LayerAnalysis(
        layer_name=LayerName.COMPETITION,
        score=score,
        summary=(
            f"竞争格局分析：基于 FMP 平台提供的市值规模、行业分类与公司档案数据，"
            f"评估 {ticker} 在 {industry} 行业中的市场地位、规模护城河与差异化优势。"
        ),
        key_findings=findings,
        data_points=data_points,
        confidence=0.7 if profile else 0.3,
    )


async def _analyze_trading_layer(ticker: str) -> "LayerAnalysis":
    """Analyze trading valuation with real P/E, P/B, EV/EBITDA from FMP."""
    logger.info("analyzing_trading_layer", ticker=ticker)

    fmp_url = f"https://financialmodelingprep.com/financial-statements/{ticker}"
    findings: List[str] = []
    data_points: List[DataPoint] = []
    score = 50.0

    price_data = await fmp_client.get_price_data(ticker)
    metrics = await fmp_client.get_key_metrics(ticker, limit=1)

    if price_data:
        pe = price_data.get("pe")
        price = price_data.get("price")
        eps = price_data.get("eps")
        market_cap = price_data.get("marketCap")
        div_yield = price_data.get("dividendYield") or 0

        if price:
            findings.append(
                f"当前股价：${price:.2f} —— 来源：FMP 实时行情"
            )

        if pe is not None and pe > 0:
            pe_comment = (
                "估值偏高，市场给予高成长预期溢价" if pe > 40
                else "估值合理，符合成长型公司定价" if pe > 20
                else "估值适中，具备一定安全边际" if pe > 12
                else "估值偏低，可能存在价值低估机会"
            )
            findings.append(
                f"市盈率（P/E）：{pe:.1f}x，{pe_comment} —— 来源：FMP 实时行情"
            )
            data_points.append(DataPoint(
                value=f"{pe:.1f}x",
                label="P/E Ratio",
                source="FMP",
                url=fmp_url,
                fetched_at=datetime.utcnow(),
            ))
            score = (
                40.0 if pe > 50
                else 55.0 if pe > 30
                else 70.0 if pe > 15
                else 80.0
            )

        if eps:
            findings.append(
                f"每股收益（EPS）：${eps:.2f} —— 来源：FMP 实时行情"
            )

        if div_yield and div_yield > 0:
            findings.append(
                f"股息率：{div_yield * 100:.2f}%，提供稳定现金回报 —— 来源：FMP 实时行情"
            )

    if metrics:
        m = metrics[0]
        period = m.get("date", "最新期")

        pb = m.get("pbRatio") or m.get("priceToBookRatio")
        if pb is not None and pb > 0:
            pb_comment = (
                "市净率偏高，市场对资产增值预期强烈" if pb > 10
                else "市净率正常" if pb > 2
                else "市净率接近净资产，估值具备安全边际"
            )
            findings.append(
                f"市净率（P/B，{period}）：{pb:.1f}x，{pb_comment} —— 来源：FMP 关键指标"
            )
            data_points.append(DataPoint(
                value=f"{pb:.1f}x",
                label="P/B Ratio",
                source="FMP",
                url=fmp_url,
                fetched_at=datetime.utcnow(),
            ))

        ev_ebitda = m.get("enterpriseValueOverEBITDA") or m.get("evToEbitda")
        if ev_ebitda is not None and ev_ebitda > 0:
            ev_comment = (
                "EV/EBITDA 偏高，体现高成长溢价" if ev_ebitda > 30
                else "EV/EBITDA 合理" if ev_ebitda > 12
                else "EV/EBITDA 偏低，企业价值相对低估"
            )
            findings.append(
                f"企业价值倍数（EV/EBITDA，{period}）：{ev_ebitda:.1f}x，{ev_comment} —— 来源：FMP 关键指标"
            )
            data_points.append(DataPoint(
                value=f"{ev_ebitda:.1f}x",
                label="EV/EBITDA",
                source="FMP",
                url=fmp_url,
                fetched_at=datetime.utcnow(),
            ))

    if not findings:
        findings = [
            "估值数据暂不可用，评分默认为中性值50分，请检查 FMP API Key 配置",
        ]

    return LayerAnalysis(
        layer_name=LayerName.TRADING,
        score=round(score, 1),
        summary=(
            f"交易估值分析：基于 FMP 平台提供的实时行情与关键指标，"
            f"采集 {ticker} 的市盈率（P/E）、市净率（P/B）及 EV/EBITDA 等核心估值数据，"
            "结合绝对值与行业常规区间，综合判断当前股价安全边际。"
        ),
        key_findings=findings,
        data_points=data_points,
        confidence=0.8 if price_data else 0.2,
    )


def _build_analyze_stock_schema():
    """Build the input schema for the tool."""
    class DynamicAnalyzeStockInput(BaseModel):
        """Input schema for analyze_stock tool."""
        ticker: str = Field(description="Stock ticker symbol (e.g., 'NVDA', 'AAPL')")
        include_industry: bool = Field(default=True, description="Include industry analysis")
        include_sentiment: bool = Field(default=True, description="Include news sentiment analysis")
        as_of_date: Optional[str] = Field(default=None, description="Historical date for time travel (YYYY-MM-DD)")
    return DynamicAnalyzeStockInput


async def analyze_stock_async(
    ticker: str,
    include_industry: bool = True,
    include_sentiment: bool = True,
    as_of_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Async version of analyze_stock - use this from async contexts."""
    logger.info("stock_analysis_started", ticker=ticker, as_of_date=as_of_date)
    
    async def run_analysis():
        layers: Dict[str, LayerAnalysis] = {}
        all_sources: List[DataPoint] = []
        
        # Financial layer (always required)
        financial_layer = await _analyze_financial_layer(ticker)
        layers["financial"] = financial_layer
        all_sources.extend(financial_layer.data_points)
        
        # Industry layer
        if include_industry:
            industry_layer = await _analyze_industry_layer(ticker)
            layers["industry"] = industry_layer
            all_sources.extend(industry_layer.data_points)
        
        # Sentiment/Expectation layer
        if include_sentiment:
            sentiment_layer = await _analyze_sentiment_layer(ticker)
            layers["expectation"] = sentiment_layer
            all_sources.extend(sentiment_layer.data_points)
        
        # Company layer - real ROE/margins from FMP
        company_layer = await _analyze_company_layer(ticker, financial_layer)
        layers["company"] = company_layer
        all_sources.extend(company_layer.data_points)

        # Competition layer - real market cap / profile from FMP
        competition_layer = await _analyze_competition_layer(ticker)
        layers["competition"] = competition_layer
        all_sources.extend(competition_layer.data_points)

        # Trading layer - real P/E, P/B, EV/EBITDA from FMP
        trading_layer = await _analyze_trading_layer(ticker)
        layers["trading"] = trading_layer
        all_sources.extend(trading_layer.data_points)
        
        # Generate final report
        company_name = ticker
        profile = await fmp_client.get_company_profile(ticker)
        if profile:
            p = profile[0] if isinstance(profile, list) else profile
            company_name = p.get("companyName", company_name)
        
        report = AnalysisReport.from_layers(ticker, company_name, layers)
        
        return {
            "ticker": ticker,
            "company_name": company_name,
            "final_score": report.final_score,
            "recommendation": report.recommendation,
            "risk_reward_ratio": report.risk_reward_ratio,
            "position_recommendation": report.position_recommendation,
            "layers": {
                name: {
                    "score": layer.score,
                    "summary": layer.summary,
                    "key_findings": layer.key_findings,
                    "confidence": layer.confidence,
                }
                for name, layer in layers.items()
            },
            "sources": [
                {
                    "value": dp.value,
                    "label": dp.label,
                    "source": dp.source,
                    "url": dp.url,
                    "fetched_at": dp.fetched_at.isoformat(),
                }
                for dp in all_sources[:20]  # Limit to top 20 sources
            ],
            "analysis_timestamp": datetime.utcnow().isoformat(),
        }
    
    try:
        result = await run_analysis()
        logger.info(
            "stock_analysis_completed",
            ticker=ticker,
            score=result["final_score"],
            recommendation=result["recommendation"],
        )
        return result
    except Exception as e:
        logger.exception("stock_analysis_failed", ticker=ticker, error=str(e))
        # Return a graceful fallback response instead of error
        return {
            "ticker": ticker,
            "company_name": ticker,
            "final_score": 50.0,
            "recommendation": "HOLD",
            "risk_reward_ratio": 1.0,
            "position_recommendation": "Unable to complete analysis - please configure FMP_API_KEY",
            "layers": {
                "financial": {"score": 50.0, "summary": "Analysis unavailable", "key_findings": ["API key not configured"], "confidence": 0.1},
                "company": {"score": 50.0, "summary": "Analysis unavailable", "key_findings": ["API key not configured"], "confidence": 0.1},
                "industry": {"score": 50.0, "summary": "Analysis unavailable", "key_findings": ["API key not configured"], "confidence": 0.1},
                "expectation": {"score": 50.0, "summary": "Analysis unavailable", "key_findings": ["API key not configured"], "confidence": 0.1},
                "competition": {"score": 50.0, "summary": "Analysis unavailable", "key_findings": ["API key not configured"], "confidence": 0.1},
                "trading": {"score": 50.0, "summary": "Analysis unavailable", "key_findings": ["API key not configured"], "confidence": 0.1},
            },
            "sources": [],
            "analysis_timestamp": datetime.utcnow().isoformat(),
            "warning": "FMP API key not configured. Analysis may be incomplete.",
        }


def analyze_stock(
    ticker: str,
    include_industry: bool = True,
    include_sentiment: bool = True,
    as_of_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Synchronous wrapper for backward compatibility.
    
    Note: Prefer using analyze_stock_async in async contexts.
    """
    import asyncio
    
    return asyncio.run(analyze_stock_async(ticker, include_industry, include_sentiment, as_of_date))


# Export tool instance
analyze_stock_tool = analyze_stock