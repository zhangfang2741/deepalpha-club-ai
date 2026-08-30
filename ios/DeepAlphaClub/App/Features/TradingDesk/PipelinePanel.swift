import SwiftUI
import DeepAlphaCore

/// 左栏：流程条（成员阵容 + 状态 + 每阶段信号）。
struct PipelinePanel: View {
    let stages: [StageDescriptor]
    let stageStatus: [String: StageStatus]
    let stageSignal: [String: StageSignal]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                panelHeader("交易台成员")
                if stages.isEmpty {
                    Text("开始分析后显示阵容")
                        .font(.caption)
                        .foregroundStyle(Theme.textTertiary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 24)
                } else {
                    ForEach(stages) { stage in
                        stageRow(stage)
                    }
                }
            }
            .padding(14)
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .background(Theme.surface,
                    in: RoundedRectangle(cornerRadius: 14))
    }

    @ViewBuilder
    private func stageRow(_ stage: StageDescriptor) -> some View {
        let status = stageStatus[stage.id] ?? .pending
        HStack(alignment: .top, spacing: 10) {
            Group {
                switch status {
                case .done:
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(Theme.success)
                case .active:
                    ProgressView().controlSize(.small)
                case .pending:
                    Circle().strokeBorder(Theme.textTertiary, lineWidth: 1.5)
                }
            }
            .font(.footnote)
            .frame(width: 16, height: 16)
            .padding(.top, 2)

            VStack(alignment: .leading, spacing: 3) {
                Text(stage.name)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(status == .pending ? Theme.textTertiary : Theme.textPrimary)
                    .lineLimit(1)
                if !stage.role.isEmpty {
                    Text(stage.role)
                        .font(.caption2.monospaced())
                        .foregroundStyle(Theme.textTertiary)
                        .lineLimit(1)
                }
                if let signal = stageSignal[stage.id] {
                    SignalChip(dir: signal.dir, conf: signal.conf)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 3)
        .padding(.horizontal, 6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            status == .active ? Theme.accent.opacity(0.07) : Color.clear,
            in: RoundedRectangle(cornerRadius: 8))
    }
}
