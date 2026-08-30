import SwiftUI
import DeepAlphaCore

/// 主容器：宽屏（iPad / 横屏）三栏并排；窄屏用分段控件切换单栏。
///
/// 窄屏没有用内嵌 TabView：外层 MainTabView 已占用底部 tab bar，
/// 再嵌一层会出现两条 tab bar 叠在一起。分段控件保留「三页」的信息分区，
/// 同时把纵向空间全留给内容。
struct TradingDeskView: View {
    @Environment(TradingDeskViewModel.self) private var vm
    @Environment(\.horizontalSizeClass) private var hSize

    @State private var ticker = "NVDA"
    @State private var market: Market = .US
    @State private var pane: Pane = .stream

    enum Pane: String, CaseIterable, Identifiable {
        case pipeline, stream, decision
        var id: String { rawValue }
        var label: String {
            switch self {
            case .pipeline: "流程"
            case .stream: "推理"
            case .decision: "决策"
            }
        }
    }

    /// 正在流式输出的那张卡（未 done 的第一张，仅 running 时显示光标）。
    private var streamingTurnId: String? {
        vm.state.status == .running
            ? vm.state.turns.first(where: { !$0.done })?.turnId
            : nil
    }

    var body: some View {
        VStack(spacing: 12) {
            Topbar(
                ticker: $ticker,
                market: $market,
                state: vm.state,
                busy: vm.busy,
                onStart: { Task { await vm.startRun(ticker: ticker, market: market) } },
                onControl: { action, text in
                    Task { await vm.control(action, text: text) }
                })

            if let err = vm.pageError ?? vm.state.error {
                ErrorBanner(message: err) {
                    vm.clearPageError()
                    vm.state.error = nil
                }
            }

            if hSize == .regular {
                wideLayout
            } else {
                narrowLayout
            }

            Text("研究 / 分析用途，非投资建议，不执行真实交易。agent 观点带置信度，不代表事实。")
                .font(.caption2.monospaced())
                .foregroundStyle(.tertiary)
                .multilineTextAlignment(.center)
        }
        .padding(14)
    }

    private var wideLayout: some View {
        HStack(alignment: .top, spacing: 12) {
            pipelinePanel.frame(width: 240)
            streamPanel
            decisionPanel.frame(width: 300)
        }
    }

    private var narrowLayout: some View {
        VStack(spacing: 10) {
            Picker("面板", selection: $pane) {
                ForEach(Pane.allCases) { p in
                    Text(p.label).tag(p)
                }
            }
            .pickerStyle(.segmented)

            switch pane {
            case .pipeline: pipelinePanel
            case .stream: streamPanel
            case .decision: decisionPanel
            }
        }
    }

    private var pipelinePanel: some View {
        PipelinePanel(
            stages: vm.state.stages,
            stageStatus: vm.state.stageStatus,
            stageSignal: vm.state.stageSignal)
    }

    private var streamPanel: some View {
        StreamPanel(
            turns: vm.state.turns,
            status: vm.state.status,
            streamingTurnId: streamingTurnId,
            runId: vm.state.runId)
    }

    private var decisionPanel: some View {
        DecisionPanel(
            signals: vm.state.signals,
            consensus: vm.state.consensus,
            verdict: vm.state.verdict,
            turns: vm.state.turns)
    }
}
