import SwiftUI

// 量化研究的「点哪儿解释哪儿」：任何等级、分数、术语都可以点开，看到的是针对这一处、
// 带本股真实数字的解释，而不是一份通用说明。

// MARK: - 等级标尺

/// 13 档等级标尺，与后端 grading.py 的 BANDS / HYSTERESIS、scoring.py 的 CAP_THRESHOLD /
/// CAP_CEILING / MIN_SAMPLE 保持一致（tests/services/quant_research/test_education.py 解析本文件守护）。
enum QuantGradeScale {
    static let bands: [(min: Double, grade: String)] = [
        (93, "A+"), (86, "A"), (80, "A-"), (73, "B+"), (66, "B"), (60, "B-"),
        (53, "C+"), (46, "C"), (40, "C-"), (33, "D+"), (26, "D"), (20, "D-"), (0, "F"),
    ]
    static let hysteresis: Double = 2
    static let capThreshold: Double = 20
    static let capCeiling = "C+"
    static let capMinWeightPct = 15   // 综合分里占比不低于它的维度才有一票否决权（对齐后端 scoring.CAP_MIN_WEIGHT）
    static let minSample = 20

    static func grade(for score: Double) -> String {
        bands.first { score >= $0.min }?.grade ?? "F"
    }

    /// 等级对应的分数区间 [下限, 上限)。
    static func range(of grade: String) -> (lo: Double, hi: Double)? {
        guard let i = bands.firstIndex(where: { $0.grade == grade }) else { return nil }
        return (bands[i].min, i == 0 ? 100 : bands[i - 1].min)
    }

    /// 字母大档的大白话含义。
    static func tierMeaning(_ grade: String?) -> String? {
        switch grade?.first {
        case "A": return L("约前 20%：在同板块里明显领先")
        case "B": return L("前 20% ~ 40%：好于多数同行")
        case "C": return L("居中：和同行差不多")
        case "D": return L("后 20% ~ 40%：弱于多数同行")
        case "F": return L("约后 20%：在同板块里明显落后")
        default: return nil
        }
    }

    static func fmt(_ v: Double) -> String {
        v == v.rounded() ? String(format: "%.0f", v) : String(format: "%.1f", v)
    }
}

// MARK: - 点击弹出解释

extension View {
    /// 点击弹出解释（底部弹层，可上拉 / 滚动）；enabled 为 false（如分享长图）时原样显示。
    func quantExplain<C: View>(_ title: String, enabled: Bool = true,
                               @ViewBuilder content: @escaping () -> C) -> some View {
        modifier(QuantExplainModifier(title: title, enabled: enabled, explanation: content))
    }
}

private struct QuantExplainModifier<C: View>: ViewModifier {
    let title: String
    let enabled: Bool
    @ViewBuilder let explanation: () -> C
    @State private var showing = false

    func body(content: Content) -> some View {
        if enabled {
            Button { showing = true } label: { content.contentShape(Rectangle()) }
                .buttonStyle(.plain)
                .accessibilityHint(L("查看解释"))
                // 用底部弹层而不是 popover 气泡：气泡贴着屏幕底部 / 嵌在半屏弹层里时，系统只给它很小的空间，
                // 内容被压扁截断（标题、P10 / P90 看不到）还盖住下面的界面，且与深色卡片颜色太近；
                // 弹层高度固定可预期，放不下就上拉 / 滚动。
                .sheet(isPresented: $showing) {
                    NavigationStack {
                        ScrollView {
                            VStack(alignment: .leading, spacing: 12) {
                                explanation()
                            }
                            .padding(16)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .background(Theme.background)
                        .navigationTitle(title)
                        .navigationBarTitleDisplayMode(.inline)
                        .toolbar {
                            ToolbarItem(placement: .topBarTrailing) { Button(L("完成")) { showing = false } }
                        }
                    }
                    .presentationDetents([.medium, .large])
                    .presentationDragIndicator(.visible)
                    .presentationBackground(Theme.background)
                }
        } else {
            content
        }
    }
}

/// 可点处的小提示符号，提示「这里能点开看解释」。
struct QuantInfoMark: View {
    var body: some View {
        Image(systemName: "info.circle").font(.system(size: 10)).foregroundStyle(Theme.textSecondary.opacity(0.8))
            .accessibilityHidden(true)
    }
}

// MARK: - 解释内容的积木

/// 一段解释文字。
struct QuantExplainText: View {
    let text: String
    var secondary = false

