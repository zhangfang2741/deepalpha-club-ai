import SwiftUI

/// 结构位置：全局判定图（全部可能结果的地图）+ 当前状态详情。
/// 不是必然依次完成的进度条——图上五个框是全部可能结果，点哪个看哪个的规则。
struct PivotPhaseBlock: View {
    let phase: PivotPhase
    @State private var showGuide = false

    var body: some View {
        SectionCard(title: L("01 · 结构位置"), systemImage: "square.stack.3d.up") {
            PivotPhaseDiagram(phase: phase)

            HStack(spacing: 16) {
                Button { showGuide = true } label: {
                    Label(L("查看完整判定依据"), systemImage: "list.bullet.clipboard")
                        .font(.caption)
                }
                .buttonStyle(.plain)
                .foregroundStyle(Theme.accent)

                AnalysisTermLink(term: "中枢", color: Theme.pivotFill)
            }
        }
        .sheet(isPresented: $showGuide) {
            NavigationStack { PivotPhaseGuideSheet(pivotPhase: phase) }
                .preferredColorScheme(.dark)
        }
    }
}
