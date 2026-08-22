import SwiftUI

/// 分析 Tab：查询 → 图表 → 结论。
///
/// 由原来的 ChanDashboardView 重构而来。原版把查询表单、图层开关、图例、
/// 三种状态视图和门禁逻辑全塞在一个 253 行的文件里，页面本身也是一条从查询
/// 一直堆到 GAP 分析的长滚动流。现在编排留在这里，各部分拆成独立视图。
struct AnalysisTabView: View {
    @StateObject private var vm = ChanViewModel()
    @EnvironmentObject private var store: StoreManager
    @EnvironmentObject private var usage: UsageTracker
    @EnvironmentObject private var orientation: AppOrientation

    @State private var showPaywall = false
    @State private var showFullscreenChart = false
    /// 查询条是否展开。未分析时展开，分析成功后自动折叠把空间让给图表。
    @State private var isQueryExpanded = true

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 14) {
                    QueryBar(vm: vm, isExpanded: $isQueryExpanded) {
                        await triggerAnalysis()
                    }

                    if !store.isSubscribed { quotaBanner }

                    if let analysis = vm.analysis {
                        // 已有结果时保留图表：重新分析用轻提示，失败用顶部错误条，
                        // 都不清空已有内容——分析一次要等好几秒，清掉太浪费。
                        if vm.isLoading { refreshingBar }
                        if let error = vm.errorMessage, !vm.isLoading { errorBanner(error) }

                        ChartSection(analysis: analysis, vm: vm,
                                     onFullscreen: openFullscreen)

                        ResultSegments(analysis: analysis, vm: vm,
                                       isSubscribed: store.isSubscribed) {
                            showPaywall = true
                        }

                        compactDisclaimer
                    } else if vm.isLoading {
                        loadingPlaceholder
                    } else if let error = vm.errorMessage {
                        errorView(error)
                    } else {
                        emptyState
                    }
                }
                .padding(14)
            }
            .scrollBounceBehavior(.basedOnSize)
            .background(Theme.background)
            .navigationTitle("缠论分析")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if !store.isSubscribed {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button { showPaywall = true } label: {
                            Label("Pro", systemImage: "crown.fill")
                                .font(.caption.bold())
                        }
                        .tint(Theme.segment)
                    }
                }
            }
            .sheet(isPresented: $showPaywall) { PaywallView() }
            .fullScreenCover(isPresented: $showFullscreenChart) {
                if let analysis = vm.analysis {
                    ChartFullscreenView(analysis: analysis, vm: vm)
                        .environmentObject(orientation)
                }
            }
        }
    }

    /// 打开全屏图表。
    ///
    /// 顺序很关键：先请求转屏，等转完再呈现。反过来的话（在全屏页的 onAppear
    /// 里转屏）用户会先看到一帧竖屏的全屏页，然后整个页面再转过去，很跳。
    private func openFullscreen() {
        orientation.enterLandscape()
        // 系统转屏动画约 0.25s，等它转完再弹，弹出来就已经是横的
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            showFullscreenChart = true
        }
    }

    // MARK: - 门禁

    /// 分析入口：会员无限次；免费用户按「不同标的」走每日额度，用尽弹付费墙。
    private func triggerAnalysis() async {
        guard !vm.isLoading else { return }  // 防重入：加载中忽略再次触发
        let symbol = vm.symbol.trimmingCharacters(in: .whitespaces).uppercased()
        if !store.isSubscribed && !symbol.isEmpty && !usage.canUseFree(symbol: symbol) {
            showPaywall = true
            return
        }
        await vm.runAnalysis()

        if vm.errorMessage == nil && vm.analysis != nil {
            // 分析成功才折叠查询条：失败时用户多半要改参数重试，收起来反而碍事
            withAnimation(.easeInOut(duration: 0.25)) { isQueryExpanded = false }
            if !store.isSubscribed {
                usage.recordUse(symbol: symbol)
            }
        }
    }

    // MARK: - 提示条

    private var quotaBanner: some View {
        Button { showPaywall = true } label: {
            HStack(spacing: 8) {
                Image(systemName: "crown.fill").foregroundColor(Theme.segment).font(.caption)
                Text("今日可分析 \(usage.remaining)/\(usage.dailyQuota) 支股票")
                    .font(.caption).foregroundColor(Theme.textPrimary)
                Spacer()
                Text("升级 Pro 无限次 ›").font(.caption.bold()).foregroundColor(Theme.accent)
            }
            .padding(10)
            .background(Theme.segment.opacity(0.08))
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
        .buttonStyle(.plain)
    }

    private var refreshingBar: some View {
        HStack(spacing: 8) {
            ProgressView().controlSize(.small).tint(Theme.accent)
            Text("正在更新分析…").font(.caption).foregroundColor(Theme.textSecondary)
            Spacer()
        }
        .padding(.horizontal, 4)
    }

    private func errorBanner(_ message: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.circle.fill").foregroundColor(Theme.down).font(.caption)
            Text(message).font(.caption).foregroundColor(Theme.textPrimary)
            Spacer()
            Button { vm.errorMessage = nil } label: {
                Image(systemName: "xmark").font(.caption2).foregroundColor(Theme.textSecondary)
            }
        }
        .padding(10)
        .background(Theme.down.opacity(0.1))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    /// 压缩版免责声明。完整版在「我的」页——App Store 要求这个可见，不能删，
    /// 但也不该在每次看图时都占掉一整块。
    private var compactDisclaimer: some View {
        Text("算法自动生成，仅供技术研究，不构成投资建议。")
            .font(.caption2)
            .foregroundColor(Theme.textSecondary)
            .frame(maxWidth: .infinity)
            .padding(.top, 4)
    }

    // MARK: - 状态视图

    private var loadingPlaceholder: some View {
        VStack(spacing: 12) {
            ProgressView().tint(Theme.accent)
            Text("正在拉取行情并计算缠论结构…")
                .font(.subheadline).foregroundColor(Theme.textSecondary)
        }
        .frame(maxWidth: .infinity, minHeight: 240)
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle").font(.largeTitle).foregroundColor(Theme.down)
            Text(message).font(.subheadline).foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
            Button("重试") { Task { await triggerAnalysis() } }
                .buttonStyle(.borderedProminent).tint(Theme.accent)
        }
        .frame(maxWidth: .infinity, minHeight: 240).padding()
    }

    /// 空状态顺带做新手引导：直接给几个能点的示例代码，比让人对着空输入框强。
    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "chart.bar.xaxis")
                .font(.system(size: 40)).foregroundColor(Theme.textSecondary)
            Text("输入股票代码，开始缠论分析")
                .font(.subheadline).foregroundColor(Theme.textSecondary)

            HStack(spacing: 8) {
                ForEach(["AAPL", "NVDA", "TSLA"], id: \.self) { symbol in
                    Button {
                        vm.symbol = symbol
                        Task { await triggerAnalysis() }
                    } label: {
                        Text(symbol)
                            .font(.caption.weight(.medium))
                            .padding(.horizontal, 14).padding(.vertical, 7)
                            .background(Theme.surfaceAlt)
                            .foregroundColor(Theme.accent)
                            .clipShape(Capsule())
                    }
                }
            }

            Text("看不懂图上的线？先去「学习」页读两分钟。")
                .font(.caption2).foregroundColor(Theme.textSecondary)
                .padding(.top, 4)
        }
        .frame(maxWidth: .infinity, minHeight: 240)
    }
}
