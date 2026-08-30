import SwiftUI
import DeepAlphaCore

/// 登录页。手机号 / 邮箱 + 密码，服务端判别账号类型（`/auth/login/account`）。
struct LoginView: View {
    @Environment(AppState.self) private var appState
    @AppStorage("remember_me") private var rememberMe = true

    @State private var channel: AccountChannel = .phone
    @State private var account = ""
    @State private var password = ""
    @State private var showRegister = false
    @State private var showForgotPassword = false
    @FocusState private var focused: Field?

    private enum Field { case account, password }

    private var canSubmit: Bool {
        AccountInput.isValid(account, channel: channel) && !password.isEmpty
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                header

                VStack(spacing: 14) {
                    AccountChannelPicker(channel: $channel)

                    AccountField(channel: channel, text: $account)
                        .focused($focused, equals: .account)
                        .submitLabel(.next)
                        .onSubmit { focused = .password }

                    AuthSecureField(icon: "lock", placeholder: "密码", text: $password)
                        .focused($focused, equals: .password)
                        .submitLabel(.go)
                        .onSubmit { submit() }

                    rememberAndForgot

                    if let error = appState.authError {
                        Text(error)
                            .font(.footnote)
                            .foregroundStyle(Theme.danger)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    AuthPrimaryButton(title: "登录", loadingTitle: "登录中…",
                                      loading: appState.loggingIn, enabled: canSubmit) {
                        submit()
                    }

                    Button {
                        appState.authError = nil
                        showRegister = true
                    } label: {
                        Text("没有账号？注册").font(.footnote)
                    }
                }
                .padding(20)
                .background(Theme.surface,
                            in: RoundedRectangle(cornerRadius: 16))

                Text("研究 / 分析用途，非投资建议，不执行真实交易。")
                    .font(.caption2)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(Theme.textTertiary)
            }
            .padding(24)
        }
        .themedBackground()
        .scrollDismissesKeyboard(.interactively)
        .sheet(isPresented: $showRegister) { RegisterView() }
        .sheet(isPresented: $showForgotPassword) { ForgotPasswordView(channel: channel) }
        .onChange(of: channel) { _, _ in
            // 切换通道时清空输入，否则手机号会留在邮箱框里显得莫名其妙
            account = ""
            appState.authError = nil
        }
    }

    private func submit() {
        focused = nil
        Task { await appState.login(account: account, password: password) }
    }

    private var header: some View {
        VStack(spacing: 8) {
            Image(systemName: "chart.line.uptrend.xyaxis")
                .font(.system(size: 48))
                .foregroundStyle(Theme.accent)
            Text("交易台")
                .font(.title.bold())
            Text("多智能体分析")
                .font(.caption.monospaced())
                .foregroundStyle(Theme.textSecondary)
        }
        .padding(.top, 40)
    }

    private var rememberAndForgot: some View {
        HStack {
            Button {
                rememberMe.toggle()
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: rememberMe ? "checkmark.square.fill" : "square")
                        .foregroundStyle(rememberMe ? Theme.accent : Theme.textSecondary)
                    Text("保持登录").font(.footnote).foregroundStyle(Theme.textSecondary)
                }
            }
            Spacer()
            Button {
                appState.authError = nil
                showForgotPassword = true
            } label: {
                Text("忘记密码？").font(.footnote)
            }
        }
    }
}
