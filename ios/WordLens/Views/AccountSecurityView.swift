import SwiftUI

struct AccountSecurityView: View {
    @ObservedObject var viewModel: SettingsViewModel

    @State private var oldPassword = ""
    @State private var newPassword = ""
    @State private var confirmPassword = ""

    // 与后端 VOCABULARY_PASSWORD_MIN_LENGTH 保持一致：只校验长度，不做字符组合要求。
    private static let passwordMinLength = 6

    private var longEnough: Bool { newPassword.count >= Self.passwordMinLength }
    private var matched: Bool { !newPassword.isEmpty && newPassword == confirmPassword }

    private var canSubmit: Bool {
        !oldPassword.isEmpty && longEnough && matched
    }

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()

            Form {
                Section {
                    SecureField(L("原密码"), text: $oldPassword)
                        .textContentType(.password)
                    SecureField(L("新密码"), text: $newPassword)
                        .textContentType(.newPassword)
                    SecureField(L("确认新密码"), text: $confirmPassword)
                        .textContentType(.newPassword)
                } header: {
                    Text(L("修改密码"))
                } footer: {
                    VStack(alignment: .leading, spacing: 8) {
                        requirementRow(L("至少 %lld 个字符", Self.passwordMinLength), isSatisfied: longEnough)
                        requirementRow(L("两次密码一致"), isSatisfied: matched)
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
                            Text(viewModel.isChangingPassword ? L("提交中...") : L("确认修改"))
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
        .navigationTitle(L("账户与安全"))
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
