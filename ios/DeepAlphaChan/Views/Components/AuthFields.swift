import SwiftUI

// 认证页面共用的输入控件。
//
// LoginView 和 RegisterView 原本各自私有实现了一份 field/secureField，
// 加上 ForgotPasswordView 就是三份完全一样的代码，抽到这里。

/// 带图标的普通输入框。
struct AuthTextField: View {
    let icon: String
    let placeholder: String
    @Binding var text: String

    var body: some View {
        HStack {
            Image(systemName: icon).foregroundColor(Theme.textSecondary).frame(width: 20)
            TextField(placeholder, text: $text).foregroundColor(Theme.textPrimary)
        }
        .padding(12)
        .background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

/// 带图标的密码输入框。
struct AuthSecureField: View {
    let icon: String
    let placeholder: String
    @Binding var text: String

    var body: some View {
        HStack {
            Image(systemName: icon).foregroundColor(Theme.textSecondary).frame(width: 20)
            SecureField(placeholder, text: $text).foregroundColor(Theme.textPrimary)
        }
        .padding(12)
        .background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

/// 手机号 / 邮箱切换。
struct AccountChannelPicker: View {
    @Binding var channel: AccountChannel

    var body: some View {
        Picker("", selection: $channel) {
            ForEach(AccountChannel.allCases) { c in
                Text(c.title).tag(c)
            }
        }
        .pickerStyle(.segmented)
    }
}

/// 账号输入框：键盘类型随通道切换。
struct AccountField: View {
    let channel: AccountChannel
    @Binding var text: String

    var body: some View {
        AuthTextField(icon: channel.icon, placeholder: channel.placeholder, text: $text)
            .keyboardType(channel == .phone ? .numberPad : .emailAddress)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
    }
}

/// 验证码输入框 + 获取按钮（带倒计时）。
///
/// 倒计时秒数与后端 EMAIL_CODE_RESEND_COOLDOWN 对齐（60 秒）。这只是个体验优化，
/// 真正的冷却由服务端把关——用户重装 App 也绕不过去。
struct VerificationCodeField: View {
    @Binding var code: String
    /// 账号格式合法才允许发码
    let canRequest: Bool
    /// 返回 true 表示发送成功，才开始倒计时。
    let onRequest: () async -> Bool

    @State private var remaining = 0
    @State private var isRequesting = false

    private let cooldown = 60

    var body: some View {
        HStack(spacing: 10) {
            HStack {
                Image(systemName: "number").foregroundColor(Theme.textSecondary).frame(width: 20)
                TextField(L("6 位验证码"), text: $code)
                    .keyboardType(.numberPad)
                    .foregroundColor(Theme.textPrimary)
                    .onChange(of: code) { _, newValue in
                        // 只留数字并截断，避免粘贴进来一串带空格的内容
                        let digits = String(newValue.filter(\.isNumber).prefix(6))
                        if digits != newValue { code = digits }
                    }
            }
            .padding(12)
            .background(Theme.surfaceAlt)
            .clipShape(RoundedRectangle(cornerRadius: 10))

            Button {
                Task {
                    isRequesting = true
                    let sent = await onRequest()
                    isRequesting = false
                    if sent { startCountdown() }
                }
            } label: {
                Group {
                    if isRequesting {
                        ProgressView().tint(Theme.accent)
                    } else {
                        Text(remaining > 0 ? "\(remaining)s" : L("获取验证码"))
                            .font(.footnote)
                    }
                }
                .frame(width: 88)
                .padding(.vertical, 14)
                .foregroundColor(buttonEnabled ? Theme.accent : Theme.textSecondary)
                .background(Theme.surfaceAlt)
                .clipShape(RoundedRectangle(cornerRadius: 10))
            }
            .disabled(!buttonEnabled)
        }
    }

    private var buttonEnabled: Bool {
        canRequest && remaining == 0 && !isRequesting
    }

    private func startCountdown() {
        remaining = cooldown
        Task {
            while remaining > 0 {
                try? await Task.sleep(for: .seconds(1))
                remaining -= 1
            }
        }
    }
}
