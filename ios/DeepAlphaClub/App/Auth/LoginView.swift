import SwiftUI
import DeepAlphaCore

struct LoginView: View {
    @Environment(AppState.self) private var appState
    @State private var email = ""
    @State private var password = ""

    var body: some View {
        VStack(spacing: 24) {
            Spacer()
            Image(systemName: "chart.line.uptrend.xyaxis")
                .font(.system(size: 56))
                .foregroundStyle(.blue)
            VStack(spacing: 6) {
                Text("交易台")
                    .font(.title.bold())
                Text("多智能体分析")
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
            }
            Spacer()

            VStack(spacing: 14) {
                TextField("邮箱", text: $email)
                    .textContentType(.emailAddress)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .textFieldStyle(.roundedBorder)
                SecureField("密码", text: $password)
                    .textContentType(.password)
                    .submitLabel(.go)
                    .onSubmit { login() }
                    .textFieldStyle(.roundedBorder)

                if let err = appState.authError {
                    Text(err)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                Button {
                    login()
                } label: {
                    if appState.loggingIn {
                        ProgressView().frame(maxWidth: .infinity)
                    } else {
                        Text("登录")
                            .frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(email.isEmpty || password.isEmpty || appState.loggingIn)
            }
            Spacer().frame(height: 80)
        }
        .padding(24)
    }

    private func login() {
        Task { await appState.login(email: email, password: password) }
    }
}
