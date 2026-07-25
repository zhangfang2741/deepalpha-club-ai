// Views/RegisterView.swift
import SwiftUI

struct RegisterView: View {
    @EnvironmentObject var auth: AuthViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var email = ""
    @State private var password = ""
    @State private var confirmPassword = ""

    private var hasUpper: Bool { password.contains { $0.isUppercase } }
    private var hasLower: Bool { password.contains { $0.isLowercase } }
    private var hasDigit: Bool { password.contains { $0.isNumber } }
    private var hasSpecial: Bool { password.contains { "!@#$%^&*()_+-=[]{}|;:,.<>?".contains($0) } }
    private var longEnough: Bool { password.count >= 8 }
    private var matched: Bool { !password.isEmpty && password == confirmPassword }

    private var canSubmit: Bool {
        !email.isEmpty && hasUpper && hasLower && hasDigit && hasSpecial && longEnough && matched
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                ScrollView {
                    VStack(spacing: 16) {
                        TextField("邮箱", text: $email)
                            .keyboardType(.emailAddress)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .padding()
                            .background(Theme.surface)
                            .foregroundStyle(Theme.textPrimary)
                            .clipShape(.rect(cornerRadius: 10))

                        SecureField("密码", text: $password)
                            .padding()
                            .background(Theme.surface)
                            .foregroundStyle(Theme.textPrimary)
                            .clipShape(.rect(cornerRadius: 10))

                        SecureField("确认密码", text: $confirmPassword)
                            .padding()
                            .background(Theme.surface)
                            .foregroundStyle(Theme.textPrimary)
                            .clipShape(.rect(cornerRadius: 10))

                        VStack(alignment: .leading, spacing: 6) {
                            checklistRow("至少 8 个字符", longEnough)
                            checklistRow("包含大写字母", hasUpper)
                            checklistRow("包含小写字母", hasLower)
                            checklistRow("包含数字", hasDigit)
                            checklistRow("包含特殊字符（如 !@#$%）", hasSpecial)
                            checklistRow("两次密码一致", matched)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)

                        if let errorMessage = auth.errorMessage {
                            Text(errorMessage)
                                .font(.footnote)
                                .foregroundStyle(Theme.unknown)
                        }

                        Button {
                            Task {
                                await auth.register(email: email, password: password)
                                if auth.isAuthenticated { dismiss() }
                            }
                        } label: {
                            HStack {
                                if auth.isLoading { ProgressView().tint(.white) }
                                Text(auth.isLoading ? "注册中…" : "注册").fontWeight(.semibold)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 14)
                            .background(canSubmit ? Theme.accent : Theme.surfaceAlt)
                            .foregroundStyle(.white)
                            .clipShape(.rect(cornerRadius: 12))
                        }
                        .disabled(!canSubmit || auth.isLoading)
                    }
                    .padding(24)
                }
            }
            .navigationTitle("注册")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private func checklistRow(_ text: String, _ satisfied: Bool) -> some View {
        HStack(spacing: 6) {
            // 图标是文字状态的视觉复述，对 VoiceOver 隐藏，避免"勾选，至少8个字符"这种
            // 冗余读法；改成把满足状态并进这一行的组合 label 里一次性读出。
            Image(systemName: satisfied ? "checkmark.circle.fill" : "circle")
                .foregroundStyle(satisfied ? Theme.known : Theme.textSecondary)
                .accessibilityHidden(true)
            Text(text)
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(text)，\(satisfied ? "已满足" : "未满足")")
    }
}
