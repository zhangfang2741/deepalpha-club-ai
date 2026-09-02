import SwiftUI

/// 图表下方的分段内容：形态分析 / 买卖点。
///
/// 形态分析是整体读法、买卖点是逐条明细，两者读法不同故分段。
/// （原先还有 GAP 段，需手动输入产业观点做深度分析，已从此处移除。）
struct ResultSegments: View {
    let analysis: ChanAnalysis

    /// 渲染进分享长图时传 true：静态图里没有切换交互，且分段控件背后的
    /// UISegmentedControl 是 UIKit 桥接，ImageRenderer 拍不平它（运行时日志报
    /// "Unable to render flattened version"），图上只会留一块空白。
    /// 所以长图不走切换器，两段上下全铺，各带小标题 —— 长图要的就是完整内容。
    var isStatic = false

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
            if isStatic {
                staticSections
            } else {
                interactiveSections
            }
        }
    }

    private var interactiveSections: some View {
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

    /// 长图布局：两段全铺，标题复用交互态的文案（买卖点带数量）。
    private var staticSections: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader(L("形态分析"))
            AnalysisSection(analysis: analysis)

            sectionHeader(title(for: .signals))
            SignalListSection(analysis: analysis)
        }
    }

    private func sectionHeader(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 13, weight: .semibold))
            .foregroundColor(Theme.textSecondary)
    }

    /// 买卖点段带上数量，不用切过去就知道有没有东西。
    private func title(for s: Segment) -> String {
        guard s == .signals, !analysis.signals.isEmpty else { return s.title }
        return "\(s.title) \(analysis.signals.count)"
    }
}
