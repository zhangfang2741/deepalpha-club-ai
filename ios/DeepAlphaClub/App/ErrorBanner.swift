import SwiftUI

/// 顶部提示条 + 关闭。默认红色报错；tint 换成橙色即为警告。
struct ErrorBanner: View {
    let message: String
    var tint: Color = .red
    var icon: String = "exclamationmark.triangle.fill"
    let onClose: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
            Text(message).font(.footnote)
            Spacer(minLength: 4)
            Button("知道了", action: onClose)
                .font(.footnote.weight(.semibold))
        }
        .foregroundStyle(tint)
        .padding(10)
        .background(tint.opacity(0.1), in: RoundedRectangle(cornerRadius: 10))
    }
}
