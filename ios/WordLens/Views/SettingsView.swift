// Views/SettingsView.swift
import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var auth: AuthViewModel
    @StateObject private var viewModel = SettingsViewModel()

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            Form {
                Section("账户概览") {
                    if let profile = viewModel.profile {
                        HStack(spacing: 14) {
                            Image(systemName: "person.crop.circle.fill")
                                .font(.system(size: 42))
                                .foregroundStyle(Theme.accent)
                                .accessibilityHidden(true)

                            VStack(alignment: .leading, spacing: 4) {
                                Text(profile.email)
                                    .font(.body.weight(.medium))
                                    .foregroundStyle(Theme.textPrimary)
                                    .lineLimit(2)
                                    .textSelection(.enabled)
                                Text("注册于 \(Self.formattedDate(profile.createdAt))")
                                    .font(.footnote)
                                    .foregroundStyle(Theme.textSecondary)
                            }
                        }
                        .padding(.vertical, 4)
                        .accessibilityElement(children: .combine)
                    } else if viewModel.isLoadingProfile {
                        HStack(spacing: 12) {
                            ProgressView()
                                .tint(Theme.accent)
                            Text("正在加载账户信息")
                                .foregroundStyle(Theme.textSecondary)
                        }
                        .frame(minHeight: 50)
                    } else if let errorMessage = viewModel.profileErrorMessage {
                        HStack {
                            Label(errorMessage, systemImage: "exclamationmark.circle")
                                .foregroundStyle(Theme.textSecondary)
                            Spacer()
                            Button("重试") {
                                Task { await viewModel.loadProfile() }
                            }
                        }
                    }
                }
                .listRowBackground(Theme.surface)

                Section("偏好设置") {
                    NavigationLink {
                        PronunciationSettingsView()
                    } label: {
                        Label("发音设置", systemImage: "speaker.wave.2")
                    }
                }
                .listRowBackground(Theme.surface)

                Section("账户") {
                    NavigationLink {
                        AccountSecurityView(viewModel: viewModel)
                    } label: {
                        Label("账户与安全", systemImage: "lock.shield")
                    }
                }
                .listRowBackground(Theme.surface)

                Section {
                    Button(role: .destructive) {
                        auth.logout()
                    } label: {
                        Label("退出登录", systemImage: "rectangle.portrait.and.arrow.right")
                            .font(.subheadline)
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
