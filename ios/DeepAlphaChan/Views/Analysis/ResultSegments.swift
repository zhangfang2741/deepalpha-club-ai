import SwiftUI

/// 图表下方的分段内容：结论 / 买卖点 / GAP。
///
/// 改造前这三块首尾相连堆在一条滚动流里，读任何一项都要长距离滚动，而它们
/// 的用途其实互不相干——结论是快速判断，买卖点是逐条明细，GAP 是要动手输入
/// 产业观点的深度分析。
struct ResultSegments: View {
    let analysis: ChanAnalysis
    @ObservedObject var vm: ChanViewModel
    let isSubscribed: Bool
    let onUpgrade: () -> Void

    @State private var segment: Segment = .conclusion

    enum Segment: String, CaseIterable, Identifiable {
        case conclusion, signals, gap
        var id: String { rawValue }
        var title: String {
            switch self {
            case .conclusion: return "结论"
            case .signals: return "买卖点"
            case .gap: return "GAP"
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
            case .conclusion:
                ConclusionSection(analysis: analysis)
            case .signals:
                SignalListSection(analysis: analysis)
            case .gap:
                GapAnalysisView(vm: vm, isSubscribed: isSubscribed, onUpgrade: onUpgrade)
            }
        }
    }

    /// 买卖点段带上数量，不用切过去就知道有没有东西。
    private func title(for s: Segment) -> String {
        guard s == .signals, !analysis.signals.isEmpty else { return s.title }
        return "\(s.title) \(analysis.signals.count)"
    }
}
