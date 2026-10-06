import SwiftUI

/// 宏观卡片四项的「怎么算的」：市场状态 / 情绪 / 驱动因素 / 行业强弱。
/// 文字按每一项单独写，数字取当天真实值（后端 `state.inputs`、驱动因素的 flat_band 等）。
/// 口径来源：app/services/regime（状态）、app/services/macro/drivers.py（驱动因素）、
/// 情绪分是第三方公开指数、这里只展示。改算法时这里的文字要一起改。
@MainActor
enum MacroDerivations {
    typealias Result = DerivationResult

    // MARK: - 市场状态

    static func state(_ s: MacroState, market: StockMarket) -> Result {
        let isUS = market == .us
        let benchmark: String
        switch market {
        case .us: benchmark = L("纳指")
        case .cn: benchmark = L("沪深300")
        case .hk: benchmark = L("盈富基金")
        }
        var inputValues: [(String, String)] = []
        if let i = s.inputs {
            inputValues = [
                (L("%@近 20 日涨跌", benchmark), DerivationFormat.pct(i.ret)),
                (L("%@年化波动", benchmark), DerivationFormat.pct(i.vol, signed: false)),
                isUS ? (L("VIX 恐慌指数"), DerivationFormat.num(i.vix))
                     : (L("20 日 / 60 日波动比"), DerivationFormat.num(i.volRatio, digits: 2)),
                (L("进攻 − 防御（涨幅差）"), DerivationFormat.pct(i.ods)),
                (L("现金 − 风险资产（涨幅差）"), DerivationFormat.pct(i.cf)),
            ]
        }
        let step1Text = isUS
            ? L("原料每天算一次，都看近 20 个交易日：纳指涨跌、纳指波动、VIX 恐慌指数，再加两个「资金流向」指标。进攻篮子 = 科技、可选消费、工业、半导体；防御篮子 = 公用事业、必需消费、医疗；现金篮子 = 短债；篮子内等权。")
            : L("原料每天算一次，都看近 20 个交易日：基准指数涨跌、基准波动、短期 / 长期波动比（这两个市场没有可用的波动率指数，用它代替 VIX），再加两个「资金流向」指标。进攻、防御、现金三个篮子都由等权的 ETF 组成。")
        let steps = [
            DerivationStep(title: L("先取五个原料"), text: step1Text, values: inputValues),
            DerivationStep(title: L("让模型把历史分成三种状态"),
                           text: L("用一个统计模型（隐马尔可夫模型）读历史上的五个原料，让它自己归纳出三种典型状态，不是我们预先划线。模型每个月最后一个交易日用截至当天的全部历史重新估计一次，之后一个月参数固定；当天只用当天及之前的数据，已经出的历史状态不会被未来数据改写。")),
            DerivationStep(title: L("给三种状态命名"),
                           text: L("哪一种最像「大盘涨、波动小、恐慌指数低、资金追进攻、没往现金跑」，就叫逐利；最相反的叫避险；介于两者之间的叫观望。")),
            DerivationStep(title: L("算今天更像哪一种"),
                           text: L("拿今天的五个原料去对照三种状态，给出各自的概率，加起来 100%。"),
                           values: [(L("逐利"), pct(s.pRiskOn)), (L("观望"), pct(s.pNeutral)), (L("避险"), pct(s.pRiskOff))]),
            DerivationStep(title: L("连续确认才算数"),
                           text: L("为避免一天一变，同一种状态要连续 3 个交易日才算确认。现在的「%@」已持续 %lld 个交易日。",
                                   s.labelText, s.daysInState)),
        ]
        let means: String
        switch s.label {
        case "risk_on": means = L("近 20 个交易日，资金更愿意买进攻型的板块（科技、可选消费等），市场整体偏积极。")
        case "risk_off": means = L("近 20 个交易日，资金更偏向防御板块和现金，市场整体偏谨慎。")
        default: means = L("近 20 个交易日，资金没有明显偏向进攻或防守，处在观望。")
        }
        return DerivationResult(
            conclusion: L("当前判定：%@，概率 %@（%@ 收盘数据）", s.labelText, pct(s.probability), s.asOf), steps: steps,
            caveat: L("概率只说「今天更像哪种历史状态」，不预测涨跌，也不是操作建议。模型把高波动当偏避险，急涨急跌的行情里可能和直觉不一致。"),
            means: means,
            notMeans: L("不代表接下来一定会涨或会跌，也不是让你买入或卖出的信号；概率不是「上涨的概率」。"),
            terms: ["市场状态", "逐利", "观望", "避险", "隐马尔可夫模型", "进攻与防御"])
    }

