import SwiftUI

/// 图表下方的分段内容：整体分析 / 买卖点 / 风险提示。
///
/// 三段读法不同故分段：整体分析是整体读法、买卖点是逐条明细、风险提示单独摘出来——
/// 原先风险提示折叠在整体分析卡片里，容易被当成结论的一部分顺手划过，现在单独
/// 成一个 tab，和另外两段并列，想看风险时才点进来，也更显眼。
struct ResultSegments: View {
    let analysis: ChanAnalysis

    /// 渲染进分享长图时传 true：静态图里没有切换交互，且分段控件背后的
    /// UISegmentedControl 是 UIKit 桥接，ImageRenderer 拍不平它（运行时日志报
    /// "Unable to render flattened version"），图上只会留一块空白。
    /// 所以长图不走切换器，三段上下全铺，各带小标题 —— 长图要的就是完整内容。
    var isStatic = false

    @State private var segment: Segment = .structure

    enum Segment: String, CaseIterable, Identifiable {
        case structure, analysis, signals, risk
        var id: String { rawValue }
        var title: String {
            switch self {
            case .structure: return L("结构")
            case .analysis: return L("整体分析")
            case .signals: return L("买卖点")
            case .risk: return L("风险提示")
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
            case .structure:
                ChanStructureView(analysis: analysis)
            case .analysis:
                AnalysisSection(analysis: analysis)
            case .signals:
                SignalListSection(analysis: analysis)
            case .risk:
                RiskSection(analysis: analysis)
            }
        }
    }

    /// 长图布局：三段全铺，标题复用交互态的文案（买卖点/风险提示带数量）。
    private var staticSections: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader(L("结构"))
            ChanStructureView(analysis: analysis)

            sectionHeader(L("整体分析"))
            AnalysisSection(analysis: analysis)

            sectionHeader(title(for: .signals))
            SignalListSection(analysis: analysis)

            sectionHeader(title(for: .risk))
            RiskSection(analysis: analysis)
        }
    }

    private func sectionHeader(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 13, weight: .semibold))
            .foregroundColor(Theme.textSecondary)
    }

    /// 买卖点/风险提示段带上数量，不用切过去就知道有没有东西。
    private func title(for s: Segment) -> String {
        switch s {
        case .structure, .analysis:
            return s.title
        case .signals:
            guard !analysis.signals.isEmpty else { return s.title }
            return "\(s.title) \(analysis.signals.count)"
        case .risk:
            let count = analysis.recommendation?.caveats.count ?? 0
            guard count > 0 else { return s.title }
            return "\(s.title) \(count)"
        }
    }
}
