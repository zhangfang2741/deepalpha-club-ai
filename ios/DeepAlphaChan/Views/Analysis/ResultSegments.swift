import SwiftUI

/// 详情页图表以下的内容：一条往下读的页面，不再分「当前状态 / 买卖点 / 风险提示」三个 Tab。
///
/// 以前三个 Tab + 底部「继续核对 →」按钮是两套导航，每个 Tab 内容又偏短、多是模板文字，
/// 页面头重脚轻。现在按阅读顺序连续排：这意味着什么 → 买卖点 → 阶段流程图（默认收起）
/// → 需要留意（只列本股的待确认项与风险）。结论本身在页面顶部的 ConclusionCard。
struct ResultSegments: View {
    let analysis: ChanAnalysis
    /// 离屏渲染分享长图时置 true：买卖点全部展开、不放可折叠的流程图。
    var isStatic = false
    /// 页面可用内容宽度，透传给阶段流程图（见 PivotPhaseBlock）。
    var contentWidth: CGFloat?

    /// 买卖点默认只展示最近几条，其余点「查看全部」。
    static let collapsedSignalCount = 3

    @State private var showAllSignals = false
    @State private var showDiagram = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let phase = analysis.pivotPhase {
                sectionHeader(L("这意味着什么"))
                meaningCard(phase)
            }

            signalsSection

            if let phase = analysis.pivotPhase, !isStatic {
                diagramSection(phase)
            }

            if !cautions.isEmpty {
                sectionHeader(L("需要留意"))
                BulletList(items: cautions, color: Theme.textSecondary)
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func sectionHeader(_ text: String, trailing: String? = nil) -> some View {
        HStack {
            Text(text)
            Spacer()
            if let trailing { Text(trailing) }
        }
        .font(.system(size: 13, weight: .semibold))
        .foregroundColor(Theme.textSecondary)
        .padding(.horizontal, 4)
        .padding(.top, 6)
    }

    // MARK: - 这意味着什么

    private func meaningCard(_ phase: PivotPhase) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(HeadlineHighlighter.highlight(Self.plainTerms(phase.reason)))
                .font(AnalysisType.body)
                .foregroundStyle(Theme.textPrimary.opacity(0.9))
                .lineSpacing(AnalysisType.bodyLineSpacing)
                .fixedSize(horizontal: false, vertical: true)
            if !phase.stageGuide.whyItMatters.isEmpty {
                Text(phase.stageGuide.whyItMatters)
                    .font(.footnote)
                    .foregroundStyle(Theme.textSecondary)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text(L("参考中枢（%@）：%@ ~ %@",
                   phase.pivot.level == .segment ? L("线段级") : L("笔级"),
                   String(format: "%.2f", phase.pivot.zd),
                   String(format: "%.2f", phase.pivot.zg)))
                .font(.caption.monospacedDigit())
                .foregroundStyle(Theme.textSecondary)
            if let next = phase.checklist.first(where: { $0.state == .pending }) {
                Divider().background(Theme.border)
                Text(L("接下来看：%@", next.label))
                    .font(.footnote)
                    .foregroundStyle(Theme.accent)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
    }

    /// 后端原因文案里的 ZG / ZD 是缠论记号，普通用户看不懂，换成「上沿 / 下沿」。
    /// 原文「守住 ZG 302.16」里记号两侧带空格（中英混排），换成中文后去掉前面那个空格，
    /// 得到「守住上沿 302.16」。
    static func plainTerms(_ text: String) -> String {
        var t = text
        for (mark, word) in [("ZG", L("上沿")), ("ZD", L("下沿"))] {
            t = t.replacingOccurrences(of: " \(mark) ", with: "\(word) ")
                .replacingOccurrences(of: mark, with: word)
        }
        return t
    }

    // MARK: - 买卖点

    private var sortedSignals: [Signal] { analysis.signals.sorted { $0.time > $1.time } }

    @ViewBuilder
    private var signalsSection: some View {
        let all = sortedSignals
        let unconfirmed = all.filter { !$0.confirmed }.count
        sectionHeader(L("买卖点 · 最新在前"),
                      trailing: unconfirmed > 0 ? L("%lld 条未确认", unconfirmed) : nil)
        if all.isEmpty {
            Text(L("当前区间没有识别到明确的买卖点，可先看上面的状态和图上的中枢位置。"))
                .font(AnalysisType.body)
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
        } else {
            let expanded = isStatic || showAllSignals
            let shown = expanded ? all : Array(all.prefix(Self.collapsedSignalCount))
            VStack(spacing: 6) {
                ForEach(shown) { SignalDetailCard(signal: $0, isStatic: isStatic) }
            }
            if !isStatic && all.count > Self.collapsedSignalCount {
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) { showAllSignals.toggle() }
                } label: {
                    Text(showAllSignals ? L("收起") : L("查看全部 %lld 个买卖点", all.count))
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(Theme.accent)
                        .frame(maxWidth: .infinity, minHeight: 36)
                }
                .buttonStyle(.plain)
            }
        }
    }

    // MARK: - 阶段流程图（默认收起）

    private func diagramSection(_ phase: PivotPhase) -> some View {
        VStack(spacing: 0) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) { showDiagram.toggle() }
            } label: {
                HStack {
                    Text(L("阶段流程图 · 当前在「%@」", Self.stageTitle(phase)))
                        .font(.subheadline)
                        .foregroundStyle(Theme.textPrimary)
                    Spacer()
                    Text(showDiagram ? L("收起") : L("展开"))
                        .font(.footnote)
                        .foregroundStyle(Theme.textSecondary)
                    Image(systemName: "chevron.down")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(Theme.textSecondary)
                        .rotationEffect(.degrees(showDiagram ? 180 : 0))
                }
                .padding(14)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            if showDiagram {
                PivotPhaseBlock(phase: phase, contentWidth: contentWidth, showsDetail: false)
            }
        }
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .padding(.top, 6)
    }

    /// 当前所在的流程节点名（如「确认买卖点」）：直接取流程图自己的节点名，保证与图上
    /// 高亮的框一字不差（不读后端 stage_guide，那里「中枢形成」与图上的「中枢震荡」是同一个框）。
    static func stageTitle(_ phase: PivotPhase) -> String {
        PhaseDiagramCopy.name(of: .node(for: phase.phase))
    }

    // MARK: - 需要留意

    /// 只列本股具体的待确认项与风险（后端给的），不再放通用模板说明。
    private var cautions: [String] {
        AnalysisInterpretation.displayedPendingNotes(analysis)
            + AnalysisInterpretation.displayedOtherRisks(analysis)
    }
}
