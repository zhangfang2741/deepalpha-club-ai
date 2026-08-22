import SwiftUI

/// 找回密码页。手机号或邮箱 + 验证码 + 新密码。
///
/// 注意：服务端对未注册的账号也返回「已发送」（防账号枚举），所以这里不能
/// 因为发码成功就提示「账号已找到」——用户输错账号时会一直收不到码，这是
/// 有意为之的取舍。
struct ForgotPasswordView: View {
    @EnvironmentObject var auth: AuthViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var channel: AccountChannel
    @State private var account = ""
    @State private var code = ""
    @State private var password = ""
    @State private var confirm = ""
    @State private var done = false

    /// 从登录页带过来当前选中的通道，省得用户再切一次。
    init(channel: AccountChannel = .phone) {
        _channel = State(initialValue: channel)
    }

    private var rules: PasswordRules { PasswordRules(password: password) }
    private var matched: Bool { !confirm.isEmpty && password == confirm }
    private var accountValid: Bool { AccountInput.isValid(account, channel: channel) }

    private var canSubmit: Bool {
        accountValid && AccountInput.isValidCode(code) && rules.allSatisfied && matched
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                ScrollView {
                    VStack(spacing: 14) {
                        AccountChannelPicker(channel: $channel)

                        AccountField(channel: channel, text: $account)

                        VerificationCodeField(code: $code, canRequest: accountValid) {
                            await auth.requestPasswordResetCode(account: account, channel: channel)
                        }

                        AuthSecureField(icon: "lock", placeholder: "新密码", text: $password)
                        AuthSecureField(icon: "lock.rotation", placeholder: "确认新密码", text: $confirm)

                        rulesChecklist

                        if let error = auth.errorMessage {
                            Text(error).font(.footnote).foregroundColor(Theme.down)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        if done {
                            Text("密码已重置，请用新密码登录")
                                .font(.footnote).foregroundColor(Theme.up)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        Button {
                            Task {
                                let ok = await auth.resetPassword(
                                    account: account, channel: channel,
                                    code: code, newPassword: password)
                                if ok {
                                    done = true
                                    try? await Task.sleep(for: .seconds(1))
                                    dismiss()
                                }
                            }
                        } label: {
                            HStack {
                                if auth.isLoading { ProgressView().tint(.white) }
                                Text(auth.isLoading ? "提交中…" : "重置密码").fontWeight(.semibold)
                            }
                            .frame(maxWidth: .infinity).padding(.vertical, 14)
                            .background(canSubmit ? Theme.accent : Theme.surfaceAlt)
                            .foregroundColor(canSubmit ? .white : Theme.textSecondary)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                        .disabled(!canSubmit || auth.isLoading)
                    }
                    .padding(20)
                }
            }
            .navigationTitle("找回密码")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("取消") { auth.errorMessage = nil; dismiss() }
                }
            }
            .onChange(of: channel) { _, _ in
                account = ""
                code = ""
                auth.errorMessage = nil
            }
        }
    }

    private var rulesChecklist: some View {
        VStack(alignment: .leading, spacing: 6) {
            rule("8–64 位长度", rules.longEnough)
            rule("含大写字母", rules.hasUpper)
            rule("含小写字母", rules.hasLower)
            rule("含数字", rules.hasDigit)
            rule("含特殊字符（如 !@#$%^&*）", rules.hasSpecial)
            rule("两次密码一致", matched)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func rule(_ text: String, _ ok: Bool) -> some View {
        HStack(spacing: 6) {
            Image(systemName: ok ? "checkmark.circle.fill" : "circle")
                .font(.caption).foregroundColor(ok ? Theme.up : Theme.textSecondary)
            Text(text).font(.caption).foregroundColor(ok ? Theme.textPrimary : Theme.textSecondary)
        }
    }
}
