import SwiftUI

/// 登录后的主容器。
///
/// 四个 Tab 对应四种意图：**看信号**、**做分析**、**学概念**、**管账号**。
/// 「晨报」暂时隐藏（保留代码与推送路由，随时可以重新挂回 TabView）；
/// 「信号」放在首位，作为每日回访的第一入口，页面顶部标题为「缠论信号」。
/// 分析 Tab 仍是最重的功能，其 ChanViewModel 提升到这里持有，
/// 「信号」页个股跳转分析时共用同一份状态。
struct MainTabView: View {
    enum Tab: Hashable {
        case morningReport, analysis, signalRadar, learn, profile
    }

    @State private var selection: Tab = {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("-marketingPlayback") {
            return .analysis
        }
        #endif
        return .signalRadar
    }()
    /// 推送路由（Task 13 的 PushNotificationManager 发 `.openMorningReport`）
    /// 写入目标市场。晨报 Tab 隐藏期间暂无人消费，先留着字段不删——
    /// 重新挂回晨报 Tab 时不用碰这段路由逻辑。
    @State private var pendingReportMarket: String?
    /// 分析 Tab 与晨报跳转共享的缠论状态。
    @ObservedObject private var push = PushNotificationManager.shared
    @StateObject private var chanVM = ChanViewModel()

    var body: some View {
        TabView(selection: $selection) {
            // 晨报暂时隐藏，保留视图与状态，未来要恢复直接取消注释即可：
            // MorningReportTabView(onOpenSymbol: openSymbol, pendingMarket: $pendingReportMarket)
            //     .tabItem { Label(L("晨报"), systemImage: "newspaper") }
            //     .tag(Tab.morningReport)

            SignalRadarView(chanVM: chanVM)
                .tabItem { Label(L("信号"), systemImage: "dot.radiowaves.left.and.right") }
                .tag(Tab.signalRadar)

            AnalysisTabView(vm: chanVM)
                .tabItem { Label(L("分析"), systemImage: "chart.xyaxis.line") }
                .tag(Tab.analysis)

            LearnTabView()
                .tabItem { Label(L("学习"), systemImage: "book") }
                .tag(Tab.learn)

            ProfileView()
                .tabItem { Label(L("我的"), systemImage: "person.circle") }
                .tag(Tab.profile)
        }
        .onReceive(push.$pendingMarket) { market in
            guard let market else { return }
            pendingReportMarket = market
            // 晨报隐藏期间，推送路由先落到「信号」页，避免 selection 指向一个
            // 不在 TabView 里的 tag（那样切换会没有任何反应）。
            selection = .signalRadar
            push.pendingMarket = nil
        }
    }

    /// 晨报「重点个股」的跳转：填好共享 ViewModel 的查询条件，切到分析 Tab 并起跑。
    /// 分析完成后进结果页的逻辑在 AnalysisTabView 里（监听 isLoading 收沿）。
    private func openSymbol(market: String, symbol: String) {
        guard let target = StockMarket(rawValue: market) else { return }
        chanVM.apply(market: target, symbol: symbol)
        selection = .analysis
        Task { await chanVM.runAnalysis() }
    }
}

extension Notification.Name {
    /// 晨报推送点击路由：object 携带目标市场（"us" / "cn" / "hk"）。
    static let openMorningReport = Notification.Name("openMorningReport")
}
