import SwiftUI

/// 听写结果页中间的常驻操作引导：左侧重来，右侧下一个。
///
/// 两侧同一套配色（次级灰文字 + 主题色箭头）：它只说明「往哪边推会发生什么」，
/// 判定结论由卡片上方那行负责，不需要在这里再用状态色强调一次。
struct DictationSwipeInstructions: View {
    var body: some View {
        HStack(spacing: 0) {
            HStack(spacing: 8) {
                DirectionalChevronMotion(pointsRight: false, color: Theme.accent)
                Text("重来")
            }

            Spacer(minLength: 72)

            HStack(spacing: 8) {
                Text("下一个")
                DirectionalChevronMotion(pointsRight: true, color: Theme.accent)
            }
        }
        .font(.subheadline.bold())
        .foregroundStyle(Theme.textSecondary)
        // 压在卡片内容之上，得足够淡才不抢戏。
        .opacity(0.52)
        .lineLimit(1)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
        .padding(.horizontal, 14)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("左滑重来，右滑下一个")
    }
}
