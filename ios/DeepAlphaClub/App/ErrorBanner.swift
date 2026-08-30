import SwiftUI

/// 顶部错误条 + 关闭。
struct ErrorBanner: View {
    let message: String
    let onClose: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
            Text(message).font(.footnote)
            Spacer(minLength: 4)
            Button("知道了", action: onClose)
                .font(.footnote.weight(.semibold))
        }
        .foregroundStyle(.red)
        .padding(10)
        .background(Color.red.opacity(0.1), in: RoundedRectangle(cornerRadius: 10))
    }
}
