"""指标大白话：全称、日常语言释义、高低怎么看。

只做教育，不参与计算与评分；口径以 metrics.py / formulas.py 为准。
文案受 copy.FORBIDDEN 约束（不出现买卖导向词与数据供应商名）。
"""

from app.services.quant_research.metrics import MOMENTUM_WINDOWS, MetricDef

# concept -> (全称 zh, 大白话 zh, 怎么看 zh, 全称 en, 大白话 en, 怎么看 en)
_CONCEPTS: dict[str, tuple[str, str, str, str, str, str]] = {
    "pe": (
        "市盈率 P/E（Price / Earnings）",
        "买下公司每 1 元年利润，要付多少钱。比如 20 倍，相当于按现在的利润水平，约 20 年才能把股价「赚回来」。",
        "越低 = 相对利润越便宜；越高 = 市场对未来利润增长期待越大。",
        "Price-to-Earnings ratio (P/E)",
        "How much you pay for each $1 of annual profit. At 20x, current profits would take about 20 years to earn back the share price.",
        "Lower = cheaper relative to profits; higher = the market expects more profit growth.",
    ),
    "peg": (
        "市盈增长比 PEG（P/E ÷ Growth）",
        "市盈率再除以利润增速，把「贵不贵」和「长得快不快」放一起看。同样 30 倍市盈率：利润每年增 30% 的公司 PEG = 1，每年增 10% 的公司 PEG = 3。",
        "越低 = 价格里透支的成长越少；通常把 1 左右当作价格与增速大致匹配的参考线。",
        "Price/Earnings-to-Growth ratio (PEG)",
        "P/E divided by profit growth, so price and growth are judged together. At the same 30x P/E, a company growing profits 30% a year has a PEG of 1; one growing 10% has a PEG of 3.",
        "Lower = less growth priced in; around 1 is often used as a rough line where price and growth match.",
    ),
    "ps": (
        "市销率 P/S（Price / Sales）",
        "买下公司每 1 元年营收，要付多少钱。还没盈利、或利润波动大的公司，常用它代替市盈率。",
        "越低 = 相对营收越便宜；利润率高的公司，这个倍数天然更高。",
        "Price-to-Sales ratio (P/S)",
        "How much you pay for each $1 of annual revenue. Often used instead of P/E for companies that are not yet profitable or have volatile profits.",
        "Lower = cheaper relative to revenue; high-margin firms naturally carry higher multiples.",
    ),
    "ev_sales": (
        "企业价值 / 营收 EV/Sales",
        "EV（企业价值）= 市值 + 负债 − 现金，相当于连同债务一起把整家公司买下的总价。EV/营收 就是这个总价相当于几年的营收，比市销率多考虑了负债和现金。",
        "越低 = 整体买下公司相对营收越便宜。",
        "Enterprise Value to Sales (EV/Sales)",
        "EV (enterprise value) = market cap + debt − cash: the total price to acquire the whole company including its debt. EV/Sales shows how many years of revenue that price equals, accounting for debt and cash unlike P/S.",
        "Lower = cheaper to acquire the whole company relative to revenue.",
    ),
    "ev_ebitda": (
        "企业价值 / EBITDA",
        "整体买下公司（含债务）的总价，相当于几年的 EBITDA。EBITDA = 息税折旧摊销前利润，可以粗略理解为主营业务一年赚到的「毛现金」。负债多少不同的公司也能放在一起比。",
        "越低 = 相对主营业务的赚钱能力越便宜。",
        "Enterprise Value to EBITDA (EV/EBITDA)",
        "The total price to acquire the company (including debt) expressed in years of EBITDA — earnings before interest, taxes, depreciation and amortization, roughly the core business's gross cash earnings. Lets you compare companies with different debt levels.",
        "Lower = cheaper relative to the core business's earning power.",
    ),
    "ev_ebit": (
        "企业价值 / EBIT",
        "整体买下公司（含债务）的总价，相当于几年的 EBIT。EBIT = 息税前利润，即扣掉成本、费用和折旧摊销，但还没扣利息和所得税的经营利润。",
        "越低 = 相对经营利润越便宜；比 EV/EBITDA 更严格，因为扣掉了设备厂房的损耗。",
        "Enterprise Value to EBIT (EV/EBIT)",
        "The total price to acquire the company (including debt) expressed in years of EBIT — operating profit after costs and depreciation, before interest and income tax.",
        "Lower = cheaper relative to operating profit; stricter than EV/EBITDA because it deducts wear and tear on assets.",
    ),
    "pb": (
        "市净率 P/B（Price / Book）",
        "股价是每股账面净资产的几倍。账面净资产 = 公司总资产减去全部负债，也就是账面上属于股东的部分。1 倍约等于按账面价格买下这些资产。",
        "越低 = 相对家底越便宜；银行、保险等资产密集的行业最常用它。",
        "Price-to-Book ratio (P/B)",
        "Share price as a multiple of book value per share. Book value = total assets minus all liabilities, the part owned by shareholders on paper. 1x roughly means paying book value for those assets.",
        "Lower = cheaper relative to net assets; most used for asset-heavy sectors like banks and insurers.",
    ),
    "pcf": (
        "市现率 P/CF（Price / Cash Flow）",
        "买下公司每 1 元年经营现金流，要付多少钱。现金比利润更难「做账」，常用来交叉验证市盈率。",
        "越低 = 相对真金白银越便宜；若市盈率低而市现率高，说明利润的现金含量偏低。",
        "Price-to-Cash-Flow ratio (P/CF)",
        "How much you pay for each $1 of annual operating cash flow. Cash is harder to dress up than profit, so it cross-checks P/E.",
        "Lower = cheaper relative to actual cash; a low P/E with a high P/CF suggests profits are not well backed by cash.",
    ),
    "rev_growth": (
        "营收增速 Revenue Growth",
        "公司售出的产品和服务，比之前多了多少。这是「生意做没做大」最直接的体现。",
        "越高 = 生意扩张越快，关键看能否持续。",
        "Revenue Growth",
        "How much more product and service the company sold than before — the most direct sign of whether the business is getting bigger.",
        "Higher = faster expansion; what matters is whether it lasts.",
    ),
    "ebitda_growth": (
        "EBITDA 增速",
        "EBITDA（息税折旧摊销前利润，主营业务赚到的「毛现金」）比之前多了多少。",
        "越高 = 经营赚钱能力增长越快；若明显快于营收，说明利润率在改善。",
        "EBITDA Growth",
        "How much EBITDA — earnings before interest, taxes, depreciation and amortization, the core business's gross cash earnings — has grown.",
        "Higher = operating earnings growing faster; growth well above revenue growth means margins are improving.",
    ),
    "ebit_growth": (
        "EBIT 增速",
        "EBIT（息税前利润，扣掉折旧后、付利息和交税前的经营利润）比之前多了多少。",
        "越高 = 经营利润增长越快；若明显快于营收，说明规模效应在显现。",
        "EBIT Growth",
        "How much EBIT — operating profit after depreciation, before interest and tax — has grown.",
        "Higher = operating profit growing faster; growth well above revenue growth points to economies of scale.",
    ),
    "eps_growth": (
        "每股收益增速 EPS Growth",
        "EPS（每股收益）= 净利润 ÷ 总股数，即每一股分到多少利润。它的增速就是股东手里每一股「能分到的利润」长了多少。",
        "越高 = 每股利润增长越快；回购减少股数也会推高 EPS，要和净利润增速对照看。",
        "Earnings-per-Share Growth (EPS Growth)",
        "EPS = net income ÷ shares outstanding, the profit attributable to each share. Its growth shows how much each share's slice of profit has grown.",
        "Higher = per-share profit growing faster; share repurchases also lift EPS, so compare with net income growth.",
    ),
    "gross_m": (
        "毛利率 Gross Margin",
        "每卖 100 元的货，扣掉直接成本（原材料、生产、采购）后还剩多少元。体现产品的定价权和成本优势。",
        "越高 = 产品越「值钱」、越难被替代；软件、品牌消费品通常远高于制造、零售。",
        "Gross Margin",
        "For every $100 of sales, how much is left after direct costs (materials, production, purchasing). Reflects pricing power and cost advantage.",
        "Higher = products are harder to replace; software and branded goods usually far exceed manufacturing and retail.",
    ),
    "ebit_m": (
        "经营利润率 EBIT Margin",
        "每卖 100 元的货，扣掉成本和销售、管理、研发等各项经营费用后，还剩多少元经营利润。",
        "越高 = 主营业务越赚钱、费用控制越好。",
        "Operating (EBIT) Margin",
        "For every $100 of sales, how much operating profit remains after costs and selling, admin and R&D expenses.",
        "Higher = the core business is more profitable and expenses are better controlled.",
    ),
    "ebitda_m": (
        "EBITDA 利润率",
        "每卖 100 元的货，主营业务能产生多少元「毛现金」（还没扣折旧摊销、利息和税）。",
        "越高 = 经营的现金创造能力越强；重资产行业要再扣掉设备更新的开支看。",
        "EBITDA Margin",
        "For every $100 of sales, how much gross cash earnings the core business generates (before depreciation, interest and tax).",
        "Higher = stronger operating cash generation; for capital-heavy industries, also subtract equipment spending.",
    ),
    "net_m": (
        "净利率 Net Margin",
        "每卖 100 元的货，扣完所有成本、费用、利息和税后，最终落到股东手里的净利润是多少元。",
        "越高 = 最终留下给股东的利润越多。",
        "Net Profit Margin",
        "For every $100 of sales, how much net profit is left for shareholders after all costs, expenses, interest and taxes.",
        "Higher = more profit left for shareholders in the end.",
    ),
    "fcf_m": (
        "自由现金流利润率 FCF Margin",
        "每卖 100 元的货，扣掉日常经营开支和买设备、建厂房等投资后，最后真正能自由支配的现金有多少元。可以用来分红、回购或还债。",
        "越高 = 「真金白银」的赚钱能力越强。",
        "Free Cash Flow Margin",
        "For every $100 of sales, how much cash is truly free after operating costs and investment in equipment and facilities — cash available for dividends, repurchases or paying down debt.",
        "Higher = stronger real cash generation.",
    ),
    "roe": (
        "净资产收益率 ROE（Return on Equity）",
        "股东每投入 100 元本钱，公司一年能赚回多少元净利润。衡量公司用股东的钱「生钱」的效率，是最常用的盈利能力指标之一。",
        "越高 = 用股东的钱赚钱越有效率，长期稳定在 15% 以上通常被视为优秀。",
        "Return on Equity (ROE)",
        "For every $100 shareholders put in, how much net profit the company earns in a year. Measures how efficiently it turns shareholders' money into profit — one of the most-watched profitability metrics.",
        "Higher = more efficient use of shareholders' money; a steady 15%+ is often seen as excellent.",
    ),
    "roa": (
        "总资产收益率 ROA（Return on Assets）",
        "公司手里每 100 元资产（不管是股东的还是借来的），一年能赚回多少元净利润。",
        "越高 = 资产用得越有效率；银行等资产密集的行业天然偏低。",
        "Return on Assets (ROA)",
        "For every $100 of assets the company holds (whether funded by shareholders or debt), how much net profit it earns in a year.",
        "Higher = assets are used more efficiently; asset-heavy industries such as banks run naturally lower.",
    ),
    "roic": (
        "投入资本回报率 ROIC（Return on Invested Capital）",
        "真正投进生意里的每 100 元（股东的钱 + 借来的钱，扣掉闲置现金），一年能产生多少元税后经营利润。比 ROE 更难被借钱「放大」。",
        "越高 = 生意本身越赚钱；长期高于资金成本（常取 8%~10%）才算在创造价值。",
        "Return on Invested Capital (ROIC)",
        "For every $100 actually put to work in the business (shareholder money + borrowed money, minus idle cash), how much after-tax operating profit it produces in a year. Harder to inflate with debt than ROE.",
        "Higher = a more profitable business; staying above the cost of capital (often 8–10%) over time is what creates value.",
    ),
    "asset_turn": (
        "资产周转率 Asset Turnover",
        "公司每 100 元资产，一年能带来多少元营收。看的是资产「转得快不快」、用得勤不勤。",
        "越高 = 资产利用越充分；超市等薄利多销行业高，重资产行业低，要和同类比。",
        "Asset Turnover",
        "For every $100 of assets, how much revenue the company brings in a year — how hard its assets are working.",
        "Higher = assets are used more fully; high-volume, low-margin businesses like supermarkets run high, capital-heavy industries low.",
    ),
    "momentum": (
        "股价动量 Price Momentum",
        "股价在过去一段时间里涨跌了多少（分红已折算回股价）。反映市场最近怎么给这家公司定价。",
        "越高 = 近期市场越认可这家公司。",
        "Price Momentum",
        "How much the share price has risen or fallen over a period (dividends folded back in). Reflects how the market has been pricing the company lately.",
        "Higher = stronger recent market approval.",
    ),
    "revision": (
        "盈利预期修正 Estimate Revisions",
        "分析师们对公司未来业绩的平均预测，最近被上调还是下调了多少。可以理解为「专业人士最近对它是更乐观了还是更谨慎了」。",
        "为正 = 预期在上调，经营好于原先设想；为负 = 预期在下调。",
        "Estimate Revisions",
        "How much analysts' average forecast for future results has been raised or cut recently — whether professionals have grown more or less optimistic.",
        "Positive = forecasts being raised, the business is doing better than expected; negative = forecasts being cut.",
    ),
}

