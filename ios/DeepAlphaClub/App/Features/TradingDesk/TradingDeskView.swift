import SwiftUI
import DeepAlphaCore

/// 主容器：宽屏（iPad / 横屏）三栏并排；窄屏用分段控件切换单栏。
///
/// 窄屏没有用内嵌 TabView：外层 MainTabView 已占用底部 tab bar，
/// 再嵌一层会出现两条 tab bar 叠在一起。分段控件保留「三页」的信息分区，
/// 同时把纵向空间全留给内容。
struct TradingDeskView: View {
    @Environment(TradingDeskViewModel.self) private var vm
    @Environment(AppState.self) private var appState
    @Environment(\.horizontalSizeClass) private var hSize

    @State private var ticker = "NVDA"
    @State private var market: Market = .US
    @State private var pane: Pane = .stream
    /// 用户看过决策页时的信号条数与裁决状态，用来判断「有没有新东西」
    @State private var seenSignalCount = 0
    @State private var seenVerdict = false

    enum Pane: String, CaseIterable, Identifiable, Hashable {
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

    /// 决策页有未读内容：裁决刚出，或又多了几条分析师信号。
    /// 窄屏一次只显示一个面板，不标出来的话裁决出来了也没人知道。
    private var badgedPanes: Set<Pane> {
        var badges: Set<Pane> = []
        let hasNewVerdict = vm.state.verdict != nil && !seenVerdict
        let hasNewSignals = vm.state.signals.count > seenSignalCount
        if hasNewVerdict || hasNewSignals { badges.insert(.decision) }
        return badges
    }

    private func markDecisionSeen() {
        seenSignalCount = vm.state.signals.count
        seenVerdict = vm.state.verdict != nil
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
                connection: vm.connection,
                busy: vm.busy,
                onStart: { Task { await vm.startRun(ticker: ticker, market: market) } },
                onControl: { action, text in
                    Task { await vm.control(action, text: text) }
                })

            // 登录态没能写进 Keychain：不是错误（本次会话能用），但下次要重登
            if let warn = appState.persistenceWarning {
                ErrorBanner(message: warn, tint: Theme.warning, icon: "exclamationmark.circle.fill") {
                    appState.persistenceWarning = nil
                }
            }

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

            if !vm.live {
                Text("研究 / 分析用途，非投资建议，不执行真实交易。agent 观点带置信度，不代表事实。")
                    .font(.caption2.monospaced())
                    .foregroundStyle(Theme.textTertiary)
                    .multilineTextAlignment(.center)
            }
        }
        .padding(14)
        .themedBackground()
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
            PaneSelector(panes: Pane.allCases, selection: $pane,
                         badged: badgedPanes) { $0.label }

            switch pane {
            case .pipeline: pipelinePanel
            case .stream: streamPanel
            case .decision: decisionPanel
            }
        }
        .onChange(of: pane) { _, newPane in
            if newPane == .decision { markDecisionSeen() }
        }
        .onChange(of: vm.state.signals.count) { _, _ in
            if pane == .decision { markDecisionSeen() }
        }
        .onChange(of: vm.state.verdict != nil) { _, _ in
            if pane == .decision { markDecisionSeen() }
        }
        .onChange(of: vm.state.runId) { _, _ in
            // 新一轮分析重新计数，否则上一轮的已读会把新裁决的角标吃掉
            seenSignalCount = 0
            seenVerdict = false
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