    // MARK: - 情绪（恐慌贪婪）

    static func sentiment(_ p: PanicIndexResponse) -> Result {
        func item(_ title: String, _ snap: PanicIndexSnapshot) -> (String, String) {
            (title, "\(Int(snap.score.rounded())) · \(PanicIndexStyle.ratingLabel(snap.rating))")
        }
        let steps = [
            DerivationStep(title: L("这是一个 0~100 的合成指数"),
                           text: L("由市场动量、股价强度、上涨家数广度、期权看跌 / 看涨比、垃圾债需求、波动率、避险资产需求这七类公开指标，各自折算成 0~100 分后取平均。该指数由第三方公开发布，这里直接展示，不是我们自己算的。")),
            DerivationStep(title: L("分数怎么分档"),
                           text: L("0~24 极度恐慌，25~44 恐慌，45~55 中性，56~75 贪婪，76~100 极度贪婪。"),
                           values: [item(L("当前"), p.current)]),
            DerivationStep(title: L("和一周前、一月前比"),
                           text: L("同一个指数在不同时点的分数，看情绪是在升温还是降温。"),
                           values: [item(L("当前"), p.current), item(L("一周前"), p.previousWeek), item(L("一月前"), p.previousMonth)]),
        ]
        return DerivationResult(
            conclusion: L("当前 %lld 分：%@", Int(p.current.score.rounded()), PanicIndexStyle.ratingLabel(p.current.rating)), steps: steps,
            caveat: L("情绪看的是市场整体的冷暖，和「市场状态」（看资金流向）口径不同，下跌后的修复初期两者常常方向不一致，不是数据错误。"),
            means: L("数字越低说明大家越恐慌，越高说明越贪婪，反映的是当下的心态。"),
            notMeans: L("极度恐慌不一定是底部，极度贪婪也不一定是顶部；它不是买卖信号。"),
            terms: ["恐慌贪婪指数", "VIX", "市场状态"])
    }

    // MARK: - 驱动因素

    static func driver(_ d: MacroDriver) -> Result {
        let unitWord: String
        let band: String
        switch d.unit {
        case "percent": unitWord = L("基点（1 基点 = 0.01%）"); band = d.flatBand.map { String(format: "%.0f bp", $0) } ?? "—"
        case "point": unitWord = L("点"); band = d.flatBand.map { String(format: "%.1f", $0) } ?? "—"
        default: unitWord = L("涨跌幅"); band = d.flatBand.map { String(format: "%.1f%%", $0) } ?? "—"
        }
        var steps: [DerivationStep] = []
        var nowPrev: [(String, String)] = []
        if let v = d.value, let c = d.change, d.unit != "change" {
            let prev = d.unit == "percent" ? v - c / 100 : v - c
            let fmt: (Double) -> String = { d.unit == "percent" ? String(format: "%.2f%%", $0) : String(format: "%.1f", $0) }
            nowPrev = [(L("今天"), fmt(v)), (L("20 个交易日前"), fmt(prev))]
        }
        steps.append(DerivationStep(
            title: L("取两个时点"),
            text: d.unit == "change"
                ? L("这一项没有可靠的点位，用跟踪它的基金价格近似，只看近 20 个交易日的涨跌幅。")
                : L("今天的值，和 20 个交易日前的值。"),
            values: nowPrev))
        steps.append(DerivationStep(
            title: L("算变化"),
            text: L("近 20 个交易日变化，单位：%@。", unitWord),
            values: MacroDetailSheet.changeText(d).map { [(L("近 20 日变化"), $0)] } ?? []))
        steps.append(DerivationStep(
            title: L("判方向"),
            text: L("变化的绝对值小于持平阈值算「持平」；否则大于 0 为上行、小于 0 为下行。"),
            values: [(L("持平阈值"), band),
                     (L("判定"), d.direction == "up" ? L("上行") : d.direction == "down" ? L("下行") : L("持平"))]))
        steps.append(DerivationStep(title: L("判对股票的影响"), text: impactRule(d.key)))
        let conclusion = [d.name, MacroDetailSheet.valueText(d), MacroDetailSheet.changeText(d)].compactMap { $0 }.joined(separator: "  ")
        var terms = ["基点"]
        switch d.key {
        case "us10y": terms = ["美债利率", "基点"]
        case "curve": terms = ["10Y-2Y 利差", "倒挂", "基点"]
        case "vix": terms = ["VIX", "波动率"]
        default: terms = []
        }
        return DerivationResult(
            conclusion: conclusion + "\n" + d.text, steps: steps,
            caveat: L("这是对环境的描述，不是预测或建议；五项各自独立判断，没有加总成一个分数。"),
            means: L("这是影响股票整体估值的外部环境之一，方向变化说明环境在变松或变紧。"),
            notMeans: L("单项变化决定不了股价，几项之间也可能互相抵消。"),
            terms: terms)
    }