_VALUATION_PREFIXES = (
    ("peg", "peg"), ("pe_", "pe"), ("ps_", "ps"), ("ev_sales", "ev_sales"),
    ("ev_ebitda", "ev_ebitda"), ("ev_ebit", "ev_ebit"),
)
_GROWTH_PREFIXES = (
    ("rev_", "rev_growth"), ("ebitda_", "ebitda_growth"), ("ebit_", "ebit_growth"), ("eps_", "eps_growth"),
)


def _concept(metric: MetricDef) -> str:
    key, dim = metric.key, metric.dimension
    if dim == "valuation":
        return next((c for p, c in _VALUATION_PREFIXES if key.startswith(p)), key)
    if dim == "growth":
        return next(c for p, c in _GROWTH_PREFIXES if key.startswith(p))
    if dim in ("momentum", "revisions"):
        return "momentum" if dim == "momentum" else "revision"
    return key


def _period_note(metric: MetricDef, lang: str) -> str:
    """同一概念不同口径（TTM / 预期 / 3 年复合 / 窗口）的一句补充。"""
    key = metric.key
    zh = lang == "zh"
    if metric.dimension == "momentum":
        months = MOMENTUM_WINDOWS[key] // 21
        return f"这里看的是最近 {months} 个月。" if zh else f"This one covers the last {months} months."
    if metric.dimension == "revisions":
        fy = "下一财年" if "fy2" in key else "本财年"
        fy_en = "next fiscal year" if "fy2" in key else "current fiscal year"
        days = 30 if key.endswith("30d") else 90
        what = "营收" if key.startswith("rev") else "每股收益"
        what_en = "revenue" if key.startswith("rev") else "EPS"
        return (f"这里看的是对{fy}{what}的预测，和 {days} 天前相比。" if zh
                else f"This one compares the {fy_en} {what_en} forecast with {days} days ago.")
    if key.endswith("_fwd"):
        return ("「前瞻 / 预期」= 用分析师对未来的预测来算，不是已实现的数字。" if zh
                else "\"Forward\" uses analysts' forecasts, not results already achieved.")
    if key.endswith("_yoy"):
        return "「同比」= 最近 12 个月和再往前 12 个月比。" if zh else "\"YoY\" compares the last 12 months with the 12 months before."
    if key.endswith("_cagr3"):
        return ("「3 年复合」= 近 3 年平均每年增长多少，比单年更能看出趋势。" if zh
                else "\"3Y CAGR\" is the average yearly growth over 3 years, steadier than a single year.")
    if key.endswith("_ttm") or key in ("pcf",):
        return "「TTM」= 最近 12 个月的实际数字。" if zh else "\"TTM\" means actual figures for the trailing 12 months."
    return ""


