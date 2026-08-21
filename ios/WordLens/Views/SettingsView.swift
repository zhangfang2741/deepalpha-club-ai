// Views/SettingsView.swift
import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var auth: AuthViewModel
    @EnvironmentObject var localization: LocalizationManager
    @EnvironmentObject var store: StoreManager
    @EnvironmentObject var usage: UsageTracker
    @StateObject private var viewModel = SettingsViewModel()
    @State private var isDeleteAccountPresented = false
    @State private var isLogoutConfirmPresented = false
    @State private var showPaywall = false

    /// App Store 订阅管理页（用户在这里取消/改套餐）。
    private static let manageSubscriptionsURL = URL(string: "https://apps.apple.com/account/subscriptions")!

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
                Section(L("账户概览")) {
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
                                Text(L("注册于 %@", Self.formattedDate(profile.createdAt)))
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
                            Text(L("正在加载账户信息"))
                                .foregroundStyle(Theme.textSecondary)
                        }
                        .frame(minHeight: 50)
                    } else if let errorMessage = viewModel.profileErrorMessage {
                        HStack {
                            Label(errorMessage, systemImage: "exclamationmark.circle")
                                .foregroundStyle(Theme.textSecondary)
                            Spacer()
                            Button(L("重试")) {
                                Task { await viewModel.loadProfile() }
                            }
                        }
                    }
                }
                .listRowBackground(Theme.surface)

                // 订阅：会员显示状态 + 管理入口；免费用户显示今日剩余额度 +
                // 升级/恢复入口（App Store 审核要求 App 内可见订阅状态与恢复购买）。
                Section {
                    if store.isSubscribed {
                        HStack(spacing: 12) {
                            Image(systemName: "crown.fill")
                                .foregroundStyle(Theme.fuzzy)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(L("Pro 会员")).foregroundStyle(Theme.textPrimary)
                                Text(L("已解锁无限拍照与学习"))
                                    .font(.caption).foregroundStyle(Theme.textSecondary)
                            }
                        }
                        Link(destination: Self.manageSubscriptionsURL) {
                            Label(L("管理订阅"), systemImage: "gearshape")
                        }
                    } else {
                        Button {
                            showPaywall = true
                        } label: {
                            HStack(spacing: 12) {
                                Image(systemName: "crown.fill").foregroundStyle(Theme.fuzzy)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(L("升级 Pro")).foregroundStyle(Theme.textPrimary)
                                    Text(L("今日剩余拍照 %lld 次 · 学习 %lld 个", usage.photosRemaining, usage.wordsRemaining))
                                        .font(.caption).foregroundStyle(Theme.textSecondary)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.caption).foregroundStyle(Theme.textSecondary)
                            }
                        }
                        Button {
                            Task { await store.restore() }
                        } label: {
                            Label(L("恢复购买"), systemImage: "arrow.clockwise")
                        }
                    }
                } header: {
                    Text(L("订阅"))
                }
                .listRowBackground(Theme.surface)

                // 学习模式已挪到首页左上角的下拉框里：它跟「当前在播哪一组」
                // 是同一件事的两个侧面，放一起才成套。
                Section {
                    // 语言切换：跟随系统（按地区自动）/ 中文 / English。
                    // 选完立刻生效——LocalizationManager 改 @Published，App 根视图
                    // 换 locale 并靠 .id 重建，无需重启。
                    Picker(selection: $localization.preference) {
                        // nil = 跟随系统；其余选项由 AppLanguage.allCases 生成，
                        // 新增语言时这里自动出现，无需改动。
                        Text(L("跟随系统")).tag(AppLanguage?.none)
                        ForEach(AppLanguage.allCases) { lang in
                            Text(lang.nativeName).tag(AppLanguage?.some(lang))
                        }
                    } label: {
                        Label(L("语言"), systemImage: "globe")
                    }
                } header: {
                    Text(L("偏好设置"))
                } footer: {
                    Text(L("选择界面语言。默认根据所在地区自动判断：中国大陆显示中文，其它地区显示英文。"))
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                }
                .listRowBackground(Theme.surface)

                Section {
                    NavigationLink {
                        PronunciationSettingsView()
                    } label: {
                        Label(L("发音设置"), systemImage: "speaker.wave.2")
                    }
                }
                .listRowBackground(Theme.surface)

                Section(L("账户")) {
                    NavigationLink {
                        AccountSecurityView(viewModel: viewModel)
                    } label: {
                        Label(L("账户与安全"), systemImage: "lock.shield")
                    }
                }
                .listRowBackground(Theme.surface)

                // 隐私政策 / 服务条款：App Store Connect 要求填隐私政策 URL，
                // 审核员也会检查 App 内可达。
                Section(L("关于")) {
                    Link(destination: AppConfig.privacyPolicyURL) {
                        Label(L("隐私政策"), systemImage: "hand.raised")
                    }
                    Link(destination: AppConfig.termsOfServiceURL) {
                        Label(L("服务条款"), systemImage: "doc.text")
                    }
                    LabeledContent {
                        Text(Self.appVersion).foregroundStyle(Theme.textSecondary)
                    } label: {
                        Label(L("版本"), systemImage: "info.circle")
                    }
                }
                .listRowBackground(Theme.surface)

                Section {
                    Button(role: .destructive) {
                        isLogoutConfirmPresented = true
                    } label: {
                        Label(L("退出登录"), systemImage: "rectangle.portrait.and.arrow.right")
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
                        Label(L("删除账号"), systemImage: "trash")
                            .font(.subheadline)
                    }
                } footer: {
                    Text(L("删除后账号与全部生词、复习进度将被永久清除，无法恢复。"))
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                }
                .listRowBackground(Theme.surface)
            }
            .scrollContentBackground(.hidden)
        }
        .navigationTitle(L("设置"))
        .navigationBarTitleDisplayMode(.inline)
        .task { await viewModel.loadProfile() }
        // 退出登录本身可逆（重新登录即可），但手机号/邮箱用户未必记得住密码，
        // 误触后要走一遍找回密码才能回来。用 confirmationDialog 而不是 alert：
        // 前者从底部升起，破坏性操作用它是 iOS 的惯例。
        .confirmationDialog(
            L("确定要退出登录吗？"),
            isPresented: $isLogoutConfirmPresented,
            titleVisibility: .visible
        ) {
            Button(L("退出登录"), role: .destructive) { auth.logout() }
            Button(L("取消"), role: .cancel) {}
        } message: {
            Text(L("退出后需要重新输入账号和密码才能登录。你的生词和复习进度都保存在云端，不会丢失。"))
        }
        .sheet(isPresented: $isDeleteAccountPresented) {
            // 账号已在服务端删除，本地 token 也就作废了，直接登出跳回登录页。
            DeleteAccountView(viewModel: viewModel) { auth.logout() }
        }
        .sheet(isPresented: $showPaywall) { PaywallView() }
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