    var body: some View {
        Text(text).font(QuantTypography.body)
            .foregroundStyle(secondary ? Theme.textSecondary : Theme.textPrimary.opacity(0.92))
            .lineSpacing(3).fixedSize(horizontal: false, vertical: true)
    }
}

/// 0~100 的五档色带 + 本股位置标记，直观看出分数落在哪一档。
struct QuantBandScale: View {
    let score: Double

    private let tiers: [(lo: Double, hi: Double, letter: String)] = [
        (0, 20, "F"), (20, 40, "D"), (40, 60, "C"), (60, 80, "B"), (80, 100, "A"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            GeometryReader { geo in
                let w = geo.size.width
                ZStack(alignment: .leading) {
                    HStack(spacing: 2) {
                        ForEach(tiers, id: \.letter) { t in
                            Text(t.letter).font(.system(size: 10, weight: .semibold))
                                .foregroundStyle(QuantGradeStyle.color(t.letter))
                                .frame(maxWidth: .infinity, minHeight: 18)
                                .background(QuantGradeStyle.color(t.letter).opacity(0.15))
                        }
                    }
                    .clipShape(RoundedRectangle(cornerRadius: 4))
                    Rectangle().fill(Theme.textPrimary).frame(width: 2, height: 24)
                        .offset(x: min(max(w * CGFloat(score / 100) - 1, 0), w - 2))
                }
            }
            .frame(height: 24)
            HStack {
                Text("0"); Spacer(); Text("50"); Spacer(); Text("100")
            }
            .font(.system(size: 9).monospacedDigit()).foregroundStyle(Theme.textSecondary)
        }
        .accessibilityHidden(true)
    }
}

/// 「分数 → 区间 → 等级」一行；防抖动保留旧等级、或被封顶时如实说明。
struct QuantBandStep: View {
    let score: Double
    let grade: String?

    var body: some View {
        if let grade {
            VStack(alignment: .leading, spacing: 6) {
                QuantBandScale(score: score)
                let byBand = QuantGradeScale.grade(for: score)
                if byBand != grade {
                    QuantExplainText(text: L("%@ 按分档应为 %@；为避免贴着边界来回跳，分数要越过边界 %@ 分以上才换等级，所以暂时保留 %@。",
                                             QuantGradeScale.fmt(score), byBand,
                                             QuantGradeScale.fmt(QuantGradeScale.hysteresis), grade))
                } else if let r = QuantGradeScale.range(of: grade) {
                    QuantExplainText(text: L("%@ 落在 %@ ~ %@ 区间 → %@", QuantGradeScale.fmt(score),
                                             QuantGradeScale.fmt(r.lo), QuantGradeScale.fmt(r.hi), grade))
                }
                if let meaning = QuantGradeScale.tierMeaning(grade) {
                    QuantExplainText(text: "\(grade)：\(meaning)", secondary: true)
                }
            }
        }
    }
}

/// 名称 + 分数的一行小条目（维度分构成、综合分构成）；weightPct 非空时名称后写它在综合分里的占比。
struct QuantScoreItem: View {
    let name: String
    let score: Double?
    let grade: String?
    var weightPct: Int? = nil

    var body: some View {
        HStack(spacing: 6) {
            Text(weightPct.map { "\(name) \($0)%" } ?? name).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary).lineLimit(1)
            Spacer(minLength: 4)
            Text(score.map { QuantGradeScale.fmt($0.rounded()) } ?? "—")
                .font(QuantTypography.metadata.weight(.semibold).monospacedDigit())
                .foregroundStyle(QuantGradeStyle.color(grade))
        }
        .padding(.horizontal, 8).padding(.vertical, 5)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 6))
    }
}

// MARK: - 各处的解释内容

/// 单项指标的等级：板块百分位 → 区间 → 等级。
struct QuantMetricGradeExplanation: View {
    let metric: QuantMetric
    let peer: QuantPeerGroup?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let p = metric.percentile {
                let pText = QuantGradeScale.fmt(p.rounded())
                if let peer {
                    QuantExplainText(text: metric.lowerBetter
                        ? L("把%@板块 %lld 家公司的「%@」从高到低排，本股比约 %@%% 的公司更低。这项指标越低越好，所以排在第 %@ 百分位。",
                            peer.sectorName, peer.sampleSize, metric.name, pText, pText)
                        : L("把%@板块 %lld 家公司的「%@」从低到高排，本股比约 %@%% 的公司更高，排在第 %@ 百分位。",
                            peer.sectorName, peer.sampleSize, metric.name, pText, pText))
                } else {
                    QuantExplainText(text: L("本股在同板块排第 %@ 百分位。", pText))
                }
                QuantBandStep(score: p, grade: metric.grade)
            } else {
                QuantExplainText(text: metric.statusNote ?? L("数据不足，这项指标暂不评等级。"))
                QuantExplainText(text: L("暂不评等级的指标不参与维度分计算，不会拉低或抬高等级。"), secondary: true)
            }
        }
    }
}

