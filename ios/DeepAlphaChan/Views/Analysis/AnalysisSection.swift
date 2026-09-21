import SwiftUI

/// 分段控件的「整体分析」段。
///
/// 刻意不叫「形态分析」：这里只陈述算法从 K 线结构里读出的事实（形态处在哪个阶段、
/// 各维度的技术强弱如何加权），不给任何投资结论，条件页的风险提示也写明「不要只看
/// 技术信号，要结合整体走势与市场结构」——这张卡本身就是那个「整体」的呈现，标题得
/// 对上，不能听起来像只在讲局部形态。
///
/// 不展示"加权强弱结论"的多空 chip（`recommendation.bias`）：它和大白话摘要、
/// 走势展望的算法口径各自独立，同一次分析里出现过互相矛盾的情况（比如结论行写
/// "下跌动能转弱"、走势展望却说"上涨延续"），用户反馈这种自相矛盾比"没有结论"
/// 更糟，所以这个多空结论至今没有入口。
///
/// 「走势」区块（`walkTypeSection`）展示的 `walk_type`/`trend_outlook` 是另一
/// 回事：这两个是纯几何判定（中枢排布 + 背驰方向），不是多因子加权，口径单一、
/// 不会自相矛盾，因此可以直接展示——不要和上面那条"不展示方向性判断"的原则
/// 混为一谈。
///
/// 风险提示已拆到 `RiskSection` 独立成一个 tab（见 ResultSegments）。
///
/// 字号统一走 AnalysisType 的三级（见 SignalFormatting.swift）。
struct AnalysisSection: View {
    let analysis: ChanAnalysis

    var body: some View {
        statusCard
    }

    /// 大白话摘要按关键词着色（笔/线段/中枢/背驰/买卖点），结构未成形时的
    /// 后端兜底摘要（`analysis.summary`）不做关键词着色处理，原样展示。
    private var headlineText: Text {
        if let headline = analysis.narrative?.headline {
            return Text(HeadlineHighlighter.highlight(headline))
        }
        return Text(analysis.summary)
    }

    /// 一行精简结构统计，取代原「当前结构」那段长技术描述。
    private var structureStats: String {
        let pivots = analysis.strokePivots.count + analysis.segmentPivots.count
        return L("%lld 根K线 · %lld 笔 · %lld 线段 · %lld 中枢 · %lld 买卖点",
                 analysis.barsCount, analysis.strokes.count,
                 analysis.segments.count, pivots, analysis.signals.count)
    }

    /// 当前状态：大白话一句话 → 走到哪一步 → 走势标签 → 查看判断依据（默认收起）
    /// → 结构统计，只陈述事实不下结论。
    ///
    /// 「查看判断依据」故意收起：加权依据是给想深挖的人看的，默认展开会和
    /// 「走到哪一步」的结论抢视觉焦点，参照设计稿改为点开才展开。
    private var statusCard: some View {
        CollapsibleCard(title: L("当前状态"), systemImage: "waveform.path.ecg",
                        defaultExpanded: true) {
            VStack(alignment: .leading, spacing: 14) {
                // 结构没成形（笔太少）时没有大白话解读，退回后端摘要；关键词着色见
                // HeadlineHighlighter，未命中关键词的字保持默认前景色
                headlineText
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Theme.textPrimary)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)

                if let phase = analysis.pivotPhase {
                    Divider().overlay(Theme.border)
                    PivotPhaseBlock(phase: phase)
                }

                if analysis.walkType != nil || analysis.trendOutlook != nil {
                    Divider().overlay(Theme.border)
                    walkTypeSection
                }

                if let rec = analysis.recommendation, !rec.reasons.isEmpty {
                    Divider().overlay(Theme.border)
                    reasonsDisclosure(rec.reasons)
                }

                Divider().overlay(Theme.border)
                Text(structureStats)
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// 「走势」区块：短标签 chip（上涨趋势/可能转折向下…）+ 一行补充说明
    /// （中枢依次抬高…）。后端的 `walkTypeLabel`/`trendOutlookLabel` 是完整句子
    /// （给 summary 拼句子用），塞进 chip 里会太长，这里按原始枚举码单独映射一套
    /// 短文案——短标签只在这一处使用，暂不值得为此新增后端字段。
    private var walkTypeSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(L("走势"))
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Theme.textSecondary)
            HStack(spacing: 8) {
                if let walkType = analysis.walkType {
                    Chip(text: WalkTypeFormatting.shortLabel(walkType, fallback: analysis.walkTypeLabel),
                         color: Theme.accent)
                }
                if let outlook = analysis.trendOutlook {
                    Chip(text: WalkTypeFormatting.shortOutlookLabel(outlook, fallback: analysis.trendOutlookLabel),
                         color: Theme.segment)
                }
            }
            if let walkType = analysis.walkType, let detail = WalkTypeFormatting.detail(walkType) {
                Text(detail)
                    .font(.caption2)
                    .foregroundColor(Theme.textSecondary)
            }
        }
    }

    /// 「查看判断依据」：默认收起的加权依据列表。
    private func reasonsDisclosure(_ reasons: [String]) -> some View {
        DisclosureGroup {
            BulletList(items: reasons, color: Theme.textSecondary)
                .padding(.top, 6)
        } label: {
            Label(L("查看判断依据"), systemImage: "checklist")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Theme.textSecondary)
        }
        .tint(Theme.textSecondary)
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
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(phase.branches) { branch in
                        HStack(alignment: .top, spacing: 4) {
                            Image(systemName: "arrow.turn.down.right")
                                .font(.system(size: 10))
                                .foregroundColor(Theme.textSecondary)
                            Text("\(branch.conditionLabel) → \(branch.resultLabel)")
                                .font(.caption2)
                                .foregroundColor(Theme.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
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
