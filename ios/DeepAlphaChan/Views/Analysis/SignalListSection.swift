import SwiftUI

/// 类型、强弱、确认状态分别解释，避免把「三类」误读为「强信号」。
struct SignalListSection: View {
    let analysis: ChanAnalysis
    var isStatic = false

    private var sortedSignals: [Signal] {
        analysis.signals.sorted { $0.time > $1.time }
    }

    var body: some View {
        VStack(spacing: 12) {
            if sortedSignals.isEmpty {
                SectionCard(title: L("当前区间未识别到明确买卖点"), systemImage: "magnifyingglass") {
                    Text(L("没有信号不代表没有风险。可返回「当前状态」查看中枢位置和待观察条件。"))
                        .font(AnalysisType.body)
                        .foregroundStyle(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            } else {
                HStack {
                    Text(L("信号明细 · 最新在前"))
                    Spacer()
                    Text(L("%lld 条未确认", sortedSignals.filter { !$0.confirmed }.count))
                }
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 8)
                ForEach(sortedSignals) { signal in
                    SignalDetailCard(signal: signal, isStatic: isStatic)
                }
            }
            Text(L("「买卖点」是缠论对价格结构的技术信号命名，非买入/卖出操作建议。"))
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 8)
        }
    }
}
