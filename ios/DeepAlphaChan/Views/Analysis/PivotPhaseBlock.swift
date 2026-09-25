import SwiftUI

/// 阶段是结构位置，不是买卖点强弱，也不是必然依次完成的进度条。
struct PivotPhaseBlock: View {
    let phase: PivotPhase
    @State private var showGuide = false

    var body: some View {
        SectionCard(title: L("01 · 结构位置"), systemImage: "square.stack.3d.up") {
            Button { showGuide = true } label: {
                HStack(alignment: .top, spacing: 8) {
                    Text(phase.phaseLabel).font(.headline)
                    Image(systemName: "info.circle")
                    Spacer(minLength: 0)
                }
                .foregroundStyle(Theme.pivotPhaseColor(phase.phase))
                .frame(minHeight: 44, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityHint(L("点击查看阶段判定说明"))

            WrapLayout(spacing: 6, lineSpacing: 6) {
                ForEach(phase.stageGuide.steps) { step in
                    let current = step.key == phase.phase
                    Text(current ? L("%@ · 当前", step.title) : step.title)
                        .font(.caption.weight(current ? .semibold : .regular))
                        .foregroundStyle(current ? Theme.pivotPhaseColor(phase.phase) : Theme.textSecondary)
                        .padding(.horizontal, 9)
                        .padding(.vertical, 6)
                        .background(Theme.surfaceAlt, in: Capsule())
                        .overlay(Capsule().strokeBorder(current ? Theme.pivotPhaseColor(phase.phase) : .clear))
                }
            }
            Text(L("阶段描述结构位置，不是必经顺序，也不代表信号强弱。"))
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            VStack(alignment: .leading, spacing: 6) {
                Text(L("参考中枢 · %@", phase.pivot.level == .segment ? L("线段级") : L("笔级")))
                    .font(.subheadline.bold())
                    .foregroundStyle(Theme.pivotFill)
                Text(L("下沿 ZD %@ — 上沿 ZG %@",
                       String(format: "%.2f", phase.pivot.zd), String(format: "%.2f", phase.pivot.zg)))
                    .font(.subheadline.monospacedDigit())
                    .foregroundStyle(Theme.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                Label(phase.confirmed ? L("阶段已确认") : L("阶段未确认"),
                      systemImage: phase.confirmed ? "checkmark.circle" : "circle.dashed")
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.pivotFill.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))

            Text(HeadlineHighlighter.highlight(phase.reason))
                .font(AnalysisType.body)
                .foregroundStyle(Theme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .lineSpacing(AnalysisType.bodyLineSpacing)
            AnalysisTermLink(term: "中枢", color: Theme.pivotFill)
        }
        .sheet(isPresented: $showGuide) {
            NavigationStack { PivotPhaseGuideSheet(pivotPhase: phase) }
                .preferredColorScheme(.dark)
        }
    }
}
