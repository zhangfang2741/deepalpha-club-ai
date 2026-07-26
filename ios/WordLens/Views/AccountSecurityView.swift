import SwiftUI

struct AccountSecurityView: View {
    @ObservedObject var viewModel: SettingsViewModel

    @State private var oldPassword = ""
    @State private var newPassword = ""
    @State private var confirmPassword = ""

    // 后端密码规则只要求长度、字母和数字。
    private var hasLetter: Bool { newPassword.contains { $0.isLetter } }
    private var hasDigit: Bool { newPassword.contains { $0.isNumber } }
    private var longEnough: Bool { newPassword.count >= 8 }
    private var matched: Bool { !newPassword.isEmpty && newPassword == confirmPassword }

    private var canSubmit: Bool {
        !oldPassword.isEmpty && hasLetter && hasDigit && longEnough && matched
    }

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()

            Form {
                Section {
                    SecureField("原密码", text: $oldPassword)
                        .textContentType(.password)
                    SecureField("新密码", text: $newPassword)
                        .textContentType(.newPassword)
                    SecureField("确认新密码", text: $confirmPassword)
                        .textContentType(.newPassword)
                } header: {
                    Text("修改密码")
                } footer: {
                    VStack(alignment: .leading, spacing: 8) {
                        requirementRow("至少 8 个字符", isSatisfied: longEnough)
                        requirementRow("包含英文字母", isSatisfied: hasLetter)
                        requirementRow("包含数字", isSatisfied: hasDigit)
                        requirementRow("两次密码一致", isSatisfied: matched)
                    }
                    .padding(.top, 4)
                }
                .listRowBackground(Theme.surface)

                if let errorMessage = viewModel.passwordErrorMessage {
                    Section {
                        Label(errorMessage, systemImage: "exclamationmark.circle.fill")
                            .font(.footnote)
                            .foregroundStyle(Theme.unknown)
                    }
                    .listRowBackground(Theme.surface)
                }

                if let successMessage = viewModel.passwordSuccessMessage {
                    Section {
                        Label(successMessage, systemImage: "checkmark.circle.fill")
                            .font(.footnote)
                            .foregroundStyle(Theme.known)
                    }
                    .listRowBackground(Theme.surface)
                }

                Section {
                    Button {
                        Task { await submitPasswordChange() }
                    } label: {
                        HStack(spacing: 10) {
                            if viewModel.isChangingPassword {
                                ProgressView()
                                    .tint(Theme.textPrimary)
                            }
                            Text(viewModel.isChangingPassword ? "提交中..." : "确认修改")
                                .frame(maxWidth: .infinity)
                        }
                        .foregroundStyle(Theme.accent)
                    }
                    .disabled(!canSubmit || viewModel.isChangingPassword)
                }
                .listRowBackground(Theme.surface)
            }
            .disabled(viewModel.isChangingPassword)
            .scrollContentBackground(.hidden)
        }
        .navigationTitle("账户与安全")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func submitPasswordChange() async {
        let succeeded = await viewModel.changePassword(
            oldPassword: oldPassword,
            newPassword: newPassword
        )
        guard succeeded else { return }

        oldPassword = ""
        newPassword = ""
        confirmPassword = ""
    }

    private func requirementRow(_ title: String, isSatisfied: Bool) -> some View {
        Label {
            Text("\(title)：\(isSatisfied ? "已满足" : "未满足")")
                .foregroundStyle(Theme.textSecondary)
        } icon: {
            Image(systemName: isSatisfied ? "checkmark.circle.fill" : "circle")
                .foregroundStyle(isSatisfied ? Theme.known : Theme.textSecondary)
        }
        .font(.caption)
        .accessibilityElement(children: .combine)
    }
}
