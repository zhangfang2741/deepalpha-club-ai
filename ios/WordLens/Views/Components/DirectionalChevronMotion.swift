import SwiftUI

/// 三层方向箭头，通过高亮从内向外依次移动表达滑动方向。
struct DirectionalChevronMotion: View {
    let pointsRight: Bool
    let color: Color

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        Group {
            if reduceMotion {
                chevrons(activeLayer: nil)
            } else {
                PhaseAnimator(pointsRight ? [0, 1, 2, 2] : [2, 1, 0, 0]) { activeLayer in
                    chevrons(activeLayer: activeLayer)
                } animation: { _ in
                    .easeInOut(duration: 0.3)
                }
            }
        }
        .accessibilityHidden(true)
    }

    private func chevrons(activeLayer: Int?) -> some View {
        HStack(spacing: -2) {
            ForEach(0..<3, id: \.self) { layer in
                Image(systemName: pointsRight ? "chevron.right" : "chevron.left")
                    .foregroundStyle(activeLayer == nil || activeLayer == layer ? color : Theme.textSecondary)
                    .scaleEffect(activeLayer == layer ? 1.08 : 0.94)
            }
        }
    }
}
