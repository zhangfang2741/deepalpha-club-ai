import SwiftUI

/// 三层方向箭头：越靠近文字的那一层越大越亮，向外逐个收小，形成一个朝文字收拢的
/// 楔形；再让一道高亮脉冲从文字侧往外走一遍，表达「往这边推」。
struct DirectionalChevronMotion: View {
    let pointsRight: Bool
    let color: Color

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private static let layerCount = 3

    var body: some View {
        Group {
            if reduceMotion {
                chevrons(activeRank: nil)
            } else {
                // rank 已经编码了方向（2 = 贴着文字，0 = 最外侧），所以左右两边共用
                // 同一组相位；脉冲从文字侧往外走，末尾多停一拍再重来。
                PhaseAnimator([2, 1, 0, 0]) { activeRank in
                    chevrons(activeRank: activeRank)
                } animation: { _ in
                    .easeInOut(duration: 0.3)
                }
            }
        }
        .accessibilityHidden(true)
    }

    private func chevrons(activeRank: Int?) -> some View {
        HStack(spacing: -1) {
            ForEach(0..<Self.layerCount, id: \.self) { layer in
                let rank = rank(for: layer)
                let isActive = activeRank == rank
                Image(systemName: pointsRight ? "chevron.right" : "chevron.left")
                    .foregroundStyle(color)
                    .opacity(baseOpacity(rank) + (isActive ? 0.3 : 0))
                    .scaleEffect(baseScale(rank) + (isActive ? 0.14 : 0))
            }
        }
    }

    /// 把 HStack 里的下标换算成「离文字有多近」：layerCount-1 是紧贴文字、最大最亮的
    /// 那个，0 是甩到最外侧、最小最淡的那个。
    ///
    /// 右滑那组文字在左（下一个 ❯❯❯），所以贴着文字的是下标 0；左滑那组文字在右
    /// （❮❮❮ 重来），贴着文字的是最后一个下标——两边正好相反，这里翻转一次。
    private func rank(for layer: Int) -> Int {
        pointsRight ? Self.layerCount - 1 - layer : layer
    }

    private func baseScale(_ rank: Int) -> Double {
        0.66 + 0.22 * Double(rank)
    }

    private func baseOpacity(_ rank: Int) -> Double {
        0.32 + 0.24 * Double(rank)
    }
}
