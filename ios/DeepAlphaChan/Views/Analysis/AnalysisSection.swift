import SwiftUI

/// 从当前事实出发，解释结构位置——全局判定图本身就是"接下来观察什么"的答案，
/// 不需要再单独一张卡片复述一遍。
struct AnalysisSection: View {
    let analysis: ChanAnalysis

    var body: some View {
        VStack(spacing: 12) {
            if let phase = analysis.pivotPhase {
                PivotPhaseBlock(phase: phase)
            } else {
                Text(L("当前数据尚不足以判断中枢阶段，请先对照图上的笔与线段。"))
                    .font(AnalysisType.body)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
            }
        }
    }
}
