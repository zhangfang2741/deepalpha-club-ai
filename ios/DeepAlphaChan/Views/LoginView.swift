import SwiftUI
import AuthenticationServices

/// 登录页。支持：后端 JWT 账号密码登录、注册、Sign in with Apple。
struct LoginView: View {
    @EnvironmentObject var auth: AuthViewModel
    @State private var email = ""
    @State private var password = ""
    @State private var showRegister = false
    @FocusState private var focused: Field?

    private enum Field { case email, password }

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            VStack(spacing: 24) {
                Spacer()
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

                VStack(spacing: 14) {
                    field(icon: "envelope", placeholder: "邮箱", text: $email)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .focused($focused, equals: .email)
                        .submitLabel(.next)
                        .onSubmit { focused = .password }

                    secureField(icon: "lock", placeholder: "密码", text: $password)
                        .focused($focused, equals: .password)
                        .submitLabel(.go)
                        .onSubmit { Task { await auth.login(email: email, password: password) } }

                    if let error = auth.errorMessage {
                        Text(error)
                            .font(.footnote)
                            .foregroundColor(Theme.down)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    Button {
                        focused = nil
                        Task { await auth.login(email: email, password: password) }
                    } label: {
                        HStack {
                            if auth.isLoading { ProgressView().tint(.white) }
                            Text(auth.isLoading ? "登录中…" : "登录")
                                .fontWeight(.semibold)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Theme.accent)
                        .foregroundColor(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                    .disabled(auth.isLoading)

                    Button {
                        auth.errorMessage = nil
                        showRegister = true
                    } label: {
                        Text("没有账号？注册").font(.footnote).foregroundColor(Theme.accent)
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

    private func field(icon: String, placeholder: String, text: Binding<String>) -> some View {
        HStack {
            Image(systemName: icon).foregroundColor(Theme.textSecondary).frame(width: 20)
            TextField(placeholder, text: text)
                .foregroundColor(Theme.textPrimary)
        }
        .padding(12)
        .background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func secureField(icon: String, placeholder: String, text: Binding<String>) -> some View {
        HStack {
            Image(systemName: icon).foregroundColor(Theme.textSecondary).frame(width: 20)
            SecureField(placeholder, text: text)
                .foregroundColor(Theme.textPrimary)
        }
        .padding(12)
        .background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}
