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
    @State private var country: PhoneCountry
    @State private var code = ""
    @State private var password = ""
    @State private var confirm = ""
    @State private var done = false

    /// 从登录页带过来当前选中的通道和区号，省得用户再选一次。
    init(channel: AccountChannel = .phone, country: PhoneCountry = .default) {
        _channel = State(initialValue: channel)
        _country = State(initialValue: country)
    }

    private var rules: PasswordRules { PasswordRules(password: password) }
    private var matched: Bool { !confirm.isEmpty && password == confirm }

    /// 手机号通道下按选定国家的位数预校验，邮箱走邮箱格式校验。
    private var accountValid: Bool {
        switch channel {
        case .phone: return country.isValidNational(account)
        case .email: return AccountInput.isValidEmail(account)
        }
    }

    /// 提交给后端的账号：手机号拼成 E.164，邮箱原样。
    private var submittedAccount: String {
        channel == .phone ? country.e164(national: account) : account
    }

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

                        if channel == .phone {
                            PhoneNumberField(country: $country, national: $account)
                        } else {
                            AccountField(channel: channel, text: $account)
                        }

                        VerificationCodeField(code: $code, canRequest: accountValid) {
                            await auth.requestPasswordResetCode(account: submittedAccount, channel: channel)
                        }

                        AuthSecureField(icon: "lock", placeholder: L("新密码"), text: $password)
                        AuthSecureField(icon: "lock.rotation", placeholder: L("确认新密码"), text: $confirm)

                        rulesChecklist

                        if let error = auth.errorMessage {
                            Text(error).font(.footnote).foregroundColor(Theme.down)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        if done {
                            Text(L("密码已重置，请用新密码登录"))
                                .font(.footnote).foregroundColor(Theme.up)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        Button {
                            Task {
                                let ok = await auth.resetPassword(
                                    account: submittedAccount, channel: channel,
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
                                Text(auth.isLoading ? L("提交中…") : L("重置密码")).fontWeight(.semibold)
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
            .navigationTitle(L("找回密码"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(L("取消")) { auth.errorMessage = nil; dismiss() }
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
