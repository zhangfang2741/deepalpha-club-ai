// Views/LoginView.swift
import SwiftUI

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
                    Text("鸟语")
                        .font(.system(size: 32, weight: .bold))
                        .foregroundColor(Theme.textPrimary)
                    Text("拍照背单词")
                        .font(.subheadline)
                        .foregroundColor(Theme.textSecondary)
                }

                VStack(spacing: 12) {
                    field("邮箱", text: $email, keyboard: .emailAddress)
                        .focused($focused, equals: .email)
                    secureField("密码", text: $password)
                        .focused($focused, equals: .password)
                }

                if let errorMessage = auth.errorMessage {
                    Text(errorMessage)
                        .font(.footnote)
                        .foregroundColor(Theme.unknown)
                }

                Button {
                    focused = nil
                    Task { await auth.login(email: email, password: password) }
                } label: {
                    HStack {
                        if auth.isLoading { ProgressView().tint(.white) }
                        Text(auth.isLoading ? "登录中…" : "登录").fontWeight(.semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(Theme.accent)
                    .foregroundColor(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                }
                .disabled(auth.isLoading)

                Button("还没有账号？去注册") { showRegister = true }
                    .font(.footnote)
                    .foregroundColor(Theme.textSecondary)

                Spacer()
                Spacer()
            }
            .padding(24)
        }
        .sheet(isPresented: $showRegister) { RegisterView() }
    }

    private func field(_ placeholder: String, text: Binding<String>, keyboard: UIKeyboardType) -> some View {
        TextField(placeholder, text: text)
            .keyboardType(keyboard)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .padding()
            .background(Theme.surface)
            .foregroundColor(Theme.textPrimary)
            .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func secureField(_ placeholder: String, text: Binding<String>) -> some View {
        SecureField(placeholder, text: text)
            .padding()
            .background(Theme.surface)
            .foregroundColor(Theme.textPrimary)
            .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}
