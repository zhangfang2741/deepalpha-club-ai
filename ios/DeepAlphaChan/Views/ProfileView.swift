import SwiftUI
import StoreKit

/// 我的：账号信息、语言、订阅、免责声明、登出。
struct ProfileView: View {
    @EnvironmentObject var auth: AuthViewModel
    @EnvironmentObject var store: StoreManager
    @EnvironmentObject var localization: LocalizationManager
    @State private var showLogoutAlert = false
    @State private var showDeleteAlert = false
    @State private var showPaywall = false
    @State private var showManageSubscriptions = false

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

                Section(L("偏好设置")) {
                    // 语言切换：跟随系统（按地区自动）/ 中文 / English。选完立刻生效。
                    Picker(selection: $localization.preference) {
                        Text(L("跟随系统")).tag(AppLanguage?.none)
                        ForEach(AppLanguage.allCases) { lang in
                            Text(lang.nativeName).tag(AppLanguage?.some(lang))
                        }
                    } label: {
                        Label(L("语言"), systemImage: "globe")
                    }
                }

                Section(L("订阅")) {
                    HStack {
                        Text(L("当前方案")).foregroundColor(Theme.textSecondary)
                        Spacer()
                        if store.isSubscribed {
                            Label(L("Pro 会员"), systemImage: "crown.fill")
                                .font(.subheadline.bold()).foregroundColor(Theme.segment)
                        } else {
                            Text(L("免费版")).foregroundColor(Theme.textPrimary)
                        }
                    }
                    if store.isSubscribed {
                        Button(L("管理订阅")) { showManageSubscriptions = true }
                    } else {
                        Button {
                            showPaywall = true
                        } label: {
                            Label(L("升级 Pro（7 天免费试用）"), systemImage: "crown.fill")
                                .foregroundColor(Theme.segment)
                        }
                    }
                    Button(L("恢复购买")) { Task { await store.restore() } }
                        .foregroundColor(Theme.accent)
                }

                Section(L("关于")) {
                    row(L("版本"), appVersion)
                    Link(destination: URL(string: "https://deepalpha.club/privacy")!) {
                        Text(L("隐私政策"))
                    }
                    Link(destination: URL(string: "https://deepalpha.club/terms")!) {
                        Text(L("服务条款"))
                    }
                }

                Section {
                    Text(L("本 App 提供的缠论结构识别、买卖点标注与操作倾向均由算法自动生成，仅供技术研究与学习参考，不构成任何投资建议或买卖要约。证券投资有风险，任何决策请自主判断并自负盈亏。"))
                        .font(.caption).foregroundColor(Theme.textSecondary)
                } header: {
                    Text(L("免责声明"))
                }

                Section {
                    Button(role: .destructive) {
                        showLogoutAlert = true
                    } label: {
                        Text(L("退出登录")).frame(maxWidth: .infinity)
                    }
                }

                Section {
                    Button(role: .destructive) {
                        showDeleteAlert = true
                    } label: {
                        HStack {
                            if auth.isLoading { ProgressView() }
                            Text(L("删除账号")).frame(maxWidth: .infinity)
                        }
                    }
                    .disabled(auth.isLoading)
                } footer: {
                    Text(L("删除账号将永久移除你的账户及关联数据，此操作不可恢复。"))
                        .font(.caption2)
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
            .sheet(isPresented: $showPaywall) { PaywallView() }
            .manageSubscriptionsSheet(isPresented: $showManageSubscriptions)
            .alert(L("确认删除账号？"), isPresented: $showDeleteAlert) {
                Button(L("取消"), role: .cancel) {}
                Button(L("永久删除"), role: .destructive) {
                    // deleteAccount 成功后内部会 logout，RootView 自动切回登录页
                    Task { _ = await auth.deleteAccount() }
                }
            } message: {
                Text(L("此操作将永久删除你的账号及关联数据，且不可恢复。"))
            }
        }
    }

    private func row(_ title: String, _ value: String) -> some View {
        HStack {
            Text(title).foregroundColor(Theme.textSecondary)
            Spacer()
            Text(value).foregroundColor(Theme.textPrimary)
        }
    }

    private var appVersion: String {
        let v = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        let b = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "1"
        return "\(v) (\(b))"
    }
}
