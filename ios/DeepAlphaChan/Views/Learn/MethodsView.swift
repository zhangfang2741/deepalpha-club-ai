import SwiftUI

/// 学习页「方法说明」：App 里每个量化结论是怎么算的，集中放在这里（不再散落在各页面）。
/// 这里只讲方法本身、不带某一天的真实数字；文字与 MacroDerivations / RadarDerivations / SignalDerivation 同源，
/// 改算法时这几处要一起改。
@MainActor
enum MethodDerivations {
    typealias Result = DerivationResult

    struct Item: Identifiable {
        let id: String
        let title: String
        let subtitle: String
        let result: Result
    }

    static var groups: [(title: String, items: [Item])] {
        [
            (L("市场与行业"), [marketState, sentiment, drivers, sector]),
            (L("基本面"), [fundamentals]),
            (L("雷达与买卖点"), [signalTypes, strength, RadarItem.resonance, RadarItem.analyst]),
        ]
    }

    private enum RadarItem {
        static var resonance: Item {
            Item(id: "resonance", title: L("共振怎么算"), subtitle: L("日线方向和 30 分钟买卖点是否一致"), result: RadarDerivations.resonance)
        }
        static var analyst: Item {
            Item(id: "analyst", title: L("角标怎么算"), subtitle: L("近 90 天券商净上调 / 净下调"), result: RadarDerivations.analyst)
        }
    }

    private static var strength: Item {
        Item(id: "strength", title: L("深浅怎么算"), subtitle: L("气泡颜色深浅 = 信号强弱"), result: RadarDerivations.strength)
    }

    // MARK: - 市场状态

    private static var marketState: Item {
        let steps = [
            DerivationStep(
                title: L("先取五个原料"),
                text: L("原料每天算一次，都看近 20 个交易日：纳指涨跌、纳指波动、VIX 恐慌指数，再加两个「资金流向」指标。进攻篮子 = 科技、可选消费、工业、半导体；防御篮子 = 公用事业、必需消费、医疗；现金篮子 = 短债；篮子内等权。")),
            DerivationStep(
                title: L("让模型把历史分成三种状态"),
                text: L("用一个统计模型（隐马尔可夫模型）读历史上的五个原料，让它自己归纳出三种典型状态，不是我们预先划线。模型每个月最后一个交易日用截至当天的全部历史重新估计一次，之后一个月参数固定；当天只用当天及之前的数据，已经出的历史状态不会被未来数据改写。")),
            DerivationStep(
                title: L("给三种状态命名"),
                text: L("哪一种最像「大盘涨、波动小、恐慌指数低、资金追进攻、没往现金跑」，就叫逐利；最相反的叫避险；介于两者之间的叫观望。")),
            DerivationStep(
                title: L("算今天更像哪一种"),
                text: L("拿今天的五个原料去对照三种状态，给出各自的概率，加起来 100%。")),
            DerivationStep(
                title: L("连续确认才算数"),
                text: L("为避免一天一变，同一种状态要连续 3 个交易日才算确认。")),
        ]
        return Item(
            id: "market", title: L("市场状态怎么算"), subtitle: L("逐利 / 观望 / 避险，和它的概率"),
            result: DerivationResult(
                conclusion: L("市场状态 = 近 20 个交易日里，今天更像哪一种历史状态"), steps: steps,
                caveat: L("概率只说「今天更像哪种历史状态」，不预测涨跌，也不是操作建议。模型把高波动当偏避险，急涨急跌的行情里可能和直觉不一致。A 股、港股用沪深 300、盈富基金做基准，没有可用的波动率指数，用 20 日 / 60 日波动比代替。"),
                means: L("近 20 个交易日，资金更愿意买进攻型的板块（科技、可选消费等），市场整体偏积极。"),
                notMeans: L("不代表接下来一定会涨或会跌，也不是让你买入或卖出的信号；概率不是「上涨的概率」。"),
                terms: ["市场状态", "逐利", "观望", "避险", "隐马尔可夫模型", "进攻与防御"]))
    }

    // MARK: - 情绪

    private static var sentiment: Item {
        let steps = [
            DerivationStep(
                title: L("这是一个 0~100 的合成指数"),
                text: L("由市场动量、股价强度、上涨家数广度、期权看跌 / 看涨比、垃圾债需求、波动率、避险资产需求这七类公开指标，各自折算成 0~100 分后取平均。该指数由第三方公开发布，这里直接展示，不是我们自己算的。")),
            DerivationStep(
                title: L("分数怎么分档"),
                text: L("0~24 极度恐慌，25~44 恐慌，45~55 中性，56~75 贪婪，76~100 极度贪婪。")),
            DerivationStep(
                title: L("和一周前、一月前比"),
                text: L("同一个指数在不同时点的分数，看情绪是在升温还是降温。")),
        ]
        return Item(
            id: "sentiment", title: L("情绪分怎么算"), subtitle: L("恐慌贪婪指数，第三方公开指数"),
            result: DerivationResult(
                conclusion: L("情绪分 = 市场整体的冷暖，0~100 分"), steps: steps,
                caveat: L("情绪看的是市场整体的冷暖，和「市场状态」（看资金流向）口径不同，下跌后的修复初期两者常常方向不一致，不是数据错误。"),
                means: L("数字越低说明大家越恐慌，越高说明越贪婪，反映的是当下的心态。"),
                notMeans: L("极度恐慌不一定是底部，极度贪婪也不一定是顶部；它不是买卖信号。"),
                terms: ["恐慌贪婪指数", "VIX", "市场状态"]))
    }

