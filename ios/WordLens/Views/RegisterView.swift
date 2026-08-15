// Views/RegisterView.swift
import SwiftUI

struct RegisterView: View {
    @EnvironmentObject var auth: AuthViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var email = ""
    @State private var password = ""
    @State private var confirmPassword = ""

    // 与后端 VOCABULARY_PASSWORD_MIN_LENGTH 保持一致：只校验长度，不做字符组合
    // 要求（NIST SP 800-63B 建议废弃组合规则，它不提升实际强度还抬高注册流失）。
    private var longEnough: Bool { password.count >= Self.passwordMinLength }
    private var matched: Bool { !password.isEmpty && password == confirmPassword }

    private static let passwordMinLength = 6

    private var canSubmit: Bool {
        !email.isEmpty && longEnough && matched
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
                            checklistRow("至少 \(Self.passwordMinLength) 个字符", longEnough)
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
                        .buttonStyle(.pressable)
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
