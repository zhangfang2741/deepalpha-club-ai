import SwiftUI

/// 登录页。复用后端 JWT 账号密码登录。
struct LoginView: View {
    @EnvironmentObject var auth: AuthViewModel
    @State private var email = ""
    @State private var password = ""
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
