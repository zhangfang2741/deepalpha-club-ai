import SwiftUI

/// 分析 Tab —— 条件页（第一页）。
///
/// 只负责录入查询条件与风险提示；分析成功后 push 到 ResultDetailView 看结果。
/// 条件与结果分成两页：录入时不被长长的结果流干扰，看结果时也不被表单占屏。
struct AnalysisTabView: View {
    /// 由 MainTabView 注入的共享状态：晨报「重点个股」跳转分析时用的是同一个
    /// ViewModel，这样切到本 Tab 时查询条件已填好、结果也能直接呈现。
    /// 本视图不再自己创建。必须用 @ObservedObject 订阅——isLoading/errorMessage
    /// 变化要驱动本视图重算（含"外部触发分析后自动进结果页"的 onChange）。
    @ObservedObject var vm: ChanViewModel
    @StateObject private var recent = RecentSymbols()
    @EnvironmentObject private var store: StoreManager
    @EnvironmentObject private var usage: UsageTracker
    @EnvironmentObject private var orientation: AppOrientation

    /// 没有历史时给的起步示例。新装用户对着一个空输入框不知道能填什么。
    private let starterSymbols = ["AAPL", "NVDA", "TSLA"]

    @State private var showPaywall = false
    /// 分析成功后置 true，push 到详情页；用户返回时自动复位。
    @State private var showResults = false