/// 维度等级：列出参与平均的每项指标百分位。
struct QuantDimensionGradeExplanation: View {
    let dimension: QuantDimension

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if dimension.isOK, let score = dimension.score {
                // 权重为 0 的指标本阶段不用（如成长期不看市净率）：仍展示，但不进分数
                let unused = dimension.allMetrics.filter { $0.percentile != nil && $0.effectiveWeight == 0 }
                let part = dimension.allMetrics.filter { $0.percentile != nil && $0.effectiveWeight > 0 }
                // 口径相近的指标合并计权（如三种 GAAP 利润率各 ×0.5），估值倍数按公司阶段取舍权重
                let weighted = part.contains { $0.effectiveWeight != 1 }
                QuantExplainText(text: weighted
                    ? L("%@分 %@ = 下面 %lld 项指标板块百分位的加权平均（名称后 ×0.5 表示口径相近或本阶段不太看重、权重较低）：",
                        dimension.name, QuantGradeScale.fmt(score), part.count)
                    : L("%@分 %@ = 下面 %lld 项指标板块百分位的平均：",
                        dimension.name, QuantGradeScale.fmt(score), part.count))
                LazyVGrid(columns: [GridItem(.flexible(), spacing: 6), GridItem(.flexible(), spacing: 6)], spacing: 6) {
                    ForEach(part) { m in
                        QuantScoreItem(name: m.effectiveWeight == 1 ? m.name : "\(m.name) ×\(String(format: "%g", m.effectiveWeight))",
                                       score: m.percentile, grade: m.grade)
                    }
                }
                if !unused.isEmpty {
                    QuantExplainText(text: L("这家公司所处的阶段不看其中 %lld 项估值指标（如市净率），它们仍在下面展示，但不参与计算；每个指标仍然和同板块全体公司比百分位。", unused.count), secondary: true)
                }
                let skipped = dimension.allMetrics.count - part.count - unused.count
                if skipped > 0 {
                    QuantExplainText(text: L("另有 %lld 项数据不足或不适用，不参与平均。", skipped), secondary: true)
                }
                QuantBandStep(score: score, grade: dimension.grade)
            } else {
                QuantExplainText(text: dimension.statusNote ?? L("参与计算的指标太少，这个维度暂不评等级。"))
                if dimension.status == "accumulating" {
                    QuantExplainText(text: L("预期修正要和 30 天、90 天前的分析师预测对比，需要先逐日记录，攒够天数后才开始评分。"),
                                     secondary: true)
                } else {
                    QuantExplainText(text: L("有效指标不足总数的三分之一（至少 2 项）时，这个维度不评等级，也不计入综合分。"),
                                     secondary: true)
                }
            }
        }
    }
}

