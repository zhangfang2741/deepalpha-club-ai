import SwiftUI
import DeepAlphaCore

/// 回放：全文直出（无流式动画），顶部裁决 + 信号，下面 Turn 卡片序列。
struct RunReplayView: View {
    let runId: String
    @Environment(\.compositionRoot) private var root
    @State private var vm: RunReplayViewModel?

    var body: some View {
        ScrollView {
            if let vm {
                content(vm)
            } else {
                ProgressView("载入中").padding(40)
            }
        }
        .navigationTitle("回放")
        .navigationBarTitleDisplayMode(.inline)
        .task(id: runId) {
            guard let root else { return }
            // VM 每个页面一个，runId 变化时复用同一个实例重新 load
            if vm == nil { vm = root.replayFactory() }
            await vm?.load(runId: runId)
        }
    }

    @ViewBuilder
    private func content(_ vm: RunReplayViewModel) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            if let d = vm.detail {
                header(d)
                DecisionPanel(signals: vm.signals, consensus: nil,
                              verdict: vm.verdict, turns: vm.turns)
            }
            if vm.loading {
                ProgressView().frame(maxWidth: .infinity).padding()
            }
            if let err = vm.error {
                ErrorBanner(message: err) { vm.error = nil }
            }
            ForEach(vm.turns) { turn in
                TurnCard(turn: turn)
            }
        }
        .padding(14)
    }

    private func header(_ d: RunDetailResponse) -> some View {
        HStack(spacing: 8) {
            Text(d.ticker).font(.headline.monospaced())
            Text(d.tradeDate).font(.caption.monospaced()).foregroundStyle(.tertiary)
            StatusBadge(status: d.status)
            Spacer(minLength: 4)
            Text(RunRow.duration(d.durationMs))
                .font(.caption.monospaced())
                .foregroundStyle(.secondary)
        }
    }
}
