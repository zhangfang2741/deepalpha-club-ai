import SwiftUI
import StoreKit

// 「我的」里的二级页：把低频功能收进去，一级页只留账号、几个入口和退出登录。

/// 订阅：当前方案、查看方案、管理订阅、恢复购买。
struct SubscriptionSettingsView: View {
    @EnvironmentObject var store: StoreManager
    @State private var showPaywall = false
    @State private var showManageSubscriptions = false

    var body: some View {
        List {
            Section {
                HStack {
                    Text(L("当前方案")).foregroundColor(Theme.textSecondary)
                    Spacer()
                    SubscriptionTierBadge()
                }
                if !store.isSubscribed {
                    Button { showPaywall = true } label: {
                        Label(L("查看订阅方案"), systemImage: "crown.fill").foregroundColor(Theme.segment)
                    }
                }
                if store.isSubscribed {
                    Button(L("管理订阅")) { showManageSubscriptions = true }
                }
                Button(L("恢复购买")) { Task { await store.restore() } }
                    .foregroundColor(Theme.accent)
            }
        }
        .navigationTitle(L("订阅"))
        .navigationBarTitleDisplayMode(.inline)
        .sheet(isPresented: $showPaywall) { PaywallView() }
        .manageSubscriptionsSheet(isPresented: $showManageSubscriptions)
    }
}

/// 一级页订阅入口右侧的当前方案标记，二级页里同样用它。
struct SubscriptionTierBadge: View {
    @EnvironmentObject var store: StoreManager

    var body: some View {
        switch store.tier {
        case .premium:
            Label(L("会员"), systemImage: "crown.fill")
                .font(.subheadline.bold()).foregroundColor(Theme.segment)
        case .free:
            Text(L("免费版")).foregroundColor(Theme.textSecondary)
        }
    }
}

/// 偏好设置：买卖点口径、专业数值开关。
struct PreferencesView: View {
    /// 是否显示专业数值（面积比 / 价差比 / 时长比等）。默认关：先让人看懂结论，需要时再打开。
    @AppStorage(ProDetails.key) private var showProDetails = false
    /// 当前口径：直接读 UserDefaults（SignalMode 的存储键），从二级页返回时随之刷新行右侧的名字。
    @AppStorage(SignalMode.storageKey) private var savedMode = SignalMode.defaultKey
    private var signalMode: String { SignalMode.all.contains(savedMode) ? savedMode : SignalMode.defaultKey }

    var body: some View {
        List {
            Section {
                NavigationLink { SignalModeSettingsView() } label: {
                    HStack {
                        Label(L("买卖点口径"), systemImage: "slider.horizontal.3")
                        Spacer()
                        Text(SignalMode.title(signalMode)).foregroundColor(Theme.textSecondary)
                    }
                }
            } footer: {
                Text(L("决定「什么算买卖点」：严格最少，中等约多一倍（默认），宽松最多。点进去看每种的区别。"))
                    .font(.caption2)
            }

            Section {
                Toggle(isOn: $showProDetails) {
                    Label(L("显示专业数值"), systemImage: "function")
                }
            } footer: {
                Text(L("打开后，买卖点详情里会多出面积比、价差比、时长比等专业数值；点「怎么识别的」随时能看到它们是什么。"))
                    .font(.caption2)
            }
        }
        .navigationTitle(L("偏好设置"))
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// 关于：版本、隐私政策、服务条款、免责声明。（语言与帮助在「我的」一级页）
struct AboutView: View {

    var body: some View {
        List {
            Section(L("关于")) {
                HStack {
                    Text(L("版本")).foregroundColor(Theme.textSecondary)
                    Spacer()
                    Text(appVersion).foregroundColor(Theme.textPrimary)
                }
                Link(destination: URL(string: "https://deepalpha.club/privacy")!) { Text(L("隐私政策")) }
                Link(destination: URL(string: "https://deepalpha.club/terms")!) { Text(L("服务条款")) }
            }

            Section {
                Text(L("本 App 提供的缠论结构识别、买卖点标注与形态分析均由算法自动生成，仅供技术研究与学习参考，不构成任何投资建议或买卖要约。证券投资有风险，任何决策请自主判断并自负盈亏。"))
                    .font(.caption).foregroundColor(Theme.textSecondary)
            } header: {
                Text(L("免责声明"))
            }
        }
        .navigationTitle(L("关于"))
        .navigationBarTitleDisplayMode(.inline)
    }

    private var appVersion: String {
        let v = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        let b = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "1"
        return "\(v) (\(b))"
    }
}

/// 账号与安全：删除账号（不可恢复，所以放在二级页里、带确认）。
struct AccountSecurityView: View {
    @EnvironmentObject var auth: AuthViewModel
    @State private var showDeleteAlert = false

    var body: some View {
        List {
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
        .navigationTitle(L("账号与安全"))
        .navigationBarTitleDisplayMode(.inline)
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
