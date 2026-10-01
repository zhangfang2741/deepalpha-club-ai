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

/// 等级色块：用于成绩单与指标行，颜色同时编码强弱，暂无时为灰色破折号。
struct QuantGradeBlock: View {
    let grade: String?
    var side: CGFloat = 44

    var body: some View {
        let color = QuantGradeStyle.color(grade)
        Text(grade ?? "—")
            .font(.system(size: side * 0.41, weight: .bold, design: .rounded))
            .foregroundStyle(color)
            .frame(width: side, height: side)
            .background(color.opacity(grade == nil ? 0.06 : 0.13), in: RoundedRectangle(cornerRadius: side * 0.25))
            .accessibilityLabel(grade ?? L("暂无"))
    }
}
