import SwiftUI

/// 图表下方的分段内容：形态分析 / 买卖点。
///
/// 形态分析是整体读法、买卖点是逐条明细，两者读法不同故分段。
/// （原先还有 GAP 段，需手动输入产业观点做深度分析，已从此处移除。）
struct ResultSegments: View {
    let analysis: ChanAnalysis

    @State private var segment: Segment = .analysis

    enum Segment: String, CaseIterable, Identifiable {
        case analysis, signals
        var id: String { rawValue }
        var title: String {
            switch self {
            case .analysis: return L("形态分析")
            case .signals: return L("买卖点")
            }
        }
    }

    var body: some View {
        VStack(spacing: 12) {
            Picker("", selection: $segment) {
                ForEach(Segment.allCases) { s in
                    Text(title(for: s)).tag(s)
                }
            }
            .pickerStyle(.segmented)

            switch segment {
            case .analysis:
                AnalysisSection(analysis: analysis)
            case .signals:
                SignalListSection(analysis: analysis)
            }
        }
    }

    /// 买卖点段带上数量，不用切过去就知道有没有东西。
    private func title(for s: Segment) -> String {
        guard s == .signals, !analysis.signals.isEmpty else { return s.title }
        return "\(s.title) \(analysis.signals.count)"
    }
}
