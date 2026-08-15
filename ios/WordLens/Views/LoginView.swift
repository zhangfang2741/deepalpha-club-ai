// Views/LoginView.swift
import SwiftUI

struct LoginView: View {
    @EnvironmentObject var auth: AuthViewModel
    @State private var account = ""
    @State private var password = ""
    @State private var showRegister = false
    @State private var showForgotPassword = false
    /// 默认手机号：国内用户手机号比邮箱好记，也是更普遍的习惯。
    @State private var method: LoginMethod = .phone
    @FocusState private var focused: Field?

    private enum Field { case account, password }

    /// 登录方式。切换时清空账号栏——手机号和邮箱互相不是有效输入，
    /// 留着上一个只会让用户对着一条格式错误发懵。
    enum LoginMethod: String, CaseIterable {
        case phone, email

        var label: String { self == .phone ? "手机号" : "邮箱" }
        var placeholder: String { self == .phone ? "手机号" : "邮箱" }
    }

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            VStack(spacing: 24) {
                Spacer()
                VStack(spacing: 8) {
                    // 从 Info.plist 读，别硬编码：登录页标题、桌面图标名、App Store
                    // 商店名三者必须一致（指南 2.3.8），硬编码过一次就漏过一次。
                    Text(AppConfig.displayName)
                        .font(.system(size: 32, weight: .bold))
                        .foregroundStyle(Theme.textPrimary)
                    Text("拍照背单词")
                        .font(.subheadline)
                        .foregroundStyle(Theme.textSecondary)
                }

                SegmentedToggle(
                    options: LoginMethod.allCases,
                    label: \.label,
                    selection: $method
                )
                .onChange(of: method) { _, _ in
                    account = ""
                    auth.clearError()
                }

                VStack(spacing: 12) {
                    field(
                        method.placeholder,
                        text: $account,
                        keyboard: method == .phone ? .phonePad : .emailAddress
                    )
                    .focused($focused, equals: .account)
                    secureField("密码", text: $password)
                        .focused($focused, equals: .password)
                }

                if let errorMessage = auth.errorMessage {
                    Text(errorMessage)
                        .font(.footnote)
                        .foregroundStyle(Theme.unknown)
                }

                Button {
                    focused = nil
                    Task {
                        switch method {
                        case .phone: await auth.loginByPhone(phone: account, password: password)
                        case .email: await auth.login(email: account, password: password)
                        }
                    }
                } label: {
                    HStack {
                        if auth.isLoading { ProgressView().tint(.white) }
                        Text(auth.isLoading ? "登录中…" : "登录").fontWeight(.semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(Theme.accent)
                    .foregroundStyle(.white)
                    .clipShape(.rect(cornerRadius: 12))
                }
                .buttonStyle(.pressable)
                .disabled(auth.isLoading)

                Button("还没有账号？去注册") { showRegister = true }
                    .font(.footnote)
                    .foregroundStyle(Theme.textSecondary)
                    .buttonStyle(.pressable)

                Button("忘记密码？") { showForgotPassword = true }
                    .font(.footnote)
                    .foregroundStyle(Theme.textSecondary)
                    .buttonStyle(.pressable)

                Spacer()
                Spacer()
            }
            .padding(24)
        }
        .sheet(isPresented: $showRegister) { RegisterView(initialMethod: method) }
        // 把已填的邮箱带过去，用户不用再输一遍——他多半就是在这一栏卡住的。
        .sheet(isPresented: $showForgotPassword) { ForgotPasswordView(initialAccount: account, method: method) }
    }

    private func field(_ placeholder: String, text: Binding<String>, keyboard: UIKeyboardType) -> some View {
        TextField(placeholder, text: text)
            .keyboardType(keyboard)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .padding()
            .background(Theme.surface)
            .foregroundStyle(Theme.textPrimary)
            .clipShape(.rect(cornerRadius: 10))
    }

    private func secureField(_ placeholder: String, text: Binding<String>) -> some View {
        SecureField(placeholder, text: text)
            .padding()
            .background(Theme.surface)
            .foregroundStyle(Theme.textPrimary)
            .clipShape(.rect(cornerRadius: 10))
    }
}