def plain_language(metric: MetricDef, lang: str) -> tuple[str, str, str]:
    """返回（全称, 大白话释义, 高低怎么看）。"""
    zh_full, zh_plain, zh_read, en_full, en_plain, en_read = _CONCEPTS[_concept(metric)]
    full, plain, reading = (zh_full, zh_plain, zh_read) if lang == "zh" else (en_full, en_plain, en_read)
    note = _period_note(metric, lang)
    if note:
        plain = f"{plain}{note}" if lang == "zh" else f"{plain} {note}"
    return full, plain, reading


# 算式输入项：基础概念 + 期间口径，拼成一句大白话（zh, en）
_INPUT_BASE: dict[str, tuple[str, str]] = {
    "price": ("每一股在市场上的成交价格（已按分红、拆股前复权）。",
              "The market price of one share (adjusted for dividends and splits)."),
    "market_cap": ("市值 = 股价 × 总股数，即市场给整家公司股权的标价。",
                   "Market cap = share price × shares outstanding: the market's price tag on all the equity."),
    "ev": ("企业价值 = 市值 + 负债 − 现金，相当于连同债务一起买下整家公司的总价。",
           "Enterprise value = market cap + debt − cash: the total price to acquire the whole company including its debt."),
    "eps": ("EPS 每股收益 = 净利润 ÷ 总股数，即每一股分到多少利润。",
            "EPS = net income ÷ shares outstanding: the profit attributable to each share."),
    "rev": ("营收：公司售出产品和服务收到的总收入，还没扣任何成本。",
            "Revenue: total income from selling products and services, before any costs."),
    "ebitda": ("EBITDA：息税折旧摊销前利润，可粗略看作主营业务赚到的「毛现金」。",
               "EBITDA: earnings before interest, taxes, depreciation and amortization — roughly the core business's gross cash earnings."),
    "ebit": ("EBIT：息税前利润，扣掉成本、费用和折旧摊销后，还没付利息和交税的经营利润。",
             "EBIT: operating profit after costs and depreciation, before interest and tax."),
    "gross": ("毛利 = 营收 − 直接成本（原材料、生产、采购）。",
              "Gross profit = revenue − direct costs (materials, production, purchasing)."),
    "net": ("净利润：扣完所有成本、费用、利息和税后，最终归股东的利润。",
            "Net income: profit left for shareholders after all costs, expenses, interest and taxes."),
    "ocf": ("经营现金流：日常经营实际收进来减去付出去的现金，不含投资和融资。",
            "Operating cash flow: cash actually collected minus paid in day-to-day operations, excluding investing and financing."),
    "fcf": ("自由现金流 = 经营现金流 − 资本开支（买设备、建厂房），是真正可以自由支配的现金。",
            "Free cash flow = operating cash flow − capital spending (equipment, facilities): the cash truly free to use."),
    "equity": ("股东权益（账面净资产）= 总资产 − 总负债，即账面上属于股东的部分，取最近一期报表。",
               "Shareholders' equity (book value) = total assets − total liabilities, from the latest balance sheet."),
    "assets": ("总资产：公司拥有的全部资产（现金、厂房、存货、应收款等），取最近一期报表。",
               "Total assets: everything the company owns (cash, plants, inventory, receivables…), from the latest balance sheet."),
    "invested": ("投入资本 = 负债 + 股东权益 − 现金，即真正投进生意里的钱（不算闲置现金）。",
                 "Invested capital = debt + equity − cash: money actually put to work in the business, excluding idle cash."),
    "nopat": ("税后 EBIT = EBIT ×（1 − 税率），即假设没有负债时经营利润交完税还剩多少。",
              "After-tax EBIT = EBIT × (1 − tax rate): operating profit after tax, as if the company had no debt."),
    "pe": ("市盈率 = 股价 ÷ 每股收益，买下每 1 元利润要付的价格。",
           "P/E = price ÷ EPS: the price paid for each $1 of profit."),
    "growth_pct": ("每股收益的增速，以百分数代入，例如增长 20% 就代入 20。",
                   "EPS growth entered as a percent number, e.g. 20% growth is entered as 20."),
    "close_now": ("最近一个交易日的收盘价（已前复权，分红折算回股价）。",
                  "The latest closing price (adjusted, with dividends folded back in)."),
    "close_then": ("区间开始那天的收盘价（已前复权），用来算这段时间涨跌了多少。",
                   "The adjusted closing price at the start of the window, used to measure the change."),
    "est_new": ("分析师们现在对这个财年的平均预测。", "Analysts' current average forecast for this fiscal year."),
    "est_old": ("同一批预测在当时（30 或 90 天前）的平均值，和现在比就知道是上调还是下调。",
                "The same average forecast back then (30 or 90 days ago); comparing it with today shows raises or cuts."),
}

