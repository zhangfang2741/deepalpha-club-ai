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
            SectionCard(title: L("先读懂信号，再看明细"), systemImage: "flag") {
                WrapLayout(spacing: 12, lineSpacing: 8) {
                    Label(L("买点"), systemImage: "arrow.up.circle.fill").foregroundStyle(Theme.up)
                    Label(L("卖点"), systemImage: "arrow.down.circle.fill").foregroundStyle(Theme.down)
                }
                .font(.subheadline.bold())
                Text(L("与 K 线、雷达一致：红色为买点，绿色为卖点；虚线表示未确认。"))
                    .font(AnalysisType.body)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                Text(L("一／二／三类描述结构类型；强／中／弱描述信号强度，对应雷达颜色深浅。类型、强度与是否确认是三个不同维度。"))
                    .font(AnalysisType.body)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                AnalysisTermLink(term: "买卖点", color: Theme.textSecondary)
            }

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
