import SwiftUI

/// 从排名等列表里打开另一只股票的分析：自带一份 ChanViewModel，不覆盖当前详情页的状态；
/// 额度规则与分析 Tab 一致（会员不限；免费用户按「不同标的」走每日额度，示例股不扣），用尽直接显示付费墙。
///
/// 在这个全屏页里再点排名里的公司，**原地换成那只股票**（`openStockAnalysis` 环境值），不再往上叠一层全屏页：
/// 以前每点一次就多盖一层（每层都是完整的详情页 + K 线图），点两三层就会因内存 / 呈现层级过深闪退。
struct StockAnalysisCover: View {
    struct Target: Identifiable, Equatable {
        let market: StockMarket
        let symbol: String
        let name: String?
        var id: String { market.rawValue + ":" + symbol }
    }

    @State private var current: Target
    @Environment(\.dismiss) private var dismiss

    init(target: Target) {
        _current = State(initialValue: target)
    }

    var body: some View {
        StockAnalysisCoverContent(target: current, onClose: { dismiss() })
            .id(current.id)   // 换股票时整页重建：旧的 ChanViewModel / 详情页随之释放
            .environment(\.openStockAnalysis, { next in current = next })
    }
}

/// 全屏页里的一只股票：独立的 ChanViewModel + 额度检查 + 详情页。
private struct StockAnalysisCoverContent: View {
    let target: StockAnalysisCover.Target
    let onClose: () -> Void

    @StateObject private var vm = ChanViewModel()
    @EnvironmentObject private var store: StoreManager
    @EnvironmentObject private var usage: UsageTracker
    @EnvironmentObject private var orientation: AppOrientation
    @State private var needsPaywall = false

    var body: some View {
        NavigationStack {
            Group {
                if needsPaywall {
                    PaywallView()
                } else if let analysis = vm.analysis {
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
                    Button(L("关闭")) { onClose() }
                }
            }
        }
        .task { await start() }
    }

    private func start() async {
        guard !vm.isLoading, vm.analysis == nil else { return }
        vm.errorMessage = nil
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

private struct OpenStockAnalysisKey: EnvironmentKey {
    static let defaultValue: ((StockAnalysisCover.Target) -> Void)? = nil
}

extension EnvironmentValues {
    /// 有值 = 当前已经在 `StockAnalysisCover` 里：打开别的股票时原地切换，不再叠一层全屏页。
    var openStockAnalysis: ((StockAnalysisCover.Target) -> Void)? {
        get { self[OpenStockAnalysisKey.self] }
        set { self[OpenStockAnalysisKey.self] = newValue }
    }
}
