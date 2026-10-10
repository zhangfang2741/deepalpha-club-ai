import Foundation

/// 基本面雷达 / 评级雷达的「怎么算的」与名单里每只股票的变化说明。口径来源：后端 `quant_research/trend.py`（事实）
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
        case .estimates, .estimatesDown:
            let down = kind.isDown
            let minN = Int(th["min_analysts"] ?? 3)
            let steps: [DerivationStep] = [
                    DerivationStep(title: L("看什么"),
                                   text: L("本财年每股盈利（EPS）的一致预期 = 覆盖这家公司的分析师预测的平均值。比较它现在和 7 / 30 / 90 天前的值。")),
                    DerivationStep(title: L("放哪一圈"),
                                   text: down ? L("近 1 周降幅够了放最内圈，否则看近 1 个月，再否则看近 3 个月（门槛和上调同一套，方向相反）。")
                                              : L("近 1 周涨幅够了放最内圈，否则看近 1 个月，再否则看近 3 个月。"),
                                   values: [(L("近1周"), pct("eps_up_7d")), (L("近1月"), pct("eps_up_30d")),
                                            (L("近3月"), pct("eps_up_90d")), (L("至少几位分析师"), "\(minN)")]),
                    DerivationStep(title: L("颜色深浅"),
                                   text: down ? L("下调幅度是该圈门槛的几倍，在当前画出来的公司里排个先后：颜色越深，下调得越多。")
                                              : L("上调幅度是该圈门槛的几倍，在当前画出来的公司里排个先后：颜色越深，上调得越多。")),
            ]
            return DerivationResult(
                conclusion: down ? L("预期下调：分析师在调低这家公司本财年的每股盈利预期。")
                                 : L("预期上调：分析师在调高这家公司本财年的每股盈利预期。"),
                steps: steps + visualSteps(t, down: down),
                caveat: market == .us ? nil
                    : L("A 股 / 港股的 1 个月、3 个月预期变化要等我们自己每天存的预期快照攒够（约 11 月起），目前主要是近 1 周。"),
                means: down ? L("市场对这家公司今年能赚多少钱的看法在变差。")
                            : L("市场对这家公司今年能赚多少钱的看法在变好。"),
                notMeans: down ? L("不代表股价会跌：预期可能已经反映在股价里，之后也可能再被调高。")
                               : L("不代表股价会涨：预期可能已经反映在股价里，之后也可能再被调低。"),
                terms: ["EPS", "一致预期"])
        case .rating, .ratingDown:
            let down = kind.isDown
            let minSteps = Int(th["rating_min_steps"] ?? 1)
            let steps: [DerivationStep] = [
                DerivationStep(title: L("看什么"),
                               text: L("我们给每家公司的综合等级（A+ 最高、F 最低，共 13 档），每天评一次。比较它现在和最近 1 周 / 1 个月 / 3 个月里最早一次评级。")),
                DerivationStep(title: down ? L("什么算下降") : L("什么算上升"),
                               text: down ? L("同一套评级方法下，综合等级比窗口开头至少低几档。评级方法升级前后不是同一把尺子，不拿来比。")
                                          : L("同一套评级方法下，综合等级比窗口开头至少高几档。评级方法升级前后不是同一把尺子，不拿来比。"),
                               values: [(down ? L("至少降几档") : L("至少升几档"), "\(minSteps)")]),
                DerivationStep(title: L("放哪一圈"),
                               text: L("看多长时间里变的：1 周内变了放最内圈，否则 1 个月内，再否则 3 个月内。")),
                DerivationStep(title: L("颜色深浅"),
                               text: down ? L("降的档数越多颜色越深；档数一样时，综合分跌得多的略深。")
                                          : L("升的档数越多颜色越深；档数一样时，综合分涨得多的略深。")),
            ]
            return DerivationResult(
                conclusion: down ? L("等级下降：我们给这家公司的综合等级比前一段时间更低。")
                                 : L("等级上升：我们给这家公司的综合等级比前一段时间更高。"),
                steps: steps + visualSteps(t, down: down),
                caveat: L("评级方法最近调整过几次，每次调整后要重新攒几天历史才有数据，所以刚升级时这里可能是空的；A 股 / 港股的评级历史比美股更短。"),
                means: down ? L("和同类公司比，这家公司的综合表现在变差。")
                            : L("和同类公司比，这家公司的综合表现在变好。"),
                notMeans: down ? L("不代表股价会跌：等级是和同行比出来的相对位置，只反映已披露的财务与预期。")
                               : L("不代表股价会涨：等级是和同行比出来的相对位置，只反映已披露的财务与预期。"),
                terms: ["综合等级"])
        case .analystUp, .analystDown:
            let down = kind.isDown
            let steps: [DerivationStep] = [
                DerivationStep(title: L("看什么"),
                               text: L("各家券商对这只股票的评级动作：上调（比如从持有升到买入）和下调（反过来）。同一家券商在窗口内多次调整只算一次，取最新的一次。")),
                DerivationStep(title: L("什么算净上调 / 净下调"),
                               text: L("窗口内上调的家数减去下调的家数，大于 0 是净上调，小于 0 是净下调；一样多不画。"),
                               values: [(L("至少净差几家"), "\(Int(th["analyst_min_net"] ?? 1))")]),
                DerivationStep(title: L("放哪一圈"),
                               text: L("近 1 周就已经净上调（净下调）的放最内圈，否则看近 1 个月，再否则近 3 个月。同一只股票上调和下调都有时，两边的列表里各出现一次。")),
                DerivationStep(title: L("颜色深浅"),
                               text: down ? L("净下调的家数越多颜色越深；家数一样时，越近的略深。")
                                          : L("净上调的家数越多颜色越深；家数一样时，越近的略深。")),
            ]
            return DerivationResult(
                conclusion: down ? L("评级下调：近期有券商把这只股票的评级调低。")
                                 : L("评级上调：近期有券商把这只股票的评级调高。"),
                steps: steps + visualSteps(t, down: down),
                caveat: L("目前只有美股有券商评级变动数据；券商的评级动作有时滞后于股价，也可能只是重申。"),
                means: down ? L("更多专业机构对这只股票的看法在变谨慎。") : L("更多专业机构对这只股票的看法在变乐观。"),
                notMeans: down ? L("不代表股价会跌：券商评级常常滞后于股价，也不总是对的。")
                               : L("不代表股价会涨：券商评级常常滞后于股价，也不总是对的。"),
                terms: ["分析师评级"])
        }
    }

    /// 两类共用的最后两步：气泡大小 = 综合等级；精选 = 只画综合等级达到门槛的公司。
    private static func visualSteps(_ t: QuantTrendRadar, down: Bool) -> [DerivationStep] {
        var steps = [DerivationStep(title: L("红与绿"),
                                    text: down ? L("绿色 = 向差的一侧（下调 / 下降），和缠论雷达里红买绿卖同一套颜色，只表示方向。")
                                               : L("红色 = 向好的一侧（上调 / 上升），和缠论雷达里红买绿卖同一套颜色，只表示方向。")),
                     DerivationStep(title: L("气泡大小"), text: L("综合等级：在当前画出来的公司里，等级最高的最大、最低的最小，中间按名次均分。气泡里的字母就是综合等级。画布最多画 12 个，其余在「查看名单与变化」里。"))]
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
        switch kind {
        case .estimates, .estimatesDown:
            if market != .us {
                return L("最近 1 周没有达到门槛的预期变化。A 股 / 港股的 1 个月、3 个月预期变化要等预期快照攒够（约 11 月起）。")
            }
            return kind == .estimates ? L("最近没有达到门槛的预期上调") : L("最近没有达到门槛的预期下调")
        case .rating, .ratingDown:
            return kind == .rating
                ? L("最近 3 个月没有综合等级上升的公司。评级方法升级后要重新攒几天历史，刚升级时这里会是空的。")
                : L("最近 3 个月没有综合等级下降的公司。评级方法升级后要重新攒几天历史，刚升级时这里会是空的。")
        case .analystUp: return L("最近 3 个月这个股票池里没有被券商净上调评级的股票")
        case .analystDown: return L("最近 3 个月这个股票池里没有被券商净下调评级的股票")
        }
    }

    /// 名单里一行的变化说明。
    static func factLine(_ item: QuantTrendItem) -> String {
        if let a = item.analyst {
            return L("近%lld天 · 上调 %lld 家 · 下调 %lld 家", a.windowDays, a.up, a.down)
        }
        if let r = item.rating {
            var line = item.kind == QuantTrendKind.ratingDown.rawValue
                ? L("综合等级 %@ → %@ · 降 %lld 档", r.fromGrade, r.toGrade, r.steps)
                : L("综合等级 %@ → %@ · 升 %lld 档", r.fromGrade, r.toGrade, r.steps)
            if let d = r.scoreDelta { line += " · " + L("综合分 %@", String(format: "%+.1f", d)) }
            return line
        }
        let f = item.facts
        if item.kind == QuantTrendKind.estimates.rawValue || item.kind == QuantTrendKind.estimatesDown.rawValue {
            return L("盈利预期 近1周 %@ · 近1月 %@ · 近3月 %@",
                     DerivationFormat.pct(f.epsRev7d), DerivationFormat.pct(f.epsRev30d), DerivationFormat.pct(f.epsRev90d))
        }
        return L("经营利润率 %@ · 现金利润率 %@ · 营收同比 %@", pp(f.dEbitMPp), pp(f.dFcfMPp), pp(f.dRevYoyPp))
    }

    /// 名单里一行的对比期（评级改善）或分析师人数（预期上调）。
    static func contextLine(_ item: QuantTrendItem) -> String {
        if let a = item.analyst {
            let firms = a.firms.joined(separator: "、")
            let last = a.lastDate.map { L("最近一次 %@", $0) } ?? ""
            return [firms, last].filter { !$0.isEmpty }.joined(separator: " · ")
        }
        if let r = item.rating { return L("评级日 %@ 对比 %@", r.toDate, r.fromDate) }
        let f = item.facts
        if item.kind == QuantTrendKind.estimates.rawValue || item.kind == QuantTrendKind.estimatesDown.rawValue {
            return L("%lld 位分析师", f.nAnalysts)
        }
        return L("%@ 对比 %@ · 披露于 %@", f.qualityPeriod ?? "—", f.qualityPrevPeriod ?? "—", f.filingDate ?? "—")
    }
}