_INPUT_PERIOD: list[tuple[str, tuple[str, str]]] = [
    ("_ttm_prev", ("这里取再往前 12 个月的实际数，用来算同比。", "Here: the actual figure for the 12 months before that, used for year-over-year growth.")),
    ("_ttm_3y", ("这里取 3 年前同期 12 个月的实际数，用来算 3 年复合增速。", "Here: the actual 12-month figure from 3 years ago, used for 3-year CAGR.")),
    ("_ttm", ("这里取最近 12 个月（最近 4 个季度加总）的实际数。", "Here: the actual figure for the trailing 12 months (last 4 quarters).")),
    ("_ntm", ("这里取分析师对未来 12 个月的平均预测（按本财年、下财年剩余时间加权）。", "Here: analysts' average forecast for the next 12 months (time-weighted across this and next fiscal year).")),
    ("_fy0", ("这里取上一个完整财年的实际数。", "Here: the actual figure for the last full fiscal year.")),
    ("_fy1", ("这里取分析师对本财年的平均预测。", "Here: analysts' average forecast for the current fiscal year.")),
    ("_fy2", ("这里取分析师对下一财年的平均预测。", "Here: analysts' average forecast for the next fiscal year.")),
]


def input_hint(name: str, lang: str) -> str | None:
    """算式输入项的大白话解释（概念 + 取数口径）。"""
    i = 0 if lang == "zh" else 1
    base, period = name, ""
    for suffix, texts in _INPUT_PERIOD:
        if name.endswith(suffix):
            base, period = name[: -len(suffix)], texts[i]
            break
    texts = _INPUT_BASE.get(base)
    if texts is None:
        return None
    return texts[i] + (period if i == 0 else f" {period}" if period else "")