    // MARK: - 驱动因素

    private static var drivers: Item {
        let steps = [
            DerivationStep(title: L("取两个时点"), text: L("今天的值，和 20 个交易日前的值。")),
            DerivationStep(
                title: L("判方向"),
                text: L("变化的绝对值小于持平阈值算「持平」；否则大于 0 为上行、小于 0 为下行。")),
            DerivationStep(title: L("美债利率"), text: MacroDerivations.impactRule("us10y")),
            DerivationStep(title: L("10Y-2Y 利差"), text: MacroDerivations.impactRule("curve")),
            DerivationStep(title: L("美元"), text: MacroDerivations.impactRule("dollar")),
            DerivationStep(title: L("波动率"), text: MacroDerivations.impactRule("vix")),
            DerivationStep(title: L("油价"), text: MacroDerivations.impactRule("oil")),
        ]
        return Item(
            id: "drivers", title: L("驱动因素怎么算"), subtitle: L("利率、利差、美元、波动率、油价"),
            result: DerivationResult(
                conclusion: L("驱动因素 = 五项外部环境各自近 20 个交易日的变化"), steps: steps,
                caveat: L("这是对环境的描述，不是预测或建议；五项各自独立判断，没有加总成一个分数。"),
                means: L("这是影响股票整体估值的外部环境之一，方向变化说明环境在变松或变紧。"),
                notMeans: L("单项变化决定不了股价，几项之间也可能互相抵消。"),
                terms: ["美债利率", "10Y-2Y 利差", "倒挂", "VIX", "基点"]))
    }

    // MARK: - 行业强弱

    private static var sector: Item {
        let steps = [
            DerivationStep(
                title: L("相对强弱 = 行业涨幅 − 大盘涨幅"),
                text: L("取近 20 个交易日，行业涨幅减去大盘涨幅，大于 0 说明跑赢大盘，小于 0 说明落后。行业按它从强到弱排序。")),
            DerivationStep(
                title: L("行业用什么代表"),
                text: L("美股用对应的行业基金价格代表；A 股、港股没有干净的行业基金，用该行业市值最大的 8 只成分股等权合成一个指数代表。")),
            DerivationStep(
                title: L("行业状态：每个行业单独算"),
                text: L("每个行业单独跑一个和大盘同类的统计模型，原料是行业涨跌、波动、恐慌指标、相对大盘强弱和资金流（成交量加权的收盘位置）；输出逐利 / 观望 / 避险的概率，同样连续 3 个交易日才确认。")),
        ]
        return Item(
            id: "sector", title: L("行业强弱怎么算"), subtitle: L("相对大盘的强弱，和行业状态"),
            result: DerivationResult(
                conclusion: L("行业强弱 = 近 20 个交易日，行业相对大盘的表现"), steps: steps,
                caveat: L("强弱是近 20 个交易日的相对表现，不预测后续涨跌，也不是操作建议。成分股很少的行业不出强弱。"),
                means: L("最近 20 个交易日，这个行业比大盘走得更好（正数）还是更差（负数）。"),
                notMeans: L("领先不代表接下来继续领先，行业强弱会轮动；行业弱也不代表里面每家公司都差。"),
                terms: ["相对强弱", "逐利", "同行业"]))
    }

    // MARK: - 基本面门槛

    private static var fundamentals: Item {
        let share = DerivationFormat.pct(0.25, digits: 0, signed: false)
        let steps = [
            DerivationStep(
                title: L("给每只股票一个综合等级"),
                text: L("估值、成长、盈利能力、动量、EPS 修正五个维度，每个维度是这只股票在同行业里的百分位（越靠前分越高），五项取平均，再对应到 A+ 到 F 共 13 档字母。任一维度为 F 时，综合等级最高 C+。点进个股详情的「基本面研究」能看到每一项。")),
            DerivationStep(
                title: L("数一数有评级的股票"),
                text: L("只统计当前这个指数里已经有综合等级的股票。")),
            DerivationStep(
                title: L("划线：取前 %@，至少 %lld 只", share, 8),
                text: L("目标只数 = 有评级股票的前 %@（至少 %lld 只）。从最高等级往下累计各等级的只数，累计到达目标的那一档就是门槛；同一等级整档纳入、不在档内切；门槛不低于 %@，小池子或整体偏弱的池子不凑数。",
                        share, 8, "B")),
            DerivationStep(
                title: L("只用当前等级"),
                text: L("用的是每只股票当前的等级，不是信号出现那天的；评级暂时读取失败时不做筛选，雷达照常显示全部信号。")),
        ]
        return Item(
            id: "fundamentals", title: L("基本面怎么算"), subtitle: L("综合等级，和雷达上的「X 及以上」门槛"),
            result: DerivationResult(
                conclusion: L("基本面 = 综合等级靠前的股票，门槛随股票池自动调整"), steps: steps,
                caveat: L("基本面靠前只是缩小观察范围，不是推荐名单，也不预测涨跌。门槛随股票池大小自动调整，不同指数的门槛不一样。"),
                means: L("按公开的财务和预期数据，这些公司在同行业里综合表现靠前。"),
                notMeans: L("不是推荐名单；基本面好也可能股价已经很高，或者短期被市场冷落。"),
                terms: ["基本面", "综合等级", "百分位", "同行业", "盈利预期修正"]))
    }

