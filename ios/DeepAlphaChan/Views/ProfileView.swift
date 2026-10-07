import SwiftUI
import StoreKit

/// 我的：账号信息 + 语言 / 帮助放一级，订阅 / 偏好设置 / 关于 / 账号与安全是二级入口 + 退出登录（功能都在 Views/Profile/ProfileSubpages.swift）。
struct ProfileView: View {
    @EnvironmentObject var auth: AuthViewModel
    @EnvironmentObject var localization: LocalizationManager
    @State private var showTour = false
    @State private var showLogoutAlert = false

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

                // 帮助：新手导览 + 联系我们
                Section(L("帮助")) {
                    Button { showTour = true } label: {
                        Label(L("重看新手导览"), systemImage: "play.circle")
                    }
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
            .sheet(isPresented: $showTour) { OnboardingTourView() }
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
