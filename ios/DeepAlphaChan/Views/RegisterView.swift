import SwiftUI

/// 注册页。对齐后端密码强度要求：8–64 位，含大小写字母、数字、特殊字符。
struct RegisterView: View {
    @EnvironmentObject var auth: AuthViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var email = ""
    @State private var username = ""
    @State private var password = ""
    @State private var confirm = ""

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                ScrollView {
                    VStack(spacing: 14) {
                        field(icon: "envelope", placeholder: "邮箱", text: $email)
                            .keyboardType(.emailAddress)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()

                        field(icon: "person", placeholder: "用户名（可选）", text: $username)
                            .autocorrectionDisabled()

                        secureField(icon: "lock", placeholder: "密码", text: $password)
                        secureField(icon: "lock.rotation", placeholder: "确认密码", text: $confirm)

                        rulesChecklist

                        if let error = auth.errorMessage {
                            Text(error).font(.footnote).foregroundColor(Theme.down)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        Button {
                            Task {
                                await auth.register(email: email, password: password,
                                                    username: username)
                                if auth.isAuthenticated { dismiss() }
                            }
                        } label: {
                            HStack {
                                if auth.isLoading { ProgressView().tint(.white) }
                                Text(auth.isLoading ? "注册中…" : "注册并登录").fontWeight(.semibold)
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
            .navigationTitle("注册")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("取消") { auth.errorMessage = nil; dismiss() }
                }
            }
        }
    }

    // MARK: - 校验

    private var hasUpper: Bool { password.range(of: "[A-Z]", options: .regularExpression) != nil }
    private var hasLower: Bool { password.range(of: "[a-z]", options: .regularExpression) != nil }
    private var hasDigit: Bool { password.range(of: "[0-9]", options: .regularExpression) != nil }
    private var hasSpecial: Bool { password.range(of: "[!@#$%^&*(),.?\":{}|<>]", options: .regularExpression) != nil }
    private var longEnough: Bool { password.count >= 8 && password.count <= 64 }
    private var matched: Bool { !confirm.isEmpty && password == confirm }

    private var canSubmit: Bool {
        !email.isEmpty && hasUpper && hasLower && hasDigit && hasSpecial && longEnough && matched
    }

    private var rulesChecklist: some View {
        VStack(alignment: .leading, spacing: 6) {
            rule("8–64 位长度", longEnough)
            rule("含大写字母", hasUpper)
            rule("含小写字母", hasLower)
            rule("含数字", hasDigit)
            rule("含特殊字符（如 !@#$%^&*）", hasSpecial)
            rule("两次密码一致", matched)
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

    private func field(icon: String, placeholder: String, text: Binding<String>) -> some View {
        HStack {
            Image(systemName: icon).foregroundColor(Theme.textSecondary).frame(width: 20)
            TextField(placeholder, text: text).foregroundColor(Theme.textPrimary)
        }
        .padding(12).background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func secureField(icon: String, placeholder: String, text: Binding<String>) -> some View {
        HStack {
            Image(systemName: icon).foregroundColor(Theme.textSecondary).frame(width: 20)
            SecureField(placeholder, text: text).foregroundColor(Theme.textPrimary)
        }
        .padding(12).background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}
