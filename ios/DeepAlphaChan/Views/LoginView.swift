import SwiftUI
import AuthenticationServices

/// 登录页。支持：手机号/邮箱 + 密码登录、注册、找回密码、Sign in with Apple。
struct LoginView: View {
    @EnvironmentObject var auth: AuthViewModel
    @State private var channel: AccountChannel = .phone
    @State private var account = ""
    @State private var password = ""
    @State private var showRegister = false
    @State private var showForgotPassword = false
    @State private var showLearn = false
    @FocusState private var focused: Field?

    private enum Field { case account, password }

    private var canSubmit: Bool {
        AccountInput.isValid(account, channel: channel) && !password.isEmpty
    }

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            VStack(spacing: 24) {
                Spacer()
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

                    if let error = auth.errorMessage {
                        Text(error)
                            .font(.footnote)
                            .foregroundColor(Theme.down)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    Button {
                        submit()
                    } label: {
                        HStack {
                            if auth.isLoading { ProgressView().tint(.white) }
                            Text(auth.isLoading ? "登录中…" : "登录")
                                .fontWeight(.semibold)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(canSubmit ? Theme.accent : Theme.surfaceAlt)
                        .foregroundColor(canSubmit ? .white : Theme.textSecondary)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                    .disabled(!canSubmit || auth.isLoading)

                    Button {
                        auth.errorMessage = nil
                        showRegister = true
                    } label: {
                        Text("没有账号？注册").font(.footnote).foregroundColor(Theme.accent)
                    }

                    // 不登录也能看教程。App Store 审核指南 5.1.1(i) 不希望 App
                    // 把所有内容都锁在注册墙后面；这里也确实没必要——教程是静态
                    // 内容，看不看得到跟有没有账号无关。
                    Button {
                        showLearn = true
                    } label: {
                        Label("先看看缠论入门", systemImage: "book")
                            .font(.footnote)
                            .foregroundColor(Theme.textSecondary)
                    }

                    dividerOr

                    SignInWithAppleButton(.signIn) { request in
                        request.requestedScopes = [.fullName, .email]
                    } onCompletion: { result in
                        handleApple(result)
                    }
                    .signInWithAppleButtonStyle(.white)
                    .frame(height: 48)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                }
                .padding(20)
                .background(Theme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 16))

                Spacer()

                Text("本 App 内容仅供技术研究与学习，不构成任何投资建议。\n投资有风险，决策需自主判断。")
                    .font(.caption2)
                    .multilineTextAlignment(.center)
                    .foregroundColor(Theme.textSecondary)
            }
            .padding(24)
        }
        .sheet(isPresented: $showRegister) { RegisterView() }
        .sheet(isPresented: $showForgotPassword) { ForgotPasswordView(channel: channel) }
        .sheet(isPresented: $showLearn) { LearnTabView() }
        .onChange(of: channel) { _, _ in
            // 切换通道时清空输入，否则手机号会留在邮箱框里显得莫名其妙
            account = ""
            auth.errorMessage = nil
        }
    }

    private func submit() {
        focused = nil
        Task { await auth.login(account: account, password: password) }
    }

    private var header: some View {
        VStack(spacing: 8) {
            Image(systemName: "waveform.path.ecg")
                .font(.system(size: 44))
                .foregroundStyle(Theme.accent)
            Text("DeepAlpha 缠论")
                .font(.title.bold())
                .foregroundColor(Theme.textPrimary)
            Text("结构化技术分析")
                .font(.subheadline)
                .foregroundColor(Theme.textSecondary)
        }
    }

    private var rememberAndForgot: some View {
        HStack {
            Button {
                auth.rememberMe.toggle()
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: auth.rememberMe ? "checkmark.square.fill" : "square")
                        .foregroundColor(auth.rememberMe ? Theme.accent : Theme.textSecondary)
                    Text("保持登录").font(.footnote).foregroundColor(Theme.textSecondary)
                }
            }
            Spacer()
            Button {
                auth.errorMessage = nil
                showForgotPassword = true
            } label: {
                Text("忘记密码？").font(.footnote).foregroundColor(Theme.accent)
            }
        }
    }

    // MARK: - Sign in with Apple 处理

    private func handleApple(_ result: Result<ASAuthorization, Error>) {
        switch result {
        case .success(let authorization):
            guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
                  let tokenData = credential.identityToken,
                  let token = String(data: tokenData, encoding: .utf8) else {
                auth.errorMessage = "无法获取 Apple 身份令牌"
                return
            }
            let name = [credential.fullName?.givenName, credential.fullName?.familyName]
                .compactMap { $0 }.joined(separator: " ")
            Task { await auth.loginWithApple(identityToken: token, fullName: name.isEmpty ? nil : name) }
        case .failure(let error):
            // 用户主动取消不提示
            if (error as NSError).code != ASAuthorizationError.canceled.rawValue {
                auth.errorMessage = "Apple 登录失败，请重试"
            }
        }
    }

    private var dividerOr: some View {
        HStack(spacing: 10) {
            Rectangle().fill(Theme.border).frame(height: 1)
            Text("或").font(.caption2).foregroundColor(Theme.textSecondary)
            Rectangle().fill(Theme.border).frame(height: 1)
        }
    }
}
