import Foundation

/// 基本面动向雷达的「怎么算的」与名单里每只股票的变化说明。口径来源：后端 `quant_research/trend.py`（事实）
/// 与 `trend_radar.py`（入圈规则，门槛随响应 `thresholds` 返回，这里直接读，改门槛不用改文案）。
@MainActor
enum TrendDerivations {
    private static func pp(_ v: Double?) -> String {
        guard let v else { return "—" }
        return String(format: "%+.1f", v) + L("个百分点")
    }

    /// 入圈规则（带当前门槛）。
    static func rules(_ t: QuantTrendRadar, kind: QuantTrendKind, market: StockMarket) -> DerivationResult {
        let th = t.thresholds
        func pct(_ k: String) -> String { DerivationFormat.pct(th[k], digits: 0) }
        switch kind {
        case .estimates:
            let minN = Int(th["min_analysts"] ?? 3)
            let steps: [DerivationStep] = [
                    DerivationStep(title: L("看什么"),
                                   text: L("本财年每股盈利（EPS）的一致预期 = 覆盖这家公司的分析师预测的平均值。比较它现在和 7 / 30 / 90 天前的值。")),
                    DerivationStep(title: L("放哪一圈"),
                                   text: L("近 1 周涨幅够了放最内圈，否则看近 1 个月，再否则看近 3 个月。"),
                                   values: [(L("近1周"), pct("eps_up_7d")), (L("近1月"), pct("eps_up_30d")),
                                            (L("近3月"), pct("eps_up_90d")), (L("至少几位分析师"), "\(minN)")]),
                    DerivationStep(title: L("颜色深浅"),
                                   text: L("上调幅度是该圈门槛的几倍，在当前画出来的公司里排个先后：颜色越深，上调得越多。")),
            ]
            return DerivationResult(
                conclusion: L("预期上调：分析师在调高这家公司本财年的每股盈利预期。"),
                steps: steps + visualSteps(t),
                caveat: market == .us ? nil
                    : L("A 股 / 港股的 1 个月、3 个月预期变化要等我们自己每天存的预期快照攒够（约 11 月起），目前主要是近 1 周。"),
                means: L("市场对这家公司今年能赚多少钱的看法在变好。"),
                notMeans: L("不代表股价会涨：预期可能已经反映在股价里，之后也可能再被调低。"),
                terms: ["EPS", "一致预期"])
        case .quality:
            let steps: [DerivationStep] = [
                    DerivationStep(title: L("怎么比"),
                                   text: L("都用最近 12 个月的口径：最近一季公布后的 12 个月，对比上一季公布时的 12 个月。看营收同比、毛利率、经营利润率、自由现金流利润率各变了几个百分点。")),
                    DerivationStep(title: L("什么算改善"),
                                   text: L("经营利润率或自由现金流利润率提高够多，四项里至少几项变好，而且没有哪一项明显变差。"),
                                   values: [(L("利润率至少提高"), pp(th["quality_margin_pp"])),
                                            (L("至少几项变好"), "\(Int(th["quality_improved_min"] ?? 2))"),
                                            (L("任一项变差不超过"), pp(th["quality_worst_pp"]))]),
                    DerivationStep(title: L("放哪一圈"), text: L("按最近一季财报披露离现在多久：1 周内、1 个月内、3 个月内。")),
                    DerivationStep(title: L("颜色深浅"),
                                   text: L("变好的百分点合计是利润率门槛的几倍，在当前画出来的公司里排个先后：颜色越深，变好得越多。")),
            ]
            return DerivationResult(
                conclusion: L("质地改善：最近一季的财报比上一季更赚钱、增长没有明显放慢。"),
                steps: steps + visualSteps(t),
                caveat: L("单季对比会受季节影响（比如零售的旺季、淡季）；港股多是半年报，换算成季度后变化偏平滑。"),
                means: L("这家公司最近一季赚钱的效率在提高。"),
                notMeans: L("一个季度变好不代表趋势会持续，也不代表股价会涨。"),
                terms: ["毛利率", "经营利润率", "自由现金流"])
        }
    }

    /// 两类共用的最后两步：气泡大小 = 综合等级；精选 = 只画综合等级达到门槛的公司。
    private static func visualSteps(_ t: QuantTrendRadar) -> [DerivationStep] {
        var steps = [DerivationStep(title: L("气泡大小"), text: L("综合等级：A+ 最大，往下每一档小一点，D 及以下最小。气泡里的字母就是综合等级。"))]
        if let grade = t.goodGrade {
            steps.append(DerivationStep(
                title: L("精选"),
                text: L("默认只画综合等级达到门槛的公司，和市场雷达里的基本面名单是同一个门槛：本市场有评级的公司里约前 25%，至少 8 只，不低于 B，整档纳入。点上面的「精选」可以切到全部。"),
                values: [(L("门槛"), L("%@ 及以上", grade))]))
        }
        return steps
    }

    /// 画布上没有气泡时的说明。
    static func emptyText(kind: QuantTrendKind, market: StockMarket) -> String {
        if kind == .estimates && market != .us {
            return L("最近 1 周没有达到门槛的预期上调。A 股 / 港股的 1 个月、3 个月预期变化要等预期快照攒够（约 11 月起）。")
        }
        return kind == .estimates ? L("最近没有达到门槛的预期上调") : L("最近 3 个月没有达到门槛的质地改善")
    }

    /// 名单里一行的变化说明。
    static func factLine(_ item: QuantTrendItem) -> String {
        let f = item.facts
        if item.kind == QuantTrendKind.estimates.rawValue {
            return L("盈利预期 近1周 %@ · 近1月 %@ · 近3月 %@",
                     DerivationFormat.pct(f.epsRev7d), DerivationFormat.pct(f.epsRev30d), DerivationFormat.pct(f.epsRev90d))
        }
        return L("经营利润率 %@ · 现金利润率 %@ · 营收同比 %@", pp(f.dEbitMPp), pp(f.dFcfMPp), pp(f.dRevYoyPp))
    }

    /// 名单里一行的对比期（质地改善）或分析师人数（预期上调）。
    static func contextLine(_ item: QuantTrendItem) -> String {
        let f = item.facts
        if item.kind == QuantTrendKind.estimates.rawValue {
            return L("%lld 位分析师", f.nAnalysts)
        }
        return L("%@ 对比 %@ · 披露于 %@", f.qualityPeriod ?? "—", f.qualityPrevPeriod ?? "—", f.filingDate ?? "—")
    }
}
