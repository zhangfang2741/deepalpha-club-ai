import SwiftUI

/// 结构位置：全局判定图（全部可能结果的地图）+ 当前状态详情。
/// 不是必然依次完成的进度条——图上五个框是全部可能结果，点哪个看哪个的规则。
///
/// 不用 SectionCard：这张图紧跟在上面的内容下面，不需要再有一个
/// 「01·结构位置」大标题分隔。
struct PivotPhaseBlock: View {
    let phase: PivotPhase

    var body: some View {
        PivotPhaseDiagram(phase: phase)
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}
