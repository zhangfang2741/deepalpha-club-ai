"""机构资金信号常量：维度元数据、权重与打分阈值。"""

# 维度元数据（key -> 中文名 + 核心问题），顺序即机构决策链顺序
DIMENSION_META = {
    "expectation": ("预期", "分析师是不是开始重新定价未来？"),
    "positioning": ("仓位", "资金是不是已经开始下注？"),
    "participation": ("参与度", "其他资金开始跟了吗？"),
    "fundamental": ("基本面", "企业经营有没有真正改善？"),
    "confirmation": ("确认", "长期资金确认了吗？"),
}

# 买入视角元数据：把「偏多状态」按买入价值排成早→晚时间轴
# key -> (买入排序 rank[1=最佳入场], 时机 timing, 优势 edge, 买入逻辑 thesis)
STATE_BUY_META = {
    "smart_money": (1, "启动前", "赔率最好",
                    "期权端资金已下注、价格还没动——买在启动前，风险回报最好"),
    "institution_accumulation": (2, "早中段", "胜率最高",
                                 "预期+期权+现货三层齐发，多维印证、假信号最少"),
    "fundamental_turn": (3, "中段", "最扛跌",
                         "营收超预期+连续兑现，有真实业绩兜底，适合拿得久"),
    "expectation_upgrade": (4, "中段", "中长期",
                            "卖方一致上修，趋势型机会，但尚无资金/业绩验证"),
    "breakout_confirmation": (5, "偏晚", "追涨",
                              "放量突破、价格已启动，属于追涨，注意回撤"),
}
# 阶梯完整顺序（用于产品展示，含未触发的灰位）
BUY_LADDER_ORDER = ["smart_money", "institution_accumulation", "fundamental_turn",
                    "expectation_upgrade", "breakout_confirmation"]
# 状态 key -> (emoji, 中文名)，供阶梯灰位展示（与 states.py 保持一致）
STATE_LABELS = {
    "smart_money": ("💰", "聪明钱"),
    "institution_accumulation": ("🔥", "机构建仓"),
    "fundamental_turn": ("🌱", "基本面改善"),
    "expectation_upgrade": ("📈", "预期上修"),
    "breakout_confirmation": ("🚀", "趋势确认"),
}
# 状态 key -> 触发逻辑（人话版判定规则，供产品展示；与 states.py 条件一一对应）
STATE_LOGIC = {
    "expectation_upgrade": "目标价环比上调 且 评级共识环比转多",
    "breakout_confirmation": "现货放量(≥1.5x) 且 收盘突破 20 日高 且 预期分 ≥ 55",
    "institution_accumulation": "预期分 ≥ 55 且 Call 资金流看涨 且 IV 抬升（放量为可选加分，非门槛）",
    "smart_money": "预期分 ≥ 55 且 Call 资金流看涨 且 IV 抬升 且 价格尚未突破",
    "event_trading": "Call 资金流看涨 且 IV 抬升，但 预期分 < 55（缺乏基本面背书 → 投机）",
    "fundamental_turn": "营收超预期 且 连续 Beat（目标价上调为可选确认，非门槛）",
    "distribution": "评级共识下调 且（看跌压力 或 内部人集中减持）",
    "neutral": "五维均未形成显著机构资金组合信号",
}

# 综合分权重（未实现的维度按 unavailable 处理，权重动态归一化）
DIMENSION_WEIGHTS = {
    "expectation": 0.30,
    "positioning": 0.25,
    "participation": 0.20,
    "fundamental": 0.15,
    "confirmation": 0.10,
}

# ── Participation 阈值 ──────────────────────────────────────────────────────
RELVOL_STRONG = 2.0      # 相对成交量 ≥ 2.0 视为显著放量
RELVOL_ELEVATED = 1.5
RELVOL_MILD = 1.2
RELVOL_QUIET = 0.8       # < 0.8 视为缩量
GAP_PCT = 2.0            # 跳空阈值（%）
VOLUME_LOOKBACK = 20     # 相对成交量与突破的回看窗口（交易日）

# ── Expectation 阈值 ────────────────────────────────────────────────────────
TP_STRONG_PCT = 5.0      # 目标价环比涨幅 ≥ 5% 视为强上调
TP_MILD_PCT = 1.0
MIN_ANALYST_COUNT = 2    # 目标价样本数下限，低于此不采信
BUY_RATIO_MAJORITY = 0.6  # 买入评级占比 ≥ 0.6 视为共识偏多

