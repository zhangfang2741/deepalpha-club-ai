import SwiftUI

/// 从排名等列表里打开另一只股票的分析：自带一份 ChanViewModel，不覆盖当前详情页的状态；
/// 额度规则与分析 Tab 一致（会员不限；免费用户按「不同标的」走每日额度，示例股不扣），用尽直接显示付费墙。
struct StockAnalysisCover: View {
    struct Target: Identifiable {
        let market: StockMarket
        let symbol: String
        let name: String?
        var id: String { market.rawValue + ":" + symbol }
    }

    let target: Target

    @StateObject private var vm = ChanViewModel()
    @EnvironmentObject private var store: StoreManager
    @EnvironmentObject private var usage: UsageTracker
    @EnvironmentObject private var orientation: AppOrientation
    @Environment(\.dismiss) private var dismiss
    @State private var needsPaywall = false

    var body: some View {
        if needsPaywall {
            PaywallView()
        } else {
            NavigationStack {
                Group {
                    if let analysis = vm.analysis {
                        ResultDetailView(analysis: analysis, vm: vm)
                            .environmentObject(orientation)
                    } else if let err = vm.errorMessage {
                        VStack(spacing: 12) {
                            Text(err).font(.callout).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center)
                            Button(L("重试")) { Task { await start() } }
                        }
                        .padding(24)
                    } else {
                        ProgressView(L("正在分析 %@…", target.symbol))
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Theme.background)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button(L("关闭")) { dismiss() }
                    }
                }
            }
            .task { await start() }
        }
    }

    private func start() async {
        guard !vm.isLoading, vm.analysis == nil else { return }
        let symbol = target.symbol.uppercased()
        let chargesQuota = !store.isSubscribed && !AppConfig.isSampleSymbol(market: target.market, symbol: symbol)
        if chargesQuota && !usage.canUseFree(symbol: symbol) {
            needsPaywall = true
            return
        }
        vm.hasSubLevelAccess = store.isPremium
        vm.apply(market: target.market, symbol: symbol, name: target.name, freq: "daily")
        await vm.runAnalysis()
        if vm.errorMessage == nil, vm.analysis != nil, chargesQuota {
            usage.recordUse(symbol: symbol)
        }
    }
}
