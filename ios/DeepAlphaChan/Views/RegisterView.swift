import SwiftUI

/// 注册页。手机号或邮箱 + 验证码 + 密码。
/// 密码规则对齐后端 validate_password_strength：8–64 位，含字母和数字。
struct RegisterView: View {
    @EnvironmentObject var auth: AuthViewModel
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
            ZStack {
                Theme.background.ignoresSafeArea()
                ScrollView {
                    VStack(spacing: 14) {
                        AccountChannelPicker(channel: $channel)

                        AccountField(channel: channel, text: $account)

                        VerificationCodeField(code: $code, canRequest: accountValid) {
                            await auth.requestRegisterCode(account: account, channel: channel)
                        }

                        AuthTextField(icon: "person", placeholder: L("用户名（可选）"), text: $username)
                            .autocorrectionDisabled()

                        AuthSecureField(icon: "lock", placeholder: L("密码"), text: $password)
                        AuthSecureField(icon: "lock.rotation", placeholder: L("确认密码"), text: $confirm)

                        rulesChecklist

                        if let error = auth.errorMessage {
                            Text(error).font(.footnote).foregroundColor(Theme.down)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        Button {
                            Task {
                                await auth.register(
                                    account: account, channel: channel, code: code,
                                    password: password, username: username)
                                if auth.isAuthenticated { dismiss() }
                            }
                        } label: {
                            HStack {
                                if auth.isLoading { ProgressView().tint(.white) }
                                Text(auth.isLoading ? L("注册中…") : L("注册并登录")).fontWeight(.semibold)
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
            .navigationTitle(L("注册"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(L("取消")) { auth.errorMessage = nil; dismiss() }
                }
            }
            .onChange(of: channel) { _, _ in
                // 切换通道时清空账号和验证码：验证码是绑在具体账号上的，留着只会误导
                account = ""
                code = ""
                auth.errorMessage = nil
            }
        }
    }

    private var rulesChecklist: some View {
        VStack(alignment: .leading, spacing: 6) {
            rule(L("8–64 位长度"), rules.longEnough)
            rule(L("含字母"), rules.hasLetter)
            rule(L("含数字"), rules.hasDigit)
            rule(L("两次密码一致"), matched)
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
