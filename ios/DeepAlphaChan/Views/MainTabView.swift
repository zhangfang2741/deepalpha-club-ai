import SwiftUI

/// 登录后的主容器。
///
/// 四个 Tab 对应四种意图：**读晨报**、**做分析**、**学概念**、**管账号**。
/// 晨报是每日回访的第一入口，放在首位；分析 Tab 仍是最重的功能，
/// 其 ChanViewModel 提升到这里持有，晨报「重点个股」跳转分析时共用同一份状态。
struct MainTabView: View {
    enum Tab: Hashable {
        case morningReport, analysis, learn, profile
    }

    @State private var selection: Tab = .morningReport
    /// 推送路由（Task 13 的 PushNotificationManager 发 `.openMorningReport`）
    /// 写入目标市场，晨报 Tab 消费后置 nil。
    @State private var pendingReportMarket: String?
    /// 分析 Tab 与晨报跳转共享的缠论状态。
    @StateObject private var chanVM = ChanViewModel()

    var body: some View {
        TabView(selection: $selection) {
            MorningReportTabView(onOpenSymbol: openSymbol, pendingMarket: $pendingReportMarket)
                .tabItem { Label(L("晨报"), systemImage: "newspaper") }

            AnalysisTabView(vm: chanVM)
                .tabItem { Label(L("分析"), systemImage: "chart.xyaxis.line") }

            LearnTabView()
                .tabItem { Label(L("学习"), systemImage: "book") }

            ProfileView()
                .tabItem { Label(L("我的"), systemImage: "person.circle") }
        }
        .onReceive(NotificationCenter.default.publisher(for: .openMorningReport)) { note in
            if let market = note.object as? String {
                pendingReportMarket = market
            }
            selection = .morningReport
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