# ── Positioning 阈值（yfinance 期权快照）────────────────────────────────────
# 快照可算实的量：Put/Call 比、Call 量/仓比、ATM IV 水平。
# 真正的 OI 变化 / IV Rank 需每日快照库（后续基建）。
PCR_CALL_HEAVY = 0.7     # Put/Call 成交量比 ≤ 0.7 视为显著看涨下注
PCR_MILD_CALL = 0.9
PCR_PUT_HEAVY = 1.3      # ≥ 1.3 视为看跌/避险主导
CALL_VOL_OI_FRESH = 0.4  # Call 当日成交量 / Call OI ≥ 0.4 视为新增下注活跃
IV_ELEVATED = 0.60       # ATM 年化 IV ≥ 60% 视为偏高（事件预期）
IV_MILD = 0.40
OPTION_EXPIRY_MAX_DAYS = 45  # 只聚合 45 天内的近月合约
OPTION_EXPIRY_MIN_COUNT = 2  # 至少聚合最近 2 个到期日

# ── Fundamental 阈值（FMP earnings-calendar）────────────────────────────────
EARNINGS_LOOKBACK_QUARTERS = 4   # 看最近 4 个财季的兑现历史
EARNINGS_WINDOW_DAYS = 21        # 距下次财报 ≤ 21 天视为资金布局窗口

# ── Confirmation 阈值（FMP insider-trading/statistics）──────────────────────
INSIDER_LOOKBACK_QUARTERS = 2    # 聚合最近 2 个季度的内部人交易
INSIDER_ACCUM_RATIO = 1.2        # acquiredDisposedRatio ≥ 1.2 视为净增持
INSIDER_DISTRIB_RATIO = 0.3      # ≤ 0.3 且卖出笔数多 视为集中减持
INSIDER_DISTRIB_SALES = 10       # 集中减持的卖出笔数下限

# ── 榜单扫描 universe ────────────────────────────────────────────────────────
# universe 动态取自 FMP S&P 500 成分股；拉取失败时降级到下面的 fallback 列表。
# 扫描阶段只用 4 个 FMP 快接口（跳过期权），排名后由用户点进详情页跑完整五维。
# 扫描在后台任务里跑（stale-while-revalidate），不阻塞请求，故可覆盖全量成分股。
# 标普 500 兜底：广谱，含金融/医疗/工业/能源（与纳指兜底明显不同）
SP500_FALLBACK = [
    "AAPL", "MSFT", "NVDA", "AVGO", "AMD", "QCOM", "TXN", "MU", "INTC", "ARM",
    "GOOGL", "META", "AMZN", "NFLX", "CRM", "ORCL", "ADBE", "NOW", "PLTR", "SNOW",
    "TSLA", "COST", "NKE", "SBUX", "MCD", "HD",
    "JPM", "BAC", "GS", "V", "MA",              # 金融（QQQ 没有）
    "LLY", "UNH", "JNJ", "ABBV", "MRK",         # 医疗（多为 NYSE）
    "CAT", "BA", "GE", "XOM", "CVX",            # 工业/能源（QQQ 没有）
]
# 纳指 100 / QQQ 兜底：纯 Nasdaq 科技成长，不含金融/能源/工业（QQQ 本就没有）
NASDAQ100_FALLBACK = [
    "AAPL", "MSFT", "NVDA", "AVGO", "GOOGL", "AMZN", "META", "TSLA", "NFLX", "COST",
    "AMD", "QCOM", "TXN", "MU", "INTC", "AMAT", "LRCX", "KLAC", "MRVL", "ADI", "ASML", "ARM",
    "ADBE", "INTU", "PANW", "CRWD", "CDNS", "SNPS", "FTNT",
    "PEP", "SBUX", "MDLZ", "BKNG", "MELI", "PDD", "ABNB", "MAR", "ORLY", "LULU", "MNST",
    "AMGN", "GILD", "REGN", "VRTX", "ISRG", "DXCM",   # Nasdaq 医疗
    "CSCO", "CMCSA", "TMUS", "ADP", "HON", "PYPL",
]
SCAN_CONCURRENCY = 20            # 扫描并发上限（后台任务）
SCAN_TOP_N = 30                  # 榜单返回条数
SCAN_FRESH_SECONDS = 21600       # 缓存新鲜期 6h：超过则后台刷新（仍先返回旧数据）
# 两段式增强：4 维排名后，对排名靠前的 K 支补抓期权，使 🔥建仓/💰聪明钱 能上榜
ENRICH_TOP_K = 25               # 补抓期权的候选数（只对 top-K，避免扫全量期权）
ENRICH_CONCURRENCY = 8          # 期权补抓并发（yfinance 较慢）
