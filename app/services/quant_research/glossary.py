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
        "真正投进生意里的每 100 元（股东的钱 + 借来的钱，不算闲着没用的现金），一年能赚回多少元（按交完税的经营利润算）。比 ROE 更不容易被借钱撑高。",
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
    "net_debt_ebitda": (
        "净负债 / EBITDA Net Debt to EBITDA",
        "把公司欠的钱扣掉手头现金，剩下的净债务，用公司一年主营业务赚到的「毛现金」来还，大约要几年。现金比负债多就是「净现金」，记 0。",
        "越低 = 还债压力越小；0 = 现金已经够还清全部负债。",
        "Net Debt to EBITDA",
        "Subtract cash from what the company owes, then ask how many years of its core business's gross cash earnings it would take to repay what is left. If cash exceeds debt the company has \"net cash\" and scores 0.",
        "Lower = less repayment pressure; 0 = cash already covers all debt.",
    ),
    "interest_cov": (
        "利息保障倍数 Interest Coverage",
        "公司一年的经营利润（EBIT），够付利息多少次。比如 5 倍，表示赚的钱是利息的 5 倍，利润掉一大半也还付得起。没有利息支出的公司记上限 100。",
        "越高 = 付利息越轻松；低于 2 倍说明利润勉强够付利息。",
        "Interest Coverage",
        "How many times over a year of operating profit (EBIT) covers the interest bill. At 5x, profit could fall by most of its size and interest would still be payable. A company with no interest expense is set to the cap of 100.",
        "Higher = interest is easier to pay; below about 2x means profit barely covers interest.",
    ),
    "current_ratio": (
        "流动比率 Current Ratio",
        "一年内要付出去的钱（流动负债），手头一年内能变成现金的资产（现金、应收款、存货等，即流动资产）够不够盖住。1.5 倍表示每欠 1 块短期的钱，手里有 1.5 块短期能变现的资产。",
        "越高 = 短期还账越宽裕；低于 1 说明短期资产不够盖短期负债。",
        "Current Ratio",
        "Whether assets that can be turned into cash within a year (cash, receivables, inventory — current assets) cover what must be paid within a year (current liabilities). At 1.5x, every $1 of short-term debt has $1.5 of short-term assets behind it.",
        "Higher = more room to pay near-term bills; below 1 means short-term assets do not cover short-term liabilities.",
    ),
    "runway_years": (
        "现金可支撑年数 Cash Runway",
        "如果公司继续按最近 12 个月的速度烧钱（自由现金流为负），手头现金能撑几年。自由现金流为正的公司不烧钱，记上限 10 年。",
        "越高 = 越不用担心现金耗尽；低于 1 年说明现金可能很快见底，要靠融资续命。",
        "Cash Runway",
        "If the company keeps burning cash at its trailing 12-month rate (negative free cash flow), how many years its cash on hand would last. Companies with positive free cash flow burn nothing and are set to the cap of 10 years.",
        "Higher = less worry about running out of cash; under 1 year means cash may run out soon unless more is raised.",
    ),
    "cfo_ni": (
        "经营现金流 / 净利润 Cash Conversion",
        "账面上赚的每 1 元净利润，实际收进了多少现金。100% 表示利润都变成了现金；明显低于 100%，说明利润很多还停留在账上（比如货发出去了还没收到钱）。",
        "越高 = 利润越是真金白银；长期低于 80% 要留意利润质量。",
        "Cash Conversion",
        "For each $1 of net income on paper, how much cash actually came in from operations. 100% means profit turned fully into cash; well below 100% means much of the profit is still on paper (for example goods shipped but not yet paid for).",
        "Higher = profit is better backed by cash; staying below 80% for long deserves attention.",
    ),
    "fcf_sbc_m": (
        "扣股权激励后自由现金流利润率 FCF Margin after Stock Comp",
        "自由现金流利润率再扣掉「用股票发给员工的薪酬」。很多科技公司少发现金、多发股票，账上现金流看着很好，但这些股票最终会稀释股东，所以也算一种真实成本。",
        "越高 = 即使把股票薪酬也当成本，公司仍然能留下真金白银；明显低于自由现金流利润率，说明股票薪酬占了很大比重。",
        "FCF Margin after Stock Comp",
        "Free cash flow margin after also subtracting pay given to employees in stock. Many tech companies pay less in cash and more in shares, which flatters cash flow, but those shares eventually dilute shareholders, so they are a real cost too.",
        "Higher = the company still keeps real cash even when stock pay is counted as a cost; far below the plain free cash flow margin means stock pay is a large share of the story.",
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
    "net_debt": ("净负债 = 负债 − 现金及短期投资；为负说明现金比负债还多（净现金），取最近一期报表。",
                 "Net debt = debt − cash and short-term investments; negative means cash exceeds debt (net cash), from the latest balance sheet."),
    "interest": ("利息支出：公司一年为借款付出的利息，取绝对值。",
                 "Interest expense: the interest the company paid on its borrowings, taken as a positive number."),
    "current_assets": ("流动资产：一年内能变成现金的资产（现金、应收账款、存货等），取最近一期报表。",
                       "Current assets: assets that can be turned into cash within a year (cash, receivables, inventory…), from the latest balance sheet."),
    "current_liabilities": ("流动负债：一年内要付出去的钱（应付账款、短期借款等），取最近一期报表。",
                            "Current liabilities: money due within a year (payables, short-term borrowings…), from the latest balance sheet."),
    "cash": ("现金及短期投资：账上随时能动用的现金，取最近一期报表。",
             "Cash and short-term investments: cash available on short notice, from the latest balance sheet."),
    "burn": ("年自由现金流出 = −自由现金流，即一年净花掉的现金（自由现金流为负时才有意义）。",
             "Free-cash-flow burn = −free cash flow: cash spent on net over a year (meaningful only when free cash flow is negative)."),
    "fcf_sbc": ("扣股权激励后自由现金流 = 自由现金流 − 股权激励费用（用股票发给员工的薪酬），把股票薪酬也当成真实成本。",
                "Free cash flow after stock comp = free cash flow − stock-based compensation (pay given in shares), counting stock pay as a real cost."),
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


# concept -> (为什么重要 zh, 我们为什么用它 zh, why en, purpose en)：大白话，一两句，不用需要再解释的术语
_WHY: dict[str, tuple[str, str, str, str]] = {
    "pe": (
        "你买股票，买的其实是公司将来的利润。同样一份利润，花的钱越少越划算，市盈率就是在算这笔账。",
        "它是看「贵不贵」最基本的尺子。我们同时看过去 12 个月（真实发生的）和未来 12 个月（分析师预计的）两个版本。公司亏钱时市盈率没有意义，就不算分。",
        "When you own a stock, you're really buying the company's future profits. The less you pay for the same profit, the better the deal — P/E does that math.",
        "It's the most basic \"is it expensive?\" yardstick. We look at both the past 12 months (what actually happened) and the next 12 months (what analysts expect). P/E means nothing when a company loses money, so it isn't scored then.",
    ),
    "peg": (
        "长得快的公司，贵一点也可能值。PEG 帮你分辨：它贵，是因为真的长得快，还是单纯被炒贵了。",
        "单看市盈率，成长快的公司总显得很贵，PEG 帮它们讨个公道。利润不增长时这个比值没意义，就不算分。",
        "A fast-growing company can be worth a higher price. PEG helps you tell whether it's pricey because it's growing fast, or just pricey.",
        "On P/E alone, fast growers always look expensive; PEG gives them a fair hearing. It's meaningless when profits aren't growing, so it isn't scored then.",
    ),
    "ps": (
        "有些公司还没开始赚钱，算不了市盈率，但它们有收入。用收入来衡量贵不贵，才能把这些公司也放进来比。",
        "让还没赚钱的公司也能比较贵不贵。也能和市盈率对照：按收入看不贵、按利润看却很贵，多半是公司利润率太低。",
        "Some companies don't make a profit yet, so they have no P/E — but they do have revenue. Measuring price against revenue lets them be compared too.",
        "Lets unprofitable companies be compared on price, and cross-checks P/E: cheap on revenue but pricey on profit usually means thin margins.",
    ),
    "ev_sales": (
        "公司欠的债，最终也得由买下它的人来还。只看市值，欠很多钱的公司会看起来比实际便宜。",
        "在市销率的基础上把欠债和现金都算进去，防止欠债多的公司看起来虚假便宜。",
        "A company's debts end up being the buyer's problem. Looking at market cap alone makes heavily indebted companies seem cheaper than they are.",
        "Builds on P/S by counting debt and cash, so indebted companies don't look falsely cheap.",
    ),
    "ev_ebitda": (
        "它把欠债算进价格、把利润算到最原始的那一层，这样不同公司记账方式不同、借钱多少不同，也能公平地比。",
        "用来和市盈率互相核对：市盈率便宜但这个指标贵，常见原因是公司欠债多，或者利润里有一次性的意外收入。",
        "It adds debt to the price and uses the rawest form of profit, so companies with different bookkeeping and borrowing can be compared fairly.",
        "A cross-check on P/E: cheap on P/E but expensive here usually means heavy debt or a one-off windfall in profits.",
    ),
    "ev_ebit": (
        "机器设备会用旧，换新要花钱。EBIT 把这笔「用旧的损耗」扣掉了，更接近公司真正赚到的钱。",
        "比 EV/EBITDA 更严格一点，防止设备多、损耗大的公司看起来便宜。",
        "Machines wear out and cost money to replace. EBIT subtracts that wear and tear, so it's closer to what the company truly earns.",
        "A slightly stricter version of EV/EBITDA, so equipment-heavy companies don't look cheap.",
    ),
    "pb": (
        "看你花的钱能买到多少「家底」。银行、保险这类公司，家底本身就是它们的生意，这个指标对它们特别有用。",
        "从「家底」的角度补充看贵不贵，对银行、保险这类公司更有参考价值。",
        "It shows how much of the company's net worth your money buys. For banks and insurers, that net worth is the business, so it's especially useful there.",
        "Adds a net-worth view of price, most useful for banks and insurers.",
    ),
    "pcf": (
        "利润是账上算出来的，现金是真收到的钱。利润很好看、现金却进不来，往往是个危险信号。",
        "核对利润有没有真金白银撑着。银行等金融公司的现金流里混着存款和贷款，没法和别人比，就不算分。",
        "Profit is calculated on paper; cash is money actually received. Great profits with little cash coming in is often a warning sign.",
        "Checks that profits are backed by real cash. For banks and other financials, cash flow mixes in deposits and loans, so it isn't scored.",
    ),
    "rev_growth": (
        "利润是从收入里来的。收入一直在涨，公司才可能越做越大；收入不涨，光靠省钱撑起来的利润增长走不远。",
        "这是看成长最基础的指标。我们看三个版本：最近一年比去年、近三年平均每年、分析师预计的明年。三个都好，成长才靠谱。",
        "Profit comes out of revenue. Only rising revenue lets a company keep getting bigger; profit growth from cost-cutting alone doesn't last.",
        "The most basic growth metric. We look at three versions: last year vs the year before, the 3-year yearly average, and analysts' forecast. When all three look good, the growth is more reliable.",
    ),
    "ebitda_growth": (
        "收入涨了不等于更赚钱——靠打折拼命卖，收入会涨，赚到的钱反而可能变少。这个数看的是「赚到的钱」有没有跟着涨。",
        "核对收入增长有没有带来更多利润。看过去和未来两个版本。",
        "More revenue doesn't always mean more profit — heavy discounting lifts sales but can shrink earnings. This checks whether earnings grew too.",
        "Checks that revenue growth brought more profit, in both past and forecast versions.",
    ),
    "ebit_growth": (
        "有些增长是靠不停买设备堆出来的。扣掉设备损耗后利润还在涨，这样的增长才算划算。",
        "和 EBITDA 增速一起看，确认扣掉设备损耗后利润还在涨。看过去和未来两个版本。",
        "Some growth is bought by piling up equipment. If profit still grows after subtracting equipment wear, the growth is worth it.",
        "Read with EBITDA growth to confirm profit still grows after equipment wear, in both past and forecast versions.",
    ),
    "eps_growth": (
        "你手里拿的是股票，每一股分到的利润涨了，你才真正得到好处。长期来看，股价基本跟着每股利润走。",
        "这是和股东关系最直接的成长指标，也用来计算 PEG。看过去和未来两个版本。",
        "You hold shares, so you only truly benefit when the profit per share goes up. Over the long run, share prices largely follow it.",
        "The growth metric closest to shareholders, also used to calculate PEG. We look at past and forecast versions.",
    ),
    "gross_m": (
        "毛利率高，说明东西能卖上价钱、别人不容易抢走生意。有了这份余钱，公司才能搞研发、打广告、扛得住降价竞争。",
        "盈利能力我们一层层往下看：先看毛利率（东西本身赚不赚钱），再看经营利润率、净利率，最后看自由现金流（真正落袋多少）。毛利率是第一层。",
        "A high gross margin means the products command a good price and rivals can't easily take the business. That spare money funds R&D, advertising and surviving price wars.",
        "We read profitability layer by layer: gross margin first (does the product itself make money?), then operating margin, net margin, and finally free cash flow (what actually lands in the bank). This is the first layer.",
    ),
    "ebit_m": (
        "东西卖得贵不代表公司赚钱，房租、工资、广告、研发都要花钱。扣掉这些还剩得多，才说明公司经营得好。",
        "盈利能力的第二层：扣掉日常经营开销后，主业还能赚多少。",
        "Selling at a good price doesn't mean the company makes money — rent, salaries, ads and R&D all cost money. Plenty left after those means the business is well run.",
        "The second layer of profitability: what the core business still earns after day-to-day running costs.",
    ),
    "ebitda_m": (
        "它不受公司怎么记设备损耗、借了多少钱的影响，适合把不同公司的「主业赚钱能力」放在一起比。",
        "和经营利润率对照看：两者差得多，说明公司设备多、损耗大；差得少，说明是不太靠设备的轻资产生意。",
        "It isn't affected by how a company books equipment wear or how much it borrowed, so it's good for comparing core earning power across companies.",
        "Compare it with operating margin: a big gap means lots of equipment and wear; a small gap means an asset-light business.",
    ),
    "net_m": (
        "所有该花的、该还的、该交的都扣完，剩下的才是股东的。这是最终「到手」的比例。",
        "盈利能力的第三层：所有东西扣完，最后留给股东多少。",
        "After everything that has to be spent, repaid and paid in tax, what's left belongs to shareholders. It's the final take-home share.",
        "The third layer of profitability: what's left for shareholders after everything.",
    ),
    "fcf_m": (
        "利润是账面上的，自由现金流才是真正落袋、能拿来分红和回购的钱。公司能不能持续回馈股东，主要看它。",
        "盈利能力的最后一层：利润最终能不能变成真金白银。银行等金融公司的现金流口径不同，不算分。",
        "Profit lives on paper; free cash flow is money actually in the bank, available for dividends and repurchases. Whether a company can keep rewarding shareholders depends mostly on it.",
        "The last layer of profitability: does profit turn into real cash? Financials count cash flow differently, so it isn't scored for them.",
    ),
    "roe": (
        "就像存银行看利息：股东把钱交给公司，ROE 就是公司每年能帮股东赚多少「利息」。利息长期都高，钱就能利滚利。",
        "从股东的角度看回报。因为借钱也能把 ROE 撑高，我们会同时看 ROA 和 ROIC 来核对。",
        "Think of bank interest: shareholders hand the company their money, and ROE is the yearly \"interest\" the company earns them. High interest year after year lets money snowball.",
        "Measures returns from the shareholder's side. Since borrowing can also push ROE up, we cross-check it with ROA and ROIC.",
    ),
    "roa": (
        "公司赚钱可以靠自己的钱，也可以靠借来的钱。ROA 把借来的也算进去，看公司手里所有家当一共能赚多少，借钱撑不高它。",
        "和 ROE 对照看：ROE 高但 ROA 低，说明高回报主要是借钱撑出来的，风险更大。",
        "A company can earn with its own money or with borrowed money. ROA counts both, showing what everything the company has can earn — borrowing can't inflate it.",
        "Compare with ROE: high ROE but low ROA means the high returns mostly come from borrowing, which is riskier.",
    ),
    "roic": (
        "它回答一个最朴素的问题：往这门生意里每投 1 块钱，一年能赚回多少？赚回来的比借钱的利息高，公司越扩张越值钱；比利息还低，扩张反而亏。",
        "最能看出「生意本身好不好」的指标，不管钱是借的还是自己的。用来和 ROE 互相核对。",
        "It answers a simple question: for every $1 put into this business, how much comes back each year? If that beats the interest on borrowed money, growing makes the company more valuable; if not, growing loses money.",
        "The best gauge of whether the business itself is good, whether the money is borrowed or not. Used to cross-check ROE.",
    ),
    "asset_turn": (
        "赚钱有两种路子：一单赚很多，或者一单赚得少、但卖得特别多（比如超市）。这个指标看的是后一种。",
        "帮你看清公司的高回报，是靠一单赚得多，还是靠卖得多。",
        "There are two ways to make money: earn a lot per sale, or earn a little per sale but make a huge number of sales (like a supermarket). This measures the second.",
        "Shows whether a company's returns come from earning a lot per sale or from selling a lot.",
    ),
    "momentum": (
        "股价涨跌反映了市场最近怎么看这家公司。研究发现，最近走得强的股票，接下来一段时间常常还会相对强一些。",
        "前面几个维度看公司本身，动量看市场怎么看它，两边互相补充。我们把 3、6、9、12 个月四段的涨跌平均起来，避免某一段的偶然波动。",
        "Price moves show how the market has been viewing the company lately. Research finds stocks that have been relatively strong often stay relatively strong for a while.",
        "The other factors look at the company itself; momentum looks at how the market sees it. We average the 3-, 6-, 9- and 12-month changes so one odd stretch doesn't dominate.",
    ),
    "revision": (
        "分析师会根据公司最新情况改预测。大家纷纷调高预期，通常说明公司干得比原来想的好。",
        "公司现在好不好，看前面几个维度；最近是在变好还是变差，看这一项。我们看分析师对今年、明年每股收益和今年营收的预测，在 30 天、90 天里改了多少。",
        "Analysts update their forecasts as news comes in. When many raise their expectations, the company is usually doing better than they thought.",
        "The other factors show how the company is doing now; this one shows whether things are getting better or worse lately. We track how much forecasts for this and next year's EPS and this year's revenue changed over 30 and 90 days.",
    ),
    "net_debt_ebitda": (
        "借的钱到期要还，利息要付。负债压得太重的公司，业绩一遇到波动就容易出问题。",
        "最直接的偿债压力指标。EBITDA 为负又有净负债的公司按最差计。",
        "Borrowed money must be repaid with interest. A heavily indebted company is fragile when earnings wobble.",
        "The most direct gauge of repayment pressure. A company with net debt and negative EBITDA is scored as lowest.",
    ),
    "interest_cov": (
        "利息是必须按时付的钱，付不起就会走到违约。",
        "和净负债 / EBITDA 互补：一个看欠多少，一个看每年付不付得起。",
        "Interest must be paid on time; failing to pay leads to default.",
        "Complements net debt / EBITDA: one asks how much is owed, the other whether the yearly cost is affordable.",
    ),
    "current_ratio": (
        "短期的账还不上，再好的长期前景也等不到。很多公司出问题，都是资金一时周转不开。",
        "衡量「近期会不会周转不灵」，和看长期负担的前两项互补。",
        "Without the cash to pay near-term bills, even a good long-term outlook never arrives. Many companies get into trouble because of a short-term cash crunch.",
        "Measures near-term liquidity, complementing the two long-term burden metrics above.",
    ),
    "runway_years": (
        "烧钱的公司，现金见底就要融资或大幅收缩，股东的权益容易被摊薄。",
        "专门盯初创、还没赚钱的公司：增长再快，钱撑不到盈利那天就没有意义。",
        "A cash-burning company that runs out of cash must raise money or cut deeply, often diluting shareholders.",
        "Aimed at early, not-yet-profitable companies: rapid growth means little if the cash runs out before profits arrive.",
    ),
    "cfo_ni": (
        "利润可以靠会计处理做得好看，现金很难作假。利润长期收不回现金的公司，往往藏着风险。",
        "检验利润的质量；亏损公司不参与（比值没有意义）。",
        "Profit can be dressed up by accounting; cash is much harder to fake. Companies whose profit never turns into cash often hide risks.",
        "Tests the quality of earnings. Loss-making companies are excluded because the ratio is meaningless.",
    ),
    "fcf_sbc_m": (
        "股票薪酬不用掏现金，所以不会出现在现金流里，但它会让每一股变得更不值钱。只看现金流，会高估大量发股票薪酬的公司。",
        "和自由现金流利润率对照看：两者差得越大，说明公司越依赖股票薪酬留住员工。",
        "Stock pay costs no cash, so it never shows in cash flow, yet it makes each share worth less. Looking at cash flow alone overstates companies that pay heavily in stock.",
        "Read it next to the plain free cash flow margin: the bigger the gap, the more the company relies on stock pay.",
    ),
}


def why_and_purpose(metric: MetricDef, lang: str) -> tuple[str, str]:
    """返回（为什么重要, 我们为什么用它）。"""
    zh_why, zh_purpose, en_why, en_purpose = _WHY[_concept(metric)]
    return (zh_why, zh_purpose) if lang == "zh" else (en_why, en_purpose)
