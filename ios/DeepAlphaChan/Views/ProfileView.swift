import SwiftUI
import StoreKit

/// 我的：账号信息 + 语言 / 买卖点口径 / 帮助放一级，订阅 / 偏好设置 / 关于 / 账号与安全是二级入口 + 退出登录（功能都在 Views/Profile/ProfileSubpages.swift）。
struct ProfileView: View {
    @EnvironmentObject var auth: AuthViewModel
    @EnvironmentObject var localization: LocalizationManager
    @State private var showLogoutAlert = false
    /// 当前口径：直接读 UserDefaults（SignalMode 的存储键），从设置页返回时随之刷新行右侧的名字。
    @AppStorage(SignalMode.storageKey) private var savedMode = SignalMode.defaultKey
    private var signalMode: String { SignalMode.all.contains(savedMode) ? savedMode : SignalMode.defaultKey }

    var body: some View {
        NavigationStack {
            List {
                Section(L("账号")) {
                    if let p = auth.profile {
                        row(L("账号"), p.displayAccount)
                        if let name = p.username { row(L("用户名"), name) }
                    } else {
                        Text(L("加载中…")).foregroundColor(Theme.textSecondary)
                    }
                }

                // 语言：选完立刻生效（跟随系统 / 中文 / English）
                Section {
                    Picker(selection: $localization.preference) {
                        Text(L("跟随系统")).tag(AppLanguage?.none)
                        ForEach(AppLanguage.allCases) { lang in
                            Text(lang.nativeName).tag(AppLanguage?.some(lang))
                        }
                    } label: {
                        Label(L("语言"), systemImage: "globe")
                    }
                }

                // 买卖点口径：影响雷达 / 详情 / 次级别，放一级页方便随时切换
                Section {
                    NavigationLink { SignalModeSettingsView() } label: {
                        HStack {
                            Label(L("买卖点口径"), systemImage: "dial.medium")
                            Spacer()
                            Text(SignalMode.title(signalMode)).foregroundColor(Theme.textSecondary)
                        }
                    }
                } footer: {
                    Text(L("决定「什么算买卖点」：严格最少，中等约多一倍（默认），宽松最多。点进去看每种的区别。"))
                        .font(.caption2)
                }

                // 帮助：联系我们
                Section(L("帮助")) {
                    NavigationLink { ContactUsView() } label: {
                        Label(L("联系我们"), systemImage: "envelope")
                    }
                }

                // 其余功能都在二级页里
                Section {
                    NavigationLink { SubscriptionSettingsView() } label: {
                        HStack {
                            Label(L("订阅"), systemImage: "crown")
                            Spacer()
                            SubscriptionTierBadge()
                        }
                    }
                    NavigationLink { PreferencesView() } label: {
                        Label(L("偏好设置"), systemImage: "slider.horizontal.3")
                    }
                    NavigationLink { AboutView() } label: {
                        Label(L("关于"), systemImage: "info.circle")
                    }
                    NavigationLink { AccountSecurityView() } label: {
                        Label(L("账号与安全"), systemImage: "lock.shield")
                    }
                }

                Section {
                    Button(role: .destructive) {
                        showLogoutAlert = true
                    } label: {
                        Text(L("退出登录")).frame(maxWidth: .infinity)
                    }
                }
            }
            .navigationTitle(L("我的"))
            .navigationBarTitleDisplayMode(.inline)
            .task { if auth.profile == nil { await auth.loadProfile() } }
            .alert(L("确认退出登录？"), isPresented: $showLogoutAlert) {
                Button(L("取消"), role: .cancel) {}
                Button(L("退出"), role: .destructive) {
                    // 不需要 dismiss：登出后 RootView 会切回登录页
                    auth.logout()
                }
            }
        }
        // 隐私页显式声明不参与截图分享：账号在这里可见，不该被拼进分享图。
        // 不依赖「别的页面 onDisappear」这类间接推断 —— 弹层盖住时推断会失灵。
        .suppressScreenshotShare()
    }

    private func row(_ title: String, _ value: String) -> some View {
        HStack {
            Text(title).foregroundColor(Theme.textSecondary)
            Spacer()
            Text(value).foregroundColor(Theme.textPrimary)
        }
    }
}