    static func impactRule(_ key: String) -> String {
        switch key {
        case "us10y": return L("利率上行对股票偏不利（估值承压，成长股更敏感），下行偏有利，持平不判断。")
        case "curve": return L("利差只描述形态（走阔 / 收窄）、不判断利弊；利差为负叫倒挂，会单独提示。")
        case "dollar": return L("美元走强偏不利（全球资金偏谨慎），走弱偏有利，持平不判断。")
        case "vix": return L("波动率上行偏不利（市场更紧张），回落偏有利，持平不判断。")
        case "oil": return L("油价上涨偏不利（通胀压力上升），下跌偏有利，持平不判断。")
        default: return L("按固定规则判断对股票偏有利、偏不利还是中性，持平不判断。")
        }
    }

    // MARK: - 行业强弱

    static func sector(_ row: SectorRow, market: StockMarket) -> Result {
        let benchmark: String
        switch market {
        case .us: benchmark = L("标普500")
        case .cn: benchmark = L("沪深300")
        case .hk: benchmark = L("恒生指数")
        }
        var steps = [
            DerivationStep(
                title: L("相对强弱 = 行业涨幅 − 大盘涨幅"),
                text: L("取近 20 个交易日，行业涨幅减去%@涨幅，大于 0 说明跑赢大盘，小于 0 说明落后。行业按它从强到弱排序。", benchmark),
                values: row.rsVsMarket.map { [(L("相对强弱"), DerivationFormat.pct($0))] } ?? []),
        ]
        let indexText = market == .us
            ? L("行业用对应的行业基金价格代表。")
            : L("行业没有干净的行业基金，用该行业市值最大的 8 只成分股等权合成一个指数代表。")
        steps.append(DerivationStep(
            title: L("行业状态：每个行业单独算"),
            text: L("%@每个行业单独跑一个和大盘同类的统计模型，原料是行业涨跌、波动、恐慌指标、相对大盘强弱和资金流（成交量加权的收盘位置）；输出逐利 / 观望 / 避险的概率，同样连续 3 个交易日才确认。", indexText),
            values: row.label.map { [(L("当前状态"), SectorBoardList.labelText($0))] } ?? []))
        return DerivationResult(
            conclusion: L("%@：相对大盘 %@", row.name, DerivationFormat.pct(row.rsVsMarket)), steps: steps,
            caveat: L("强弱是近 20 个交易日的相对表现，不预测后续涨跌，也不是操作建议。成分股很少的行业不出强弱。"),
            means: L("最近 20 个交易日，这个行业比大盘走得更好（正数）还是更差（负数）。"),
            notMeans: L("领先不代表接下来继续领先，行业强弱会轮动；行业弱也不代表里面每家公司都差。"),
            terms: ["相对强弱", "逐利", "同行业"])
    }

    private static func pct(_ v: Double) -> String { DerivationFormat.pct(v, digits: 0, signed: false) }
}