# concept -> (为什么重要 zh, 我们为什么用它 zh, why en, purpose en)
_WHY: dict[str, tuple[str, str, str, str]] = {
    "pe": (
        "长期来看，股价跟着利润走。市盈率把「价格」和「利润」放在一起，是全球投资者最常用的估值尺子，几乎所有研报和财经新闻都会用到。",
        "估值维度的核心指标。我们同时看最近 12 个月（已实现，有据可查）和未来 12 个月（预期，反映市场正在为什么定价）两个版本。亏损公司的市盈率没有意义，标为不适用、不参与评分。",
        "Over the long run, share prices follow profits. P/E puts price and profit side by side and is the most widely used valuation yardstick in research and financial news.",
        "The core valuation metric. We use both the trailing 12 months (actual, verifiable) and the next 12 months (forecast, what the market is pricing in). P/E is meaningless for loss-makers, so it is marked not applicable and left unscored.",
    ),
    "peg": (
        "只看市盈率会冤枉高成长公司：长得快的公司本来就值更高的倍数。PEG 把增速考虑进来，区分「贵但长得快」和「贵又长不动」。",
        "给估值维度补上成长视角，平衡市盈率对高成长公司的偏见。增速为负或接近零时比值会失真，不参与评分。",
        "P/E alone penalizes fast growers, which deserve higher multiples. PEG factors in growth, separating \"pricey but growing fast\" from \"pricey and stalling\".",
        "Adds a growth lens to valuation, offsetting P/E's bias against fast growers. When growth is negative or near zero the ratio distorts and is left unscored.",
    ),
    "ps": (
        "营收比利润更稳定、更难调节，而且亏损公司没有市盈率可用。市销率让还没盈利或利润波动大的公司也能比较贵不贵。",
        "让估值维度覆盖到亏损和利润波动大的公司，并和市盈率互相印证：市销率低而市盈率高，往往说明利润率偏低。",
        "Revenue is steadier and harder to manipulate than profit, and loss-makers have no usable P/E. P/S lets unprofitable or volatile companies be compared on price too.",
        "Extends valuation to loss-making and volatile companies and cross-checks P/E: a low P/S with a high P/E usually signals thin margins.",
    ),
    "ev_sales": (
        "市值只算股东那部分，忽略了公司背的债和手里的现金。两家市值一样的公司，一家负债累累、一家现金充裕，真要整体买下来，代价完全不同。",
        "在市销率的基础上把负债和现金算进来，避免高负债公司看起来「虚假便宜」。",
        "Market cap counts only the shareholders' slice and ignores debt and cash. Two companies with equal market caps — one heavily indebted, one cash-rich — cost very different amounts to acquire outright.",
        "Builds on P/S by bringing debt and cash into the price, so heavily indebted companies don't look falsely cheap.",
    ),
    "ev_ebitda": (
        "这是企业并购中最常用的估值方法：收购方要承接全部债务，关心的是主营业务能产生多少现金利润。它不受折旧政策、税率和融资方式影响，不同公司之间可比性强。",
        "估值维度里最「中性」的一把尺子，用来和市盈率互相校验：市盈率低但 EV/EBITDA 高，往往是负债多或一次性收益抬高了利润。",
        "It is the go-to valuation method in mergers and acquisitions: an acquirer takes on all the debt and cares about the core business's cash earnings. It is unaffected by depreciation policy, tax rates and financing, so it compares well across companies.",
        "The most neutral valuation yardstick, used to cross-check P/E: a low P/E with a high EV/EBITDA often means heavy debt or one-off gains are flattering profits.",
    ),
    "ev_ebit": (
        "厂房设备会磨损、要花钱更新。EBITDA 没扣这部分，会让重资产公司看起来更便宜；EBIT 扣掉了折旧，更接近真实的经营利润。",
        "在 EV/EBITDA 之外再加一道更严格的检验，防止重资产公司靠「不扣折旧」显得便宜。",
        "Plants and equipment wear out and must be replaced. EBITDA ignores that, flattering capital-heavy firms; EBIT deducts depreciation and is closer to true operating profit.",
        "A stricter check alongside EV/EBITDA, so capital-heavy companies can't look cheap just by leaving out depreciation.",
    ),
    "pb": (
        "净资产是公司的「家底」。对银行、保险这类资产本身就是生意的行业，利润波动大时，市净率比市盈率更能反映价格是否合理。",
        "给估值维度补上资产视角，对金融等资产密集的行业尤其有参考价值。",
        "Book value is the company's net worth on paper. For banks and insurers, where assets are the business, P/B often says more than P/E when profits swing.",
        "Adds an asset lens to valuation, especially useful for asset-heavy sectors such as financials.",
    ),
    "pcf": (
        "利润可以通过会计处理调节，现金很难作假。很多财务问题最早都是在「利润好看但现金流差」上露出马脚的。",
        "作为市盈率的现金版本，检验利润有没有真金白银支撑。金融股的经营现金流包含存贷款变动、不可比，标为不适用。",
        "Profits can be shaped by accounting choices; cash is much harder to fake. Many financial problems first show up as \"good profits, weak cash flow\".",
        "A cash version of P/E that checks whether profits are backed by real cash. For financials, operating cash flow includes deposit and loan movements and isn't comparable, so it is marked not applicable.",
    ),
    "rev_growth": (
        "营收是一切利润的源头。没有营收增长，利润增长只能靠压缩成本，迟早会到头；持续扩大的营收是公司长期变大的根基。",
        "成长维度的基础指标。我们看三个版本：同比（最近一年）、3 年复合（长期趋势，过滤单年波动）、预期增速（未来）——三者方向一致，说明成长更扎实。",
        "Revenue is the source of all profit. Without revenue growth, profit can only grow by cutting costs, which eventually runs out; steadily rising revenue is the foundation of long-term growth.",
        "The foundation of the growth factor. We use three versions: year-over-year (last year), 3-year CAGR (long-term trend, smoothing single-year noise) and forecast growth (the future). When all three agree, growth is on firmer ground.",
    ),
    "ebitda_growth": (
        "营收增长不一定带来更多利润，靠打折冲量的增长没有意义。EBITDA 增速告诉你，增长是不是「赚钱的增长」。",
        "检验营收增长有没有转化为经营利润；同时看已实现和预期两个版本。",
        "Revenue growth doesn't always bring more profit — growth bought with discounts is hollow. EBITDA growth shows whether growth is profitable growth.",
        "Checks whether revenue growth turns into operating earnings, using both actual and forecast versions.",
    ),
    "ebit_growth": (
        "EBIT 扣掉了折旧，能看出增长是不是靠大量砸钱买设备换来的。EBIT 增速快于营收，说明规模越大越赚钱。",
        "和 EBITDA 增速配合，看扣除设备损耗后经营利润是否仍在增长；同时看已实现和预期两个版本。",
        "EBIT deducts depreciation, revealing whether growth was bought with heavy equipment spending. EBIT growing faster than revenue means scale is making the business more profitable.",
        "Pairs with EBITDA growth to see whether operating profit still grows after equipment wear, using both actual and forecast versions.",
    ),
    "eps_growth": (
        "股东真正拥有的是每一股，EPS 增长才直接对应每股价值的增长。长期来看，股价走势和每股收益的增长高度相关。",
        "成长维度里离股东最近的指标，也是 PEG 的增速来源；同时看已实现和预期两个版本。",
        "Shareholders own shares, so EPS growth maps directly to growth in per-share value. Over the long run, share prices track EPS growth closely.",
        "The growth metric closest to shareholders and the growth input for PEG, using both actual and forecast versions.",
    ),
    "gross_m": (
        "毛利率是公司「护城河」最直观的体现：产品有独特性、品牌有号召力，才能卖得比成本贵很多。毛利率高的公司才有余力投研发、做营销、扛住价格战。",
        "盈利能力维度的第一层：先看产品本身赚不赚钱，再往下看扣完费用、利息、税之后还剩多少（经营利润率 → 净利率 → 自由现金流利润率）。",
        "Gross margin is the most visible sign of a competitive moat: only distinctive products and strong brands can be priced far above cost. High-margin firms can afford R&D and marketing and can weather price wars.",
        "The first layer of profitability: does the product itself make money? Later layers show what's left after expenses, interest and tax (operating margin → net margin → free cash flow margin).",
    ),
    "ebit_m": (
        "毛利高不代表公司赚钱，销售、管理、研发费用可能把毛利吃光。经营利润率反映主营业务真正的赚钱能力和管理效率。",
        "盈利能力维度的第二层：在毛利率基础上扣除各项经营费用，看主营业务本身的盈利水平。",
        "High gross margin doesn't guarantee profit — selling, admin and R&D costs can eat it all. Operating margin shows the core business's real earning power and how well it is run.",
        "The second layer of profitability: after operating expenses, how profitable is the core business itself?",
    ),
    "ebitda_m": (
        "EBITDA 利润率排除了折旧政策和融资结构的影响，方便把资本结构不同的公司放在一起比较主业的现金创造能力。",
        "和经营利润率配合看：两者差距大，说明折旧摊销重（重资产生意）；差距小，则是轻资产生意。",
        "EBITDA margin strips out depreciation policy and financing structure, making it easy to compare core cash generation across differently financed companies.",
        "Read alongside operating margin: a wide gap means heavy depreciation (a capital-heavy business); a narrow gap means an asset-light one.",
    ),
    "net_m": (
        "净利率是所有成本、费用、利息、税扣完后的最终结果，直接决定股东能分到多少。",
        "盈利能力维度的第三层：看最终落到股东手里的利润占比。",
        "Net margin is the bottom line after every cost, expense, interest payment and tax — it decides what shareholders actually get.",
        "The third layer of profitability: the share of revenue that finally reaches shareholders.",
    ),
    "fcf_m": (
        "利润是会计数字，自由现金流才是公司真正能拿来分红、回购、还债、再投资的钱。长期回报优秀的公司，大多能持续产生大量自由现金流。",
        "盈利能力维度的最后一层，检验利润能不能变成真金白银。金融股的现金流结构不同，标为不适用。",
        "Profit is an accounting figure; free cash flow is the money a company can actually use for dividends, repurchases, debt repayment and reinvestment. Most companies with strong long-term returns generate plenty of it.",
        "The final layer of profitability: can profits turn into real cash? Financials have a different cash-flow structure and are marked not applicable.",
    ),
    "roe": (
        "ROE 衡量公司用股东的钱「钱生钱」的能力。能长期保持高 ROE 的公司，把赚到的利润再投进去还能获得高回报，股东的财富就会像复利一样增长。",
        "盈利能力维度里从股东视角看回报。因为借钱也能把 ROE 撑高，我们同时看 ROA 和 ROIC 来交叉验证。",
        "ROE measures how well a company turns shareholders' money into more money. A company that sustains high ROE can reinvest profits at high returns, compounding shareholder wealth.",
        "Profitability from the shareholder's view. Because borrowing can inflate ROE, we cross-check it with ROA and ROIC.",
    ),
    "roa": (
        "ROA 不区分钱是借来的还是股东的，衡量全部资产的赚钱效率，不容易被高杠杆美化。",
        "和 ROE 配合看：ROE 高但 ROA 低，说明高回报主要靠借钱放大，风险更高。",
        "ROA doesn't care whether money is borrowed or owned; it measures how efficiently all assets earn, and leverage can't easily dress it up.",
        "Read alongside ROE: high ROE with low ROA means returns are mostly amplified by debt, which carries more risk.",
    ),
    "roic": (
        "很多长期投资者把 ROIC 视为衡量生意质量最关键的指标：它回答「每投进去 1 元，生意本身能赚回多少」。长期高于资金成本，公司越扩张越创造价值；低于资金成本，扩张反而在消耗价值。",
        "盈利能力维度里最能反映生意本身质量的指标，不受融资方式影响，用来和 ROE 互相校验。",
        "Many long-term investors see ROIC as the key measure of business quality: for every $1 put in, what does the business earn? Above the cost of capital, growth creates value; below it, growth destroys value.",
        "The profitability metric that best reflects business quality, independent of financing, and a cross-check on ROE.",
    ),
    "asset_turn": (
        "赚钱有两条路：每笔生意赚得多（高利润率），或者用同样的资产做更多生意（高周转）。资产周转率衡量的是后一条。",
        "补上盈利能力的「效率」一面，帮助理解回报率来自高利润率还是高周转。",
        "There are two ways to earn: make more on each sale (high margins) or do more business with the same assets (high turnover). Asset turnover measures the second.",
        "Adds the efficiency side of profitability, showing whether returns come from high margins or high turnover.",
    ),
    "momentum": (
        "股价走势汇总了市场对公司最新信息的判断。量化研究中被反复验证的一个现象是：过去一段时间相对偏强的股票，之后一段时间往往仍相对偏强（动量效应）。",
        "动量维度看市场怎么定价，与看公司本身的基本面维度互补。我们同时看 3、6、9、12 个月四个窗口再取平均，避免单一时间段的偶然波动。",
        "Price trends summarize the market's reading of the latest information. One of the most repeatedly documented findings in quant research is that relatively strong stocks tend to stay relatively strong for a while (the momentum effect).",
        "The momentum factor shows how the market is pricing the stock, complementing the fundamental factors. We average four windows — 3, 6, 9 and 12 months — to avoid one period's noise.",
    ),
    "revision": (
        "分析师会根据公司最新的经营情况调整预测。预期持续上调，往往意味着公司经营好于原先设想；研究发现，盈利预期的变化方向对之后的股价表现有一定解释力。",
        "反映「边际变化」：基本面是公司现在的状态，预期修正是最近在往哪边变。我们看本财年、下财年 EPS 和本财年营收在 30 / 90 天里的变化。",
        "Analysts update forecasts as new business information arrives. Steady upward revisions usually mean the business is doing better than expected, and research finds the direction of revisions helps explain later share-price performance.",
        "Captures change at the margin: fundamentals describe where the company is, revisions show which way things are moving. We track current- and next-year EPS and current-year revenue over 30 and 90 days.",
    ),
}


def why_and_purpose(metric: MetricDef, lang: str) -> tuple[str, str]:
    """返回（为什么重要, 我们为什么用它）。"""
    zh_why, zh_purpose, en_why, en_purpose = _WHY[_concept(metric)]
    return (zh_why, zh_purpose) if lang == "zh" else (en_why, en_purpose)
