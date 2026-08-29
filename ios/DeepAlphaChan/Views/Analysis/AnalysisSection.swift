import SwiftUI

/// 分段控件的「形态分析」段。
///
/// 刻意不叫「结论」：这里只陈述算法从 K 线结构里读出的事实（形态处在哪个阶段、
/// 各维度的技术强弱如何加权），不给任何投资结论。措辞层面也一路避开操作动词。
///
/// 两张卡：
/// - 形态分析：大白话一句话 → 加权后的技术强弱 → 各项事实依据 → 一行结构统计；
/// - 风险提示：单独折叠、默认收起。它讲的是「这些事实有多不可靠」（右侧未确认
///   结构、缠论的滞后性、免责声明），和上面陈述事实是两件事，混在一张卡里读者
///   会把它当成结论的一部分略过。
///
/// 改造前这一段是「形态解读」+「技术形态倾向」两张卡，两边其实是同一批因子
/// （末笔 / 线段 / 中枢位置 / 背驰）算了两遍、措辞各写一套，且两张卡的 chip 会
/// 各自表述（一个「上涨动能减弱」、一个「偏空」）。现在后端把这些因子加权成
/// 一个倾向，前端也就只剩一处表述。
///
/// 字号统一走 AnalysisType 的三级（见 SignalFormatting.swift）。
struct AnalysisSection: View {
    let analysis: ChanAnalysis

    var body: some View {
        VStack(spacing: 12) {
            analysisCard
            if let caveats = analysis.recommendation?.caveats, !caveats.isEmpty {
                riskCard(caveats)
            }
        }
    }

    /// 一行精简结构统计，取代原「当前结构」那段长技术描述。
    private var structureStats: String {
        let pivots = analysis.strokePivots.count + analysis.segmentPivots.count
        return L("%lld 根K线 · %lld 笔 · %lld 线段 · %lld 中枢 · %lld 买卖点",
                 analysis.barsCount, analysis.strokes.count,
                 analysis.segments.count, pivots, analysis.signals.count)
    }

    /// 标题栏 chip：优先用加权后的多空倾向；结构没成形时退回趋势。
    private var chip: (String, Color) {
        if let rec = analysis.recommendation {
            return (SignalFormatting.biasLabel(rec.bias), SignalFormatting.biasColor(rec.bias))
        }
        return (SignalFormatting.trendLabel(analysis.currentTrend),
                SignalFormatting.trendColor(analysis.currentTrend))
    }

    private var analysisCard: some View {
        // 默认展开——它是这张页面最该先读的那段
        CollapsibleCard(title: L("形态分析"), systemImage: "text.magnifyingglass",
                        accessoryChip: chip, defaultExpanded: true) {
            VStack(alignment: .leading, spacing: 14) {
                // 结构没成形（笔太少）时没有大白话解读，退回后端摘要
                Text(analysis.narrative?.headline ?? analysis.summary)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Theme.textPrimary)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)

                if let rec = analysis.recommendation {
                    // 技术强弱单独一行：它是各项事实的加权汇总，和下面逐条列出的
                    // 事实是两个层次，挨着排会混成一团。
                    Text(rec.actionLabel)
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(SignalFormatting.biasColor(rec.bias))
                        .fixedSize(horizontal: false, vertical: true)

                    if !rec.reasons.isEmpty {
                        Divider().overlay(Theme.border)
                        // 首条是「几项偏多、几项偏空」的加权统计，先解释了为什么
                        // 下面会出现与上方强弱反向的单条事实
                        BulletList(title: L("依据"), items: rec.reasons, color: Theme.textSecondary)
                    }
                }

                Divider().overlay(Theme.border)
                Text(structureStats)
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// 风险提示。后端 caveats 已含「待确认结构」（caveats.extend(pending_notes)）。
    private func riskCard(_ caveats: [String]) -> some View {
        CollapsibleCard(title: L("风险提示"), systemImage: "exclamationmark.triangle",
                        accessoryChip: (L("%lld 条", caveats.count), Theme.segment)) {
            BulletList(items: caveats, color: Theme.segment)
        }
    }
}
