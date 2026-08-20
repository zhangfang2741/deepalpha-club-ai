// Views/SettingsView.swift
import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var auth: AuthViewModel
    @EnvironmentObject var localization: LocalizationManager
    @StateObject private var viewModel = SettingsViewModel()
    @State private var isDeleteAccountPresented = false
    @State private var isLogoutConfirmPresented = false

    /// 「1.0 (1)」：MARKETING_VERSION + CURRENT_PROJECT_VERSION，报障时好定位。
    private static var appVersion: String {
        let info = Bundle.main.infoDictionary
        let short = info?["CFBundleShortVersionString"] as? String ?? "—"
        let build = info?["CFBundleVersion"] as? String ?? "—"
        return "\(short) (\(build))"
    }

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
                                Text(profile.displayIdentifier)
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

                // 学习模式已挪到首页左上角的下拉框里：它跟「当前在播哪一组」
                // 是同一件事的两个侧面，放一起才成套。
                Section {
                    // 语言切换：跟随系统（按地区自动）/ 中文 / English。
                    // 选完立刻生效——LocalizationManager 改 @Published，App 根视图
                    // 换 locale 并靠 .id 重建，无需重启。
                    Picker(selection: $localization.preference) {
                        Text("跟随系统").tag(LanguagePreference.system)
                        Text(AppLanguage.chinese.nativeName).tag(LanguagePreference.chinese)
                        Text(AppLanguage.english.nativeName).tag(LanguagePreference.english)
                    } label: {
                        Label("语言", systemImage: "globe")
                    }
                } header: {
                    Text("偏好设置")
                } footer: {
                    Text("选择界面语言。默认根据所在地区自动判断：中国大陆显示中文，其它地区显示英文。")
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                }
                .listRowBackground(Theme.surface)

                Section {
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

                // 隐私政策 / 服务条款：App Store Connect 要求填隐私政策 URL，
                // 审核员也会检查 App 内可达。
                Section("关于") {
                    Link(destination: AppConfig.privacyPolicyURL) {
                        Label("隐私政策", systemImage: "hand.raised")
                    }
                    Link(destination: AppConfig.termsOfServiceURL) {
                        Label("服务条款", systemImage: "doc.text")
                    }
                    LabeledContent {
                        Text(Self.appVersion).foregroundStyle(Theme.textSecondary)
                    } label: {
                        Label("版本", systemImage: "info.circle")
                    }
                }
                .listRowBackground(Theme.surface)

                Section {
                    Button(role: .destructive) {
                        isLogoutConfirmPresented = true
                    } label: {
                        Label("退出登录", systemImage: "rectangle.portrait.and.arrow.right")
                            .font(.subheadline)
                    }
                }
                .listRowBackground(Theme.surface)

                // 删除账号：指南 5.1.1(v) 强制要求，单独成组和「退出登录」拉开
                // 距离，避免误点。
                Section {
                    Button(role: .destructive) {
                        isDeleteAccountPresented = true
                    } label: {
                        Label("删除账号", systemImage: "trash")
                            .font(.subheadline)
                    }
                } footer: {
                    Text("删除后账号与全部生词、复习进度将被永久清除，无法恢复。")
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                }
                .listRowBackground(Theme.surface)
            }
            .scrollContentBackground(.hidden)
        }
        .navigationTitle("设置")
        .navigationBarTitleDisplayMode(.inline)
        .task { await viewModel.loadProfile() }
        // 退出登录本身可逆（重新登录即可），但手机号/邮箱用户未必记得住密码，
        // 误触后要走一遍找回密码才能回来。用 confirmationDialog 而不是 alert：
        // 前者从底部升起，破坏性操作用它是 iOS 的惯例。
        .confirmationDialog(
            "确定要退出登录吗？",
            isPresented: $isLogoutConfirmPresented,
            titleVisibility: .visible
        ) {
            Button("退出登录", role: .destructive) { auth.logout() }
            Button("取消", role: .cancel) {}
        } message: {
            Text("退出后需要重新输入账号和密码才能登录。你的生词和复习进度都保存在云端，不会丢失。")
        }
        .sheet(isPresented: $isDeleteAccountPresented) {
            // 账号已在服务端删除，本地 token 也就作废了，直接登出跳回登录页。
            DeleteAccountView(viewModel: viewModel) { auth.logout() }
        }
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
                formatter.locale = Locale(identifier: Localized.language().localeIdentifier)
                formatter.dateFormat = L("yyyy年M月d日")
                return formatter.string(from: date)
            }
        }
        return raw
    }
}
