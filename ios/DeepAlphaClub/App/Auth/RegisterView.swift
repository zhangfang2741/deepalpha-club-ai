import SwiftUI
import DeepAlphaCore

/// 注册页。手机号或邮箱 + 验证码 + 密码，注册成功即登录。
/// 密码规则对齐后端 validate_password_strength：8–64 位，含字母和数字。
struct RegisterView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss

    @State private var channel: AccountChannel = .phone
    @State private var account = ""
    @State private var code = ""
    @State private var username = ""
    @State private var password = ""
    @State private var confirm = ""

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
                        await appState.requestRegisterCode(account: account, channel: channel)
                    }

                    AuthTextField(icon: "person", placeholder: "用户名（可选）", text: $username)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    AuthSecureField(icon: "lock", placeholder: "密码", text: $password)
                    AuthSecureField(icon: "lock.rotation", placeholder: "确认密码", text: $confirm)

                    PasswordRulesChecklist(rules: rules, matched: matched)

                    if let error = appState.authError {
                        Text(error)
                            .font(.footnote)
                            .foregroundStyle(Theme.danger)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    AuthPrimaryButton(title: "注册并登录", loadingTitle: "注册中…",
                                      loading: appState.loggingIn, enabled: canSubmit) {
                        Task {
                            await appState.register(
                                account: account, channel: channel, code: code,
                                password: password, username: username)
                            if appState.isLoggedIn { dismiss() }
                        }
                    }
                }
                .padding(20)
            }
            .themedBackground()
        .scrollDismissesKeyboard(.interactively)
            .navigationTitle("注册")
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
                // 切换通道时清空账号和验证码：验证码是绑在具体账号上的，留着只会误导
                account = ""
                code = ""
                appState.authError = nil
            }
        }
    }
}
