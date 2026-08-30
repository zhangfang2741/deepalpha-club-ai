import SwiftUI
import DeepAlphaCore

// 认证页面共用的输入控件：登录 / 注册 / 找回密码三个页面都用同一套。

/// 带图标的普通输入框。
struct AuthTextField: View {
    let icon: String
    let placeholder: String
    @Binding var text: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .foregroundStyle(.secondary)
                .frame(width: 20)
            TextField(placeholder, text: $text)
        }
        .padding(12)
        .background(Color(.secondarySystemBackground),
                    in: RoundedRectangle(cornerRadius: 10))
    }
}

/// 带图标的密码输入框。
struct AuthSecureField: View {
    let icon: String
    let placeholder: String
    @Binding var text: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .foregroundStyle(.secondary)
                .frame(width: 20)
            SecureField(placeholder, text: $text)
        }
        .padding(12)
        .background(Color(.secondarySystemBackground),
                    in: RoundedRectangle(cornerRadius: 10))
    }
}

/// 手机号 / 邮箱切换。
struct AccountChannelPicker: View {
    @Binding var channel: AccountChannel

    var body: some View {
        Picker("账号类型", selection: $channel) {
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
            .textContentType(channel == .phone ? .telephoneNumber : .emailAddress)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
    }
}

/// 验证码输入框 + 获取按钮（带倒计时）。
///
/// 倒计时秒数与后端重发冷却对齐（60 秒）。这只是个体验优化，真正的冷却由服务端
/// 把关——用户重装 App 也绕不过去。
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
            HStack(spacing: 10) {
                Image(systemName: "number")
                    .foregroundStyle(.secondary)
                    .frame(width: 20)
                TextField("6 位验证码", text: $code)
                    .keyboardType(.numberPad)
                    .textContentType(.oneTimeCode)
                    .onChange(of: code) { _, newValue in
                        // 只留数字并截断，避免粘贴进来一串带空格的内容
                        let digits = String(newValue.filter(\.isNumber).prefix(6))
                        if digits != newValue { code = digits }
                    }
            }
            .padding(12)
            .background(Color(.secondarySystemBackground),
                        in: RoundedRectangle(cornerRadius: 10))

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
                        ProgressView()
                    } else {
                        Text(remaining > 0 ? "\(remaining)s" : "获取验证码")
                            .font(.footnote)
                    }
                }
                .frame(width: 88)
                .padding(.vertical, 14)
                .background(Color(.secondarySystemBackground),
                            in: RoundedRectangle(cornerRadius: 10))
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

/// 密码规则清单（注册页与找回密码页共用）。
struct PasswordRulesChecklist: View {
    let rules: PasswordRules
    let matched: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            row("8–64 位长度", rules.longEnough)
            row("含字母", rules.hasLetter)
            row("含数字", rules.hasDigit)
            row("两次密码一致", matched)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(Color(.tertiarySystemBackground),
                    in: RoundedRectangle(cornerRadius: 10))
    }

    private func row(_ text: String, _ ok: Bool) -> some View {
        HStack(spacing: 6) {
            Image(systemName: ok ? "checkmark.circle.fill" : "circle")
                .font(.caption)
                .foregroundStyle(ok ? Color.green : Color.secondary)
            Text(text)
                .font(.caption)
                .foregroundStyle(ok ? Color.primary : Color.secondary)
        }
    }
}

/// 认证页面的主按钮（登录 / 注册 / 重置共用同一套样式与 loading 态）。
struct AuthPrimaryButton: View {
    let title: String
    let loadingTitle: String
    let loading: Bool
    let enabled: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if loading { ProgressView().tint(.white) }
                Text(loading ? loadingTitle : title).fontWeight(.semibold)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(enabled ? Color.accentColor : Color(.secondarySystemBackground),
                        in: RoundedRectangle(cornerRadius: 12))
            .foregroundStyle(enabled ? Color.white : Color.secondary)
        }
        .disabled(!enabled || loading)
    }
}
