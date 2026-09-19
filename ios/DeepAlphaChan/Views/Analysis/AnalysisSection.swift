import SwiftUI

/// 分段控件的「整体分析」段。
///
/// 刻意不叫「形态分析」：这里只陈述算法从 K 线结构里读出的事实（形态处在哪个阶段、
/// 各维度的技术强弱如何加权），不给任何投资结论，条件页的风险提示也写明「不要只看
/// 技术信号，要结合整体走势与市场结构」——这张卡本身就是那个「整体」的呈现，标题得
/// 对上，不能听起来像只在讲局部形态。
///
/// 不展示任何方向性判断（多空 chip / 加权强弱结论 / 走势展望）：这三者算法口径
/// 各自独立，同一次分析里出现过互相矛盾的情况（比如标题栏"中性"、结论行却写
/// "下跌动能转弱"、走势展望又说"上涨延续"），用户反馈这种自相矛盾比"没有结论"
/// 更糟。只保留客观陈述——大白话摘要、加权依据列表、结构统计——由用户自己判断，
/// 不替用户下结论。
///
/// 风险提示已拆到 `RiskSection` 独立成一个 tab（见 ResultSegments）。
///
/// 字号统一走 AnalysisType 的三级（见 SignalFormatting.swift）。
struct AnalysisSection: View {
    let analysis: ChanAnalysis

    var body: some View {
        statusCard
    }

    /// 一行精简结构统计，取代原「当前结构」那段长技术描述。
    private var structureStats: String {
        let pivots = analysis.strokePivots.count + analysis.segmentPivots.count
        return L("%lld 根K线 · %lld 笔 · %lld 线段 · %lld 中枢 · %lld 买卖点",
                 analysis.barsCount, analysis.strokes.count,
                 analysis.segments.count, pivots, analysis.signals.count)
    }

    /// 当前状态：大白话一句话 → 各项事实依据 → 一行结构统计，只陈述事实不下结论。
    private var statusCard: some View {
        CollapsibleCard(title: L("当前状态"), systemImage: "waveform.path.ecg",
                        defaultExpanded: true) {
            VStack(alignment: .leading, spacing: 14) {
                // 结构没成形（笔太少）时没有大白话解读，退回后端摘要
                Text(analysis.narrative?.headline ?? analysis.summary)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Theme.textPrimary)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)

                if let rec = analysis.recommendation, !rec.reasons.isEmpty {
                    Divider().overlay(Theme.border)
                    BulletList(title: L("依据"), items: rec.reasons, color: Theme.textSecondary)
                }

                Divider().overlay(Theme.border)
                Text(structureStats)
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}
