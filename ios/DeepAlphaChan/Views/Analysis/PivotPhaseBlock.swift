import SwiftUI

/// 结构位置：全局判定图（全部可能结果的地图）+ 当前状态详情。
/// 不是必然依次完成的进度条——图上五个框是全部可能结果，点哪个看哪个的规则。
struct PivotPhaseBlock: View {
    let phase: PivotPhase

    var body: some View {
        SectionCard(title: L("01 · 结构位置"), systemImage: "square.stack.3d.up") {
            PivotPhaseDiagram(phase: phase)
        }
    }
}
