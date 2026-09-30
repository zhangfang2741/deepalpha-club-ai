import SwiftUI

/// 量化研究的等级配色：沿用 App 的红涨绿跌——A / B 偏强为红、C 中性为灰、D / F 偏弱为绿。
enum QuantGradeStyle {
    static func color(_ grade: String?) -> Color {
        guard let first = grade?.first else { return Theme.textSecondary }
        switch first {
        case "A": return Theme.up
        case "B": return Theme.up.opacity(0.7)
        case "D": return Theme.down.opacity(0.75)
        case "F": return Theme.down
        default: return Theme.textSecondary
        }
    }
}

/// 等级徽标（圆角小方块里一个等级字母）。
struct QuantGradeBadge: View {
    let grade: String?
    var size: CGFloat = 15

    var body: some View {
        Text(grade ?? "—")
            .font(.system(size: size, weight: .semibold))
            .foregroundStyle(QuantGradeStyle.color(grade))
            .frame(minWidth: size * 2.2, minHeight: size * 1.75)
            .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 8))
    }
}
