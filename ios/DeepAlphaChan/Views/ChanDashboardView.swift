import SwiftUI

/// 缠论主界面。
struct ChanDashboardView: View {
    @StateObject private var vm = ChanViewModel()
    @State private var showSettings = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 14) {
                    queryBar
                    DisclaimerBanner()

                    if vm.isLoading {
                        loadingPlaceholder
                    } else if let error = vm.errorMessage {
                        errorView(error)
                    } else if let analysis = vm.analysis {
                        layerToggles
                        ChanChartView(analysis: analysis, vm: vm)
                        legend
                        SignalPanelView(analysis: analysis)
                        GapAnalysisView(vm: vm)
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
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showSettings = true } label: {
                        Image(systemName: "person.circle")
                    }
                }
            }
            .sheet(isPresented: $showSettings) { ProfileView() }
        }
        .task {
            if vm.analysis == nil { await vm.runAnalysis() }
        }
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
                        .onSubmit { Task { await vm.runAnalysis() } }
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
                    Task { await vm.runAnalysis() }
                } label: {
                    Text("分析").fontWeight(.semibold)
                        .padding(.horizontal, 20).padding(.vertical, 8)
                        .background(Theme.accent).foregroundColor(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                }
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
            Button("重试") { Task { await vm.runAnalysis() } }
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
