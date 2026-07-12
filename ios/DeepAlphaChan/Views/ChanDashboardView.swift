import SwiftUI

/// 缠论主界面。
struct ChanDashboardView: View {
    @StateObject private var vm = ChanViewModel()
    @EnvironmentObject private var store: StoreManager
    @EnvironmentObject private var usage: UsageTracker
    @State private var showSettings = false
    @State private var showPaywall = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 14) {
                    queryBar
                    if !store.isSubscribed { quotaBanner }
                    DisclaimerBanner()

                    if let analysis = vm.analysis {
                        // 已有结果：始终保留图表；重新分析中显示轻提示，失败用顶部错误条（不清空）
                        if vm.isLoading { refreshingBar }
                        if let error = vm.errorMessage, !vm.isLoading { errorBanner(error) }
                        layerToggles
                        ChanChartView(analysis: analysis, vm: vm)
                        chartHint
                        legend
                        SignalPanelView(analysis: analysis)
                        GapAnalysisView(vm: vm, isSubscribed: store.isSubscribed) { showPaywall = true }
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
            .background(Theme.background)
            .navigationTitle("缠论分析")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if !store.isSubscribed {
                    ToolbarItem(placement: .topBarLeading) {
                        Button { showPaywall = true } label: {
                            Label("Pro", systemImage: "crown.fill")
                                .font(.caption.bold())
                        }
                        .tint(Theme.segment)
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showSettings = true } label: {
                        Image(systemName: "person.circle")
                    }
                }
            }
            .sheet(isPresented: $showSettings) { ProfileView() }
            .sheet(isPresented: $showPaywall) { PaywallView() }
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
        // 分析成功且非会员才记一次（同标的当天不重复扣）
        if vm.errorMessage == nil && vm.analysis != nil && !store.isSubscribed {
            usage.recordUse(symbol: symbol)
        }
    }

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

    /// 重新分析中的轻提示（已有图表时用，避免整屏 spinner 覆盖）。
    private var refreshingBar: some View {
        HStack(spacing: 8) {
            ProgressView().controlSize(.small).tint(Theme.accent)
            Text("正在更新分析…").font(.caption).foregroundColor(Theme.textSecondary)
            Spacer()
        }
        .padding(.horizontal, 4)
    }

    /// 分析失败时的顶部错误条（保留下方图表）。
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

    /// 图表手势提示。
    private var chartHint: some View {
        Text("双指缩放 · 单指拖动平移 · 纵向拖动看单根 OHLC")
            .font(.caption2).foregroundColor(Theme.textSecondary)
            .frame(maxWidth: .infinity, alignment: .center)
    }

    // MARK: - 查询栏

    private var queryBar: some View {
        VStack(spacing: 10) {
            HStack(spacing: 10) {
                HStack {
                    Image(systemName: "magnifyingglass").foregroundColor(Theme.textSecondary)
                    TextField("股票代码，如 AAPL", text: $vm.symbol)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                        .foregroundColor(Theme.textPrimary)
                        .onSubmit { Task { await triggerAnalysis() } }
                }
                .padding(10).background(Theme.surfaceAlt)
                .clipShape(RoundedRectangle(cornerRadius: 10))

                Picker("", selection: $vm.freq) {
                    Text("日线").tag("daily")
                    Text("周线").tag("weekly")
                }
                .pickerStyle(.segmented)
                .frame(width: 130)
            }

            HStack(spacing: 10) {
                DatePicker("", selection: $vm.startDate, displayedComponents: .date)
                    .labelsHidden()
                Text("→").foregroundColor(Theme.textSecondary)
                DatePicker("", selection: $vm.endDate, displayedComponents: .date)
                    .labelsHidden()
                Spacer()
                Button {
                    Task { await triggerAnalysis() }
                } label: {
                    HStack(spacing: 6) {
                        if vm.isLoading { ProgressView().controlSize(.small).tint(.white) }
                        Text(vm.isLoading ? "分析中" : "分析").fontWeight(.semibold)
                    }
                    .padding(.horizontal, 20).padding(.vertical, 8)
                    .background(vm.isLoading ? Theme.surfaceAlt : Theme.accent)
                    .foregroundColor(vm.isLoading ? Theme.textSecondary : .white)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .disabled(vm.isLoading)
            }
        }
        .padding(14)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    // MARK: - 图层开关

    private var layerToggles: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                toggleChip("分型", isOn: $vm.showFractals)
                toggleChip("笔", isOn: $vm.showStrokes)
                toggleChip("线段", isOn: $vm.showSegments)
                toggleChip("中枢", isOn: $vm.showPivots)
                toggleChip("买卖点", isOn: $vm.showSignals)
            }
        }
    }

    private func toggleChip(_ title: String, isOn: Binding<Bool>) -> some View {
        Button { isOn.wrappedValue.toggle() } label: {
            Text(title)
                .font(.system(size: 13, weight: .medium))
                .padding(.horizontal, 14).padding(.vertical, 7)
                .background(isOn.wrappedValue ? Theme.accent.opacity(0.2) : Theme.surfaceAlt)
                .foregroundColor(isOn.wrappedValue ? Theme.accent : Theme.textSecondary)
                .clipShape(Capsule())
                .overlay(Capsule().stroke(isOn.wrappedValue ? Theme.accent.opacity(0.5) : .clear, lineWidth: 1))
        }
    }

    private var legend: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 14) {
                legendItem(Theme.stroke, "笔")
                legendItem(Theme.segment, "线段")
                legendItem(Theme.pivotFill, "中枢")
                legendItem(Theme.topFractal, "顶分型")
                legendItem(Theme.bottomFractal, "底分型")
                Text("虚线=未确认").font(.caption2).foregroundColor(Theme.textSecondary)
            }
            .padding(.horizontal, 4)
        }
    }

    private func legendItem(_ color: Color, _ text: String) -> some View {
        HStack(spacing: 4) {
            RoundedRectangle(cornerRadius: 2).fill(color).frame(width: 12, height: 3)
            Text(text).font(.caption2).foregroundColor(Theme.textSecondary)
        }
    }

    // MARK: - 状态视图

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

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "chart.bar.xaxis").font(.largeTitle).foregroundColor(Theme.textSecondary)
            Text("输入股票代码与日期范围，开始缠论分析")
                .font(.subheadline).foregroundColor(Theme.textSecondary)
        }
        .frame(maxWidth: .infinity, minHeight: 200)
    }
}