    // MARK: - 买卖点类型

    private static var signalTypes: Item {
        let steps = [
            DerivationStep(
                title: L("一类：趋势背驰"),
                text: L("价格先走出至少两个依次下移、互不重叠的中枢（A 和 B），并已向下离开 B。")
                    + "\n" + L("b 段 = A 与 B 之间的那一段，c 段 = 离开 B 的这一段。各自把 MACD 红绿柱的面积相加，再用 c 段除以 b 段。")
                    + "\n" + L("c 段把价格推到新低，但面积比小于 100%，说明这一段下跌的力气比上一段小，这就是趋势背驰，一类买点成立的条件。")),
            DerivationStep(
                title: L("二类：一类后的第一次回头"),
                text: L("一买之后价格先反弹、再第一次回落，回落的低点没有跌破一买的低点，就是二买。")),
            DerivationStep(
                title: L("三类：离开中枢后的第一次回头"),
                text: L("回落的低点仍在中枢上沿之上，说明中枢上沿成了支撑，就是三买。")),
            DerivationStep(
                title: L("走完再确认"),
                text: L("这一笔走完、并且反方向的下一笔已经开始成形，才算成立，所以它比价格转折晚几天出现。后面如果价格继续创新极值，这个一类就作废。")),
            DerivationStep(
                title: L("卖点是反过来"),
                text: L("以上按买点讲，卖点把方向整体翻转：上涨趋势里创新高但力气更小是一卖，其余同理。")),
        ]
        return Item(
            id: "signals", title: L("买卖点怎么识别"), subtitle: L("一类、二类、三类各自的判定"),
            result: DerivationResult(
                conclusion: L("买卖点 = 缠论对价格结构的一次观测，按严格口径识别"), steps: steps,
                caveat: L("买卖点只是缠论对价格结构的一次观测，不预测涨跌，也不是操作建议。个股的分析页上，每个信号还能看到它自己的真实数字。"),
                means: L("价格走势里出现了符合定义的结构位置。"),
                notMeans: L("不保证后续会涨或会跌，也不是买卖指令。"),
                terms: ["趋势背驰", "中枢", "MACD", "二买", "三买", "结构信号"]))
    }
}

/// 方法说明列表页：学习页点进来，按组列出所有「怎么算的」。
struct MethodsView: View {
    var body: some View {
        ScrollView {
            VStack(spacing: 10) {
                Text(L("App 里每个算出来的结论，都能在这里看到是怎么得出的。这里讲方法本身；某一只股票、某一天的具体数字，在对应的页面里。"))
                    .font(.footnote).foregroundColor(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 8)
                ForEach(Array(MethodDerivations.groups.enumerated()), id: \.offset) { _, group in
                    Text(group.title)
                        .font(.headline).foregroundColor(Theme.textPrimary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 8).padding(.top, 10)
                    ForEach(group.items) { item in
                        NavigationLink { MethodDetailView(item: item) } label: { row(item) }
                            .buttonStyle(.plain)
                    }
                }
                Text(L("以上为知识讲解，仅供学习参考，不构成投资建议。"))
                    .font(.caption2).foregroundColor(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 8).padding(.top, 8)
            }
            .padding(.horizontal, Theme.contentHInset)
            .padding(.vertical, Theme.contentVInset)
        }
        .background(Theme.background)
        .navigationTitle(L("方法说明"))
        .navigationBarTitleDisplayMode(.inline)
    }

    private func row(_ item: MethodDerivations.Item) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(item.title).font(.subheadline.weight(.semibold)).foregroundColor(Theme.textPrimary)
                Text(item.subtitle).font(.caption).foregroundColor(Theme.textSecondary).multilineTextAlignment(.leading)
            }
            Spacer(minLength: 8)
            Image(systemName: "chevron.right").font(.caption).foregroundColor(Theme.textSecondary)
        }
        .padding(14)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

struct MethodDetailView: View {
    let item: MethodDerivations.Item

    var body: some View {
        ScrollView {
            DerivationContent(result: item.result)
                .padding(.horizontal, Theme.contentHInset)
                .padding(.vertical, Theme.contentVInset)
        }
        .background(Theme.background)
        .navigationTitle(item.title)
        .navigationBarTitleDisplayMode(.inline)
    }
}
