import SwiftUI
import DeepAlphaCore

/// 找回密码页。手机号或邮箱 + 验证码 + 新密码。
///
/// 注意：服务端对未注册的账号也返回「已发送」（防账号枚举），所以这里不能
/// 因为发码成功就提示「账号已找到」——用户输错账号时会一直收不到码，这是
/// 有意为之的取舍。
struct ForgotPasswordView: View {
    @Environment(AppState.self) private var appState
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
            ScrollView {
                VStack(spacing: 14) {
                    AccountChannelPicker(channel: $channel)

                    AccountField(channel: channel, text: $account)

                    VerificationCodeField(code: $code, canRequest: accountValid) {
                        await appState.requestPasswordResetCode(account: account, channel: channel)
                    }

                    AuthSecureField(icon: "lock", placeholder: "新密码", text: $password)
                    AuthSecureField(icon: "lock.rotation", placeholder: "确认新密码", text: $confirm)

                    PasswordRulesChecklist(rules: rules, matched: matched)

                    if let error = appState.authError {
                        Text(error)
                            .font(.footnote)
                            .foregroundStyle(.red)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    if done {
                        Text("密码已重置，请用新密码登录")
                            .font(.footnote)
                            .foregroundStyle(.green)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    AuthPrimaryButton(title: "重置密码", loadingTitle: "提交中…",
                                      loading: appState.loggingIn, enabled: canSubmit) {
                        Task {
                            let ok = await appState.resetPassword(
                                account: account, channel: channel,
                                code: code, newPassword: password)
                            if ok {
                                done = true
                                try? await Task.sleep(for: .seconds(1))
                                dismiss()
                            }
                        }
                    }
                }
                .padding(20)
            }
            .scrollDismissesKeyboard(.interactively)
            .navigationTitle("找回密码")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("取消") {
                        appState.authError = nil
                        dismiss()
                    }
                }
            }
            .onChange(of: channel) { _, _ in
                account = ""
                code = ""
                appState.authError = nil
            }
        }
    }
}
