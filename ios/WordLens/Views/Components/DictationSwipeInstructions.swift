import SwiftUI

/// 听写结果页中间的常驻操作引导：左侧重来，右侧继续。
struct DictationSwipeInstructions: View {
    let resultColor: Color

    var body: some View {
        HStack(spacing: 0) {
            HStack(spacing: 8) {
                DirectionalChevronMotion(pointsRight: false, color: Theme.accent)
                Text("重来")
            }

            Spacer(minLength: 72)

            HStack(spacing: 8) {
                Text("继续")
                DirectionalChevronMotion(pointsRight: true, color: resultColor)
            }
        }
        .font(.subheadline.bold())
        .foregroundStyle(Theme.textSecondary)
        .opacity(0.52)
        .lineLimit(1)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
        .padding(.horizontal, 14)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("左滑重来，右滑继续")
    }
}
