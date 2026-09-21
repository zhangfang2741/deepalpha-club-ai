import SwiftUI

/// 「走到哪一步」阶段徽标点击后弹出的讲解层。完整实现见 Task 8。
struct PivotPhaseGuideSheet: View {
    let pivotPhase: PivotPhase

    var body: some View {
        Text(pivotPhase.phaseLabel)
    }
}
