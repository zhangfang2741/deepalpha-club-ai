import SwiftUI

/// 分析 Tab —— 条件页（第一页）。
///
/// 只负责录入查询条件与风险提示；分析成功后 push 到 ResultDetailView 看结果。
/// 条件与结果分成两页：录入时不被长长的结果流干扰，看结果时也不被表单占屏。
struct AnalysisTabView: View {
    @StateObject private var vm = ChanViewModel()
    @EnvironmentObject private var store: StoreManager
    @EnvironmentObject private var usage: UsageTracker
    @EnvironmentObject private var orientation: AppOrientation

    @State private var showPaywall = false
    /// 分析成功后置 true，push 到详情页；用户返回时自动复位。
    @State private var showResults = false

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
                            Label("Pro", systemImage: "crown.fill").font(.caption.bold())
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
        }
    }

    // MARK: - 门禁 + 跳转

    /// 分析入口：会员无限次；免费用户按「不同标的」走每日额度，用尽弹付费墙。
    /// 成功后跳转到详情页。
    private func triggerAnalysis() async {
        guard !vm.isLoading else { return }  // 防重入
        let symbol = vm.symbol.trimmingCharacters(in: .whitespaces).uppercased()
        if !store.isSubscribed && !symbol.isEmpty && !usage.canUseFree(symbol: symbol) {
            showPaywall = true
            return
        }
        await vm.runAnalysis()

        if vm.errorMessage == nil && vm.analysis != nil {
            if !store.isSubscribed { usage.recordUse(symbol: symbol) }
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
                Text("不要只看技术信号")
                    .font(.subheadline.bold()).foregroundColor(Theme.textPrimary)
            }
            Text("缠论主要观察价格走势与市场结构。投资决策还应结合基本面、成长性、估值、盈利预期和市场环境综合判断。")
                .font(.footnote).foregroundColor(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            Text("技术上的「买点」，不等于投资上的「值得买」。")
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

    private var loadingPlaceholder: some View {
        VStack(spacing: 12) {
            ProgressView().tint(Theme.accent)
            Text("正在拉取行情并计算缠论结构…")
                .font(.subheadline).foregroundColor(Theme.textSecondary)
        }
        .frame(maxWidth: .infinity, minHeight: 200)
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle").font(.largeTitle).foregroundColor(Theme.down)
            Text(message).font(.subheadline).foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
            Button("重试") { Task { await triggerAnalysis() } }
                .buttonStyle(.borderedProminent).tint(Theme.accent)
        }
        .frame(maxWidth: .infinity, minHeight: 200).padding()
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
                        vm.market = .us
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
        .frame(maxWidth: .infinity, minHeight: 200)
    }
}
