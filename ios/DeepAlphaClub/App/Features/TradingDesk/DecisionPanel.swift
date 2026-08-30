import SwiftUI
import DeepAlphaCore

/// 右栏：共识 + 各分析师信号列表 + 裁决卡。
struct DecisionPanel: View {
    let signals: [SignalRow]
    let consensus: ConsensusData?
    let verdict: VerdictData?
    let turns: [Turn]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                panelHeader("决策")
                ConsensusMeter(consensus: consensus)
                if !signals.isEmpty {
                    VStack(spacing: 8) {
                        ForEach(signals) { s in
                            HStack(spacing: 8) {
                                Text(s.name)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                                Spacer(minLength: 4)
                                SignalChip(dir: s.dir, conf: s.conf, extracted: s.extracted)
                            }
                        }
                    }
                }
                VerdictCard(verdict: verdict, turns: turns)
            }
            .padding(14)
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .background(Color(.secondarySystemBackground),
                    in: RoundedRectangle(cornerRadius: 14))
    }
}
