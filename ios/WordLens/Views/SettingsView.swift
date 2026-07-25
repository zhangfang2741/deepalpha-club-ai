// Views/SettingsView.swift
import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var auth: AuthViewModel
    @StateObject private var viewModel = SettingsViewModel()
    @State private var voiceGender: PronunciationVoiceGender = PronunciationVoiceGender.current

    @State private var oldPassword = ""
    @State private var newPassword = ""
    @State private var confirmPassword = ""

    // 后端 validate_vocabulary_password_strength() 只要求字母+数字。
    private var hasLetter: Bool { newPassword.contains { $0.isLetter } }
    private var hasDigit: Bool { newPassword.contains { $0.isNumber } }
    private var longEnough: Bool { newPassword.count >= 8 }
    private var matched: Bool { !newPassword.isEmpty && newPassword == confirmPassword }

    private var canSubmitPasswordChange: Bool {
        !oldPassword.isEmpty && hasLetter && hasDigit && longEnough && matched
    }

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            Form {
                Section("个人信息") {
                    if let profile = viewModel.profile {
                        LabeledContent("邮箱", value: profile.email)
                        LabeledContent("注册时间", value: Self.formattedDate(profile.createdAt))
                    } else if viewModel.isLoadingProfile {
                        ProgressView()
                    }
                }
                .listRowBackground(Theme.surface)

                Section("发音音色") {
                    Picker("音色", selection: $voiceGender) {
                        Text("女声").tag(PronunciationVoiceGender.female)
                        Text("男声").tag(PronunciationVoiceGender.male)
                    }
                    .pickerStyle(.segmented)
                    .onChange(of: voiceGender) { _, newValue in
                        PronunciationVoiceGender.current = newValue
                    }
                }
                .listRowBackground(Theme.surface)

                Section("修改密码") {
                    SecureField("原密码", text: $oldPassword)
                    SecureField("新密码", text: $newPassword)
                    SecureField("确认新密码", text: $confirmPassword)

                    VStack(alignment: .leading, spacing: 6) {
                        checklistRow("至少 8 个字符", longEnough)
                        checklistRow("包含英文字母", hasLetter)
                        checklistRow("包含数字", hasDigit)
                        checklistRow("两次密码一致", matched)
                    }

                    if let errorMessage = viewModel.passwordErrorMessage {
                        Text(errorMessage).font(.footnote).foregroundStyle(Theme.unknown)
                    }
                    if let successMessage = viewModel.passwordSuccessMessage {
                        Text(successMessage).font(.footnote).foregroundStyle(Theme.known)
                    }

                    Button {
                        Task {
                            let ok = await viewModel.changePassword(oldPassword: oldPassword, newPassword: newPassword)
                            if ok {
                                oldPassword = ""
                                newPassword = ""
                                confirmPassword = ""
                            }
                        }
                    } label: {
                        HStack {
                            if viewModel.isChangingPassword { ProgressView() }
                            Text(viewModel.isChangingPassword ? "提交中…" : "确认修改")
                        }
                    }
                    .disabled(!canSubmitPasswordChange || viewModel.isChangingPassword)
                }
                .listRowBackground(Theme.surface)

                Section {
                    Button("退出登录", role: .destructive) {
                        auth.logout()
                    }
                }
                .listRowBackground(Theme.surface)
            }
            .scrollContentBackground(.hidden)
        }
        .navigationTitle("设置")
        .navigationBarTitleDisplayMode(.inline)
        .task { await viewModel.loadProfile() }
    }

    private func checklistRow(_ text: String, _ satisfied: Bool) -> some View {
        HStack(spacing: 6) {
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

    /// 后端返回不带时区的 ISO 8601 字符串（naive UTC），解析后按本地时区格式化。
    private static func formattedDate(_ raw: String) -> String {
        for format in ["yyyy-MM-dd'T'HH:mm:ss.SSSSSS", "yyyy-MM-dd'T'HH:mm:ss"] {
            let parser = DateFormatter()
            parser.locale = Locale(identifier: "en_US_POSIX")
            parser.timeZone = TimeZone(identifier: "UTC")
            parser.dateFormat = format
            if let date = parser.date(from: raw) {
                let formatter = DateFormatter()
                formatter.locale = Locale(identifier: "zh_CN")
                formatter.dateFormat = "yyyy年M月d日"
                return formatter.string(from: date)
            }
        }
        return raw
    }
}
