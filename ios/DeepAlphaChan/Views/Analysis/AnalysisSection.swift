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

    /// 当前状态：大白话一句话 → 走到哪一步 → 各项事实依据 → 走势标签 → 结构统计，
    /// 只陈述事实不下结论。
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

                if let phase = analysis.pivotPhase {
                    Divider().overlay(Theme.border)
                    PivotPhaseBlock(phase: phase)
                }

                if let rec = analysis.recommendation, !rec.reasons.isEmpty {
                    Divider().overlay(Theme.border)
                    BulletList(title: L("依据"), items: rec.reasons, color: Theme.textSecondary)
                }

                if analysis.walkTypeLabel != nil || analysis.trendOutlookLabel != nil {
                    Divider().overlay(Theme.border)
                    walkTypeChips
                }

                Divider().overlay(Theme.border)
                Text(structureStats)
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// 「走势」标签行：走势类型 + 走势展望的人话标签（这两个字段此前未被 UI 消费）。
    private var walkTypeChips: some View {
        HStack(spacing: 8) {
            if let label = analysis.walkTypeLabel { Chip(text: label, color: Theme.accent) }
            if let label = analysis.trendOutlookLabel { Chip(text: label, color: Theme.segment) }
        }
    }
}

/// 「走到哪一步」区块：阶段徽标（点击弹讲解）+ checklist + 因为 + 分支说明。
///
/// 独立成子 View 而不是 AnalysisSection 的私有方法：需要自己的 @State 管理
/// 讲解 sheet 的呈现，方法内部不能声明 @State。
private struct PivotPhaseBlock: View {
    let phase: PivotPhase
    @State private var showGuide = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Text(L("走到哪一步"))
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(Theme.textSecondary)
                Spacer()
                Button {
                    showGuide = true
                } label: {
                    HStack(spacing: 4) {
                        Text(phase.phaseLabel)
                        Image(systemName: "info.circle")
                    }
                }
                .buttonStyle(.plain)
                .font(.system(size: 12, weight: .medium))
                .padding(.horizontal, 10).padding(.vertical, 4)
                .background(Theme.accent.opacity(0.15))
                .foregroundColor(Theme.accent)
                .clipShape(Capsule())
                .accessibilityHint(L("点击查看阶段判定说明"))
            }

            VStack(alignment: .leading, spacing: 6) {
                ForEach(phase.checklist) { item in
                    HStack(alignment: .top, spacing: 6) {
                        Image(systemName: item.state == .done ? "checkmark.circle.fill" : "circle")
                            .foregroundColor(item.state == .done ? Theme.accent : Theme.textSecondary)
                            .font(.system(size: 13))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(item.label)
                                .font(.system(size: 13, weight: item.state == .done ? .medium : .regular))
                                .foregroundColor(item.state == .done ? Theme.textPrimary : Theme.textSecondary)
                            if !item.detail.isEmpty {
                                Text(item.detail)
                                    .font(.caption2)
                                    .foregroundColor(Theme.textSecondary)
                            }
                        }
                    }
                }
            }

            HStack(alignment: .top, spacing: 4) {
                Text(L("因为")).font(.caption).foregroundColor(Theme.accent)
                Text(phase.reason).font(.caption).foregroundColor(Theme.textSecondary)
            }

            if !phase.branches.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(phase.branches) { branch in
                        Text("↳ \(branch.conditionLabel) → \(branch.resultLabel)")
                            .font(.caption2)
                            .foregroundColor(Theme.textSecondary)
                    }
                }
            }
        }
        .sheet(isPresented: $showGuide) {
            NavigationStack { PivotPhaseGuideSheet(pivotPhase: phase) }
                .preferredColorScheme(.dark)
        }
    }
}