/// 综合等级：各维度分按公司阶段加权平均 → 在全部样本中的百分位 → 等级（含封顶）。
struct QuantOverallGradeExplanation: View {
    let research: QuantResearch

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let o = research.overall, let score = o.score {
                let weighted = research.scoredDimensions.contains { $0.weightPct != nil }
                QuantExplainText(text: weighted
                    ? L("综合分 %@ = %lld 个已评分维度按所处阶段加权的平均（名称后是它占综合分的比例）：", QuantGradeScale.fmt(score), o.dimensionsUsed)
                    : L("综合分 %@ = %lld 个已评分维度的平均：", QuantGradeScale.fmt(score), o.dimensionsUsed))
                LazyVGrid(columns: [GridItem(.flexible(), spacing: 6), GridItem(.flexible(), spacing: 6)], spacing: 6) {
                    ForEach(research.scoredDimensions.filter(\.isOK)) { d in
                        QuantScoreItem(name: d.name, score: d.score, grade: d.grade, weightPct: d.weightPct)
                    }
                }
                if weighted {
                    if let stage = research.stage {
                        QuantExplainText(text: L("这家公司处在「%@」：不同阶段看重的东西不一样——成长期更看重增速，成熟期更看重估值和赚钱能力。", stage.name), secondary: true)
                    } else {
                        QuantExplainText(text: L("这家公司没有划分阶段，各个维度占一样的比例。"), secondary: true)
                    }
                }
                if QuantMoatCard.isEnabled, research.moat != nil {
                    QuantExplainText(text: L("护城河只展示，不计入综合分。"), secondary: true)
                }
                if let p = o.universePercentile {
                    if let universe = research.peerGroup?.universeName {
                        QuantExplainText(text: L("再把综合分和全部样本股票（%@）比，高于约 %@%% 的股票，排第 %@ 百分位。",
                                                 universe, QuantGradeScale.fmt(p.rounded()), QuantGradeScale.fmt(p.rounded())))
                    } else {
                        QuantExplainText(text: L("再把综合分和全部样本股票（标普1500 成分股）比，高于约 %@%% 的股票，排第 %@ 百分位。",
                                                 QuantGradeScale.fmt(p.rounded()), QuantGradeScale.fmt(p.rounded())))
                    }
                    if o.capped {
                        QuantBandScale(score: p)
                        QuantExplainText(text: L("按百分位本可以更高，但有占比不低于 %lld%% 的基本面维度（估值 / 成长 / 盈利能力 / 财务稳健）分低于 %@（F 档），综合等级最高只给 %@——重要维度的明显短板不能被其他强项掩盖。",
                                                 QuantGradeScale.capMinWeightPct,
                                                 QuantGradeScale.fmt(QuantGradeScale.capThreshold), QuantGradeScale.capCeiling))
                    } else {
                        QuantBandStep(score: p, grade: o.grade)
                    }
                }
                if o.grade == nil, let note = o.note { QuantExplainText(text: note, secondary: true) }
            } else {
                QuantExplainText(text: research.overall?.note ?? L("可用维度不足，暂不评综合等级。"))
            }
        }
    }
}

/// 比较对象：为什么只和同板块比。
struct QuantPeerExplanation: View {
    let peer: QuantPeerGroup

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            QuantExplainText(text: L("每个指标只和%@板块的 %lld 家公司比。不同行业的生意模式差别很大，比如软件公司毛利率天然比超市高，跨行业比没有意义。",
                                     peer.sectorName, peer.sampleSize))
            if let universe = peer.universeName {
                QuantExplainText(text: L("板块按全球行业分类标准（GICS）一级行业划分，样本是%@。", universe), secondary: true)
            } else {
                QuantExplainText(text: L("板块按全球行业分类标准（GICS）划分，样本是标普1500 成分股。"), secondary: true)
            }
            if !peer.inUniverse {
                QuantExplainText(text: L("本股不在样本内，用同一套板块分布给它定位。"), secondary: true)
            }
        }
    }
}

/// 板块中位：用本指标的真实数字解释。
struct QuantMedianExplanation: View {
    let metric: QuantMetric
    let research: QuantResearch

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            QuantExplainText(text: L("把同板块公司按「%@」从低到高排成一队，站在正中间那家公司的数值就是板块中位。它比平均值更不容易被个别极端公司带偏。",
                                     metric.name))
            if let median = metric.sectorMedianDisplay {
                QuantExplainText(text: L("这里：%@ 是 %@，板块中位是 %@。", research.symbol, metric.displayValue, median))
            }
        }
    }
}

/// 分布条：P10 ~ P90 用本指标的真实刻度解释。
struct QuantDistributionExplanation: View {
    let metric: QuantMetric
    let research: QuantResearch

    var body: some View {
        let isPercent = metric.displayValue.hasSuffix("%")
        let ticks: [(String, String, Int)] = [("P10", "p10", 10), ("P25", "p25", 25), (L("中位"), "p50", 50),
                                               ("P75", "p75", 75), ("P90", "p90", 90)]
        VStack(alignment: .leading, spacing: 8) {
            QuantExplainText(text: L("这条线把同板块公司按这项指标从低到高摆开。P 后面的数字表示「有多少比例的公司低于这个值」："))
            ForEach(ticks, id: \.1) { name, key, pct in
                if let v = metric.distribution?[key] {
                    QuantExplainText(text: L("%@ = %@：约 %lld%% 的公司低于它", name,
                                             DistributionStrip.short(v, isPercent: isPercent), pct), secondary: true)
                }
            }
            QuantExplainText(text: metric.lowerBetter
                ? L("白线是 %@。这项指标越低越好，所以左端（红）更好、右端（绿）更弱。", research.symbol)
                : L("白线是 %@。这项指标越高越好，所以右端（红）更好、左端（绿）更弱。", research.symbol))
            QuantExplainText(text: L("超出 P10 ~ P90 的极端值贴边显示。"), secondary: true)
        }
    }
}
