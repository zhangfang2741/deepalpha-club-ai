import SwiftUI

/// 雷达上的量化指标「怎么算的」：基本面门槛、共振标记、券商角标、气泡深浅。
/// 口径来源：app/services/signal_radar/quality_view.py（门槛）、app/services/chan/sub_level.py（共振）、
/// analyst_events.py（角标）、chan/signals.py（强弱）。改算法时这里的文字要一起改。
@MainActor
enum RadarDerivations {
    typealias Result = DerivationResult

    // MARK: - 基本面门槛

    static func fundamentals(_ r: SignalRadarResponse) -> Result? {
        guard let threshold = r.qualityThreshold, !threshold.isEmpty else { return nil }
        let rated = r.qualityRatedCount ?? 0
        let share = r.qualityShare ?? 0.25
        let minCount = r.qualityMinCount ?? 8
        let floor = r.qualityFloor ?? "B"
        let target = max(minCount, Int((Double(rated) * share).rounded(.up)))
        let steps = [
            DerivationStep(
                title: L("给每只股票一个综合等级"),
                text: L("估值、成长、盈利能力、动量、EPS 修正、财务稳健六个维度，每个维度是这只股票在同行业里的百分位（越靠前分越高），再按公司所处阶段加权平均（成长期更看重增速，成熟期更看重估值和赚钱能力），对应到 A+ 到 F 共 13 档字母。重要维度为 F 时，综合等级最高 C+。点进个股详情的「基本面研究」能看到每一项和各自的占比。")),
            DerivationStep(
                title: L("数一数有评级的股票"),
                text: L("只统计当前这个指数里已经有综合等级的股票。"),
                values: [(L("有评级的只数"), "\(rated)")]),
            DerivationStep(
                title: L("划线：取前 %@，至少 %lld 只", DerivationFormat.pct(share, digits: 0, signed: false), minCount),
                text: L("目标只数 = 有评级股票的前 %@（至少 %lld 只）。从最高等级往下累计各等级的只数，累计到达目标的那一档就是门槛；同一等级整档纳入、不在档内切；门槛不低于 %@，小池子或整体偏弱的池子不凑数。",
                        DerivationFormat.pct(share, digits: 0, signed: false), minCount, floor),
                values: [(L("目标只数"), "\(target)"), (L("门槛"), L("%@ 及以上", threshold)),
                         (L("达标只数"), "\(r.qualityGoodCount ?? 0)")]),
            DerivationStep(
                title: L("只用当前等级"),
                text: L("用的是每只股票当前的等级，不是信号出现那天的；评级暂时读取失败时不做筛选，雷达照常显示全部信号。")),
        ]
        return DerivationResult(
            conclusion: L("基本面：%lld 只达标，门槛 %@ 及以上", r.qualityGoodCount ?? 0, threshold), steps: steps,
            caveat: L("基本面靠前只是缩小观察范围，不是推荐名单，也不预测涨跌。门槛随股票池大小自动调整，不同指数的门槛不一样。"),
            means: L("按公开的财务和预期数据，这些公司在同行业里综合表现靠前。"),
            notMeans: L("不是推荐名单；基本面好也可能股价已经很高，或者短期被市场冷落。"),
            terms: ["基本面", "综合等级", "百分位", "同行业", "盈利预期修正"])
    }

    // MARK: - 共振标记

    static var resonance: Result {
        let steps = [
            DerivationStep(
                title: L("先定大级别的方向"),
                text: L("取日线的形态倾向：由末笔方向、线段方向、中枢位置、背驰、量价这几项各给一个正负分，加权相加；总分够大偏多，够小偏空，居中算僵持。")),
            DerivationStep(
                title: L("再看小级别近期的买卖点"),
                text: L("在 30 分钟线上，找最近两个交易日出现的买卖点；同时有买点和卖点时，以最新的一个为准。")),
            DerivationStep(
                title: L("对一对方向"),
                text: L("日线偏多、30 分钟又出现买点（或日线偏空、30 分钟出现卖点），方向一致，叫「共振」；方向相反叫「逆势」；30 分钟还没有买卖点、或日线方向僵持，叫「等待」；30 分钟数据取不到叫「不可用」。")),
        ]
        return DerivationResult(
            conclusion: L("共振 = 日线方向和 30 分钟买卖点一致"), steps: steps,
            caveat: L("共振只说两个级别方向一致，不表示后续一定上涨或下跌。盘中每 30 分钟刷新一次。"),
            means: L("大小两个时间周期的方向一致，信号更「同频」。"),
            notMeans: L("不保证后续会涨或会跌，也不是买卖指令。"),
            terms: ["共振", "次级别", "结构信号"])
    }

    // MARK: - 券商角标

    static var analyst: Result {
        let steps = [
            DerivationStep(
                title: L("取近 90 天的评级变动"),
                text: L("只看券商对这只股票的评级调整：上调（比如从中性调到买入）和下调，维持原评级不算。")),
            DerivationStep(
                title: L("相减得到净值"),
                text: L("净值 = 上调家数 − 下调家数。大于 0 画「▲n」（红），小于 0 画「▼n」（绿），等于 0 或没有数据就不画。")),
            DerivationStep(
                title: L("只做美股"),
                text: L("A 股的研报没有上调 / 下调字段，港股只有各券商最新的评级，所以这个角标只对美股显示。")),
        ]
        return DerivationResult(
            conclusion: L("角标 = 近 90 天券商净上调 / 净下调家数"), steps: steps,
            caveat: L("只是评级调整次数的事实陈列，不代表评级对错，也不预测涨跌。"),
            means: L("近 90 天里，有几家券商调高（▲）或调低（▼）了对这只股票的评级。"),
            notMeans: L("券商也会看错，评级变化不是买卖建议。"),
            terms: ["券商评级"])
    }

    // MARK: - 气泡深浅

    static var strength: Result {
        let steps = [
            DerivationStep(
                title: L("一类：统一标「中」"),
                text: L("一类是趋势背驰。缠论原文只有「面积更小即背驰」，没有强弱分档；我们用两个年代约 2000 个信号检验过，面积比和后续收益没有关系，所以不再分档，一律标「中」。")),
            DerivationStep(
                title: L("二、三类：按中枢和落点定"),
                text: L("看所靠中枢的级别（线段级比笔级强），和回落（反弹）的落点离中枢边界有多远（越远越强），两项加权后分强 / 中 / 弱。")),
            DerivationStep(
                title: L("颜色深浅"),
                text: L("红买绿卖不变，强弱只改颜色的深浅：越强越深，越弱越浅。")),
        ]
        return DerivationResult(
            conclusion: L("深浅 = 信号强弱（强 / 中 / 弱）"), steps: steps,
            caveat: L("强弱描述的是这个结构自身的坚决程度，不是预期收益的大小。"),
            means: L("颜色越深，说明这个结构形态本身越清晰、越坚决。"),
            notMeans: L("不是预期收益的大小：颜色深不等于赚得多，也不等于更可能成功。"),
            terms: ["结构信号", "买卖点", "趋势背驰"])
    }
}