    init(vm: ChanViewModel) {
        self.vm = vm
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 14) {
                    QueryBar(vm: vm) { await triggerAnalysis() }

                    if !store.isSubscribed { quotaBanner }

                    riskNotice

                    if vm.isLoading {
                        loadingPlaceholder
                    } else if let error = vm.errorMessage {
                        errorView(error)
                    } else {
                        emptyState
                    }
                }
                .padding(.horizontal, Theme.contentHInset)
                .padding(.vertical, Theme.contentVInset)
            }
            .scrollBounceBehavior(.basedOnSize)
            .background(Theme.background)
            .navigationTitle(L("缠论分析"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if !store.isSubscribed {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button { showPaywall = true } label: {
                            Label(L("去订阅"), systemImage: "crown.fill").font(.caption.bold())
                        }
                        .tint(Theme.segment)
                    }
                }
            }
            .sheet(isPresented: $showPaywall) { PaywallView() }
            .navigationDestination(isPresented: $showResults) {
                if let analysis = vm.analysis {
                    ResultDetailView(analysis: analysis, vm: vm)
                        .environmentObject(orientation)
                }
            }
            // 原本这里还监听 vm.isLoading 下降沿，为的是晨报「重点个股」跳转
            // 分析 Tab 后自动进结果页（晨报当时借用的是本 Tab 的 NavigationStack）。
            // 晨报已隐藏，「市场」页（原信号雷达）也改成了自己独立的 NavigationStack
            // 直接 push，不再借用这里——继续留着这段监听只会误伤：chanVM 是共享的，
            // 只要别的入口跑了一次分析，本 Tab 哪怕没被看到也会把 showResults 置为
            // true，导致用户之后手动点开「分析」看到的是别人跑过的旧结果而不是
            // 空白条件页。晨报以后要恢复，应该照「市场」页的做法自建 NavigationStack，
            // 而不是复用这里。
            #if DEBUG
            .task {
                await runDemoAnalysisIfRequested()
            }
            #endif
        }
    }

    #if DEBUG
    /// 登录完成后自动打开演示标的，供无人工录制流程使用。
    private func runDemoAnalysisIfRequested() async {
        guard ProcessInfo.processInfo.arguments.contains("-deepalphaDemo"),
              vm.analysis == nil,
              let demoSymbol = ProcessInfo.processInfo.arguments
                  .first(where: { $0.hasPrefix("-deepalphaDemoSymbol=") })
                  .map({ String($0.dropFirst("-deepalphaDemoSymbol=".count)) }),
              !demoSymbol.isEmpty else { return }
        vm.apply(market: .us, symbol: demoSymbol)
        // 等待登录收尾任务完成，避免 Keychain 写入与首个分析请求竞态。
        try? await Task.sleep(nanoseconds: 800_000_000)
        await triggerAnalysis()
        if vm.analysis == nil, vm.errorMessage == "Not authenticated" {
            try? await Task.sleep(nanoseconds: 1_000_000_000)
            await triggerAnalysis()
        }
    }
    #endif

    // MARK: - 门禁 + 跳转

    /// 分析入口：会员无限次；免费用户按「不同标的」走每日额度，用尽弹付费墙。
    /// 成功后跳转到详情页。
    private func triggerAnalysis() async {
        guard !vm.isLoading else { return }  // 防重入
        let symbol = vm.symbol.trimmingCharacters(in: .whitespaces).uppercased()
        // 示例股（英伟达/茅台/腾讯）不扣额度，见 AppConfig.sampleSymbols
        let chargesQuota = !store.isSubscribed && !AppConfig.isSampleSymbol(market: vm.market, symbol: symbol)
        if chargesQuota && !symbol.isEmpty && !usage.canUseFree(symbol: symbol) {
            showPaywall = true
            return
        }
        await vm.runAnalysis()

        if vm.errorMessage == nil && vm.analysis != nil {
            if chargesQuota { usage.recordUse(symbol: symbol) }
            // 会员也要记：这是快捷入口，和计费额度无关
            recent.record(market: vm.market, symbol: symbol)
            showResults = true
        }
    }

    // MARK: - 风险提示

    /// 条件页的核心风险提示：提醒用户缠论只是技术信号，别把「技术买点」当「值得买」。
    private var riskNotice: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundColor(Theme.segment).font(.subheadline)
                Text(L("不要只看技术信号"))
                    .font(.subheadline.bold()).foregroundColor(Theme.textPrimary)
            }
            Text(L("缠论主要观察价格走势与市场结构。投资决策还应结合基本面、成长性、估值、盈利预期和市场环境综合判断。"))
                .font(.footnote).foregroundColor(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            Text(L("技术上的「买点」，不等于投资上的「值得买」。"))
                .font(.footnote.weight(.medium)).foregroundColor(Theme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.segment.opacity(0.08))
        .overlay(
            RoundedRectangle(cornerRadius: 12).stroke(Theme.segment.opacity(0.3), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - 提示条与状态视图

    /// 额度提示条。
    ///
    /// 刻意不写成「0/3」这种分数：分子到底是剩余还是已用，读的人猜不出来，
    /// 用完那一刻显示「0/3」看着更像还没开始用。改成把剩余次数直接说成话。
    ///
    /// 另外额度的计量单位是「**新**标的」——当天已分析过的股票不重复扣次数、
    /// 用完后也仍能再看（见 UsageTracker.canUseFree）。用尽态补一行说明这件事，
    /// 否则一个孤零零的「已用完」会让人以为整个功能都锁死了。
    private var quotaBanner: some View {
        let exhausted = usage.remaining == 0
        let tint = exhausted ? Theme.up : Theme.segment
        return Button { showPaywall = true } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    Image(systemName: exhausted ? "lock.fill" : "crown.fill")
                        .foregroundColor(tint).font(.caption)
                    Text(exhausted
                         ? L("今日 %lld 支新股票的免费额度已用完", usage.dailyQuota)
                         : L("今日还可分析 %lld 支新股票", usage.remaining))
                        .font(.caption).foregroundColor(Theme.textPrimary)
                    Spacer()
                    Text(exhausted ? L("开通订阅继续 ›") : L("订阅解锁无限次 ›"))
                        .font(.caption.bold()).foregroundColor(Theme.accent)
                }
                if exhausted {
                    Text(L("今天已分析过的股票仍可继续查看"))
                        .font(.caption2).foregroundColor(Theme.textSecondary)
                }
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(tint.opacity(exhausted ? 0.14 : 0.08))
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(exhausted ? tint.opacity(0.4) : .clear, lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
        .buttonStyle(.plain)
    }

    private var loadingPlaceholder: some View {
        VStack(spacing: 12) {
            ProgressView().tint(Theme.accent)
            Text(L("正在拉取行情并计算缠论结构…"))
                .font(.subheadline).foregroundColor(Theme.textSecondary)
        }
        .frame(maxWidth: .infinity, minHeight: 200)
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle").font(.largeTitle).foregroundColor(Theme.down)
            Text(message).font(.subheadline).foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
            Button(L("重试")) { Task { await triggerAnalysis() } }
                .buttonStyle(.borderedProminent).tint(Theme.accent)
        }
        .frame(maxWidth: .infinity, minHeight: 200).padding()
    }

    /// 空状态：分析过的标的直接列出来当快捷入口——回访用户想看的多半就是上次那几支。
    /// 还没有历史时退回起步示例，别让新用户对着一个空输入框发愣。
    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "chart.bar.xaxis")
                .font(.system(size: 40)).foregroundColor(Theme.textSecondary)
            Text(recent.entries.isEmpty
                 ? L("输入股票代码，开始缠论分析")
                 : L("最近分析过"))
                .font(.subheadline).foregroundColor(Theme.textSecondary)

            if recent.entries.isEmpty {
                HStack(spacing: 8) {
                    ForEach(starterSymbols, id: \.self) { symbol in
                        // 示例都是美股：当前选着 A 股时点 AAPL 也要切回美股
                        symbolChip(text: symbol) { vm.apply(market: .us, symbol: symbol) }
                    }
                }
            } else {
                // 6 条在窄屏上一行放不下，用自动换行的流式布局
                FlowLayout(spacing: 8) {
                    ForEach(recent.entries) { entry in
                        symbolChip(text: entry.display) {
                            vm.apply(market: entry.market, symbol: entry.symbol)
                        }
                    }
                }
            }

            Text(L("看不懂图上的线？先去「学习」页读两分钟。"))
                .font(.caption2).foregroundColor(Theme.textSecondary)
                .padding(.top, 4)
        }
        .frame(maxWidth: .infinity, minHeight: 200)
    }

    /// 可点的代码 chip：先按 apply 填好查询条件，再跑分析。
    private func symbolChip(text: String, apply: @escaping () -> Void) -> some View {
        Button {
            apply()
            Task { await triggerAnalysis() }
        } label: {
            Text(text)
                .font(.caption.weight(.medium))
                .padding(.horizontal, 14).padding(.vertical, 7)
                .background(Theme.surfaceAlt)
                .foregroundColor(Theme.accent)
                .clipShape(Capsule())
        }
    }
}
