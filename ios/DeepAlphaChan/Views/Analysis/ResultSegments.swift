import SwiftUI

/// 图表下方按状态、信号、风险组织阅读，整页共用外层滚动容器。
struct ResultSegments: View {
    let analysis: ChanAnalysis

    /// 渲染进分享长图时传 true：静态图里没有切换交互，长图要的是完整内容而不是
    /// 用户当下选中的那一段，所以不走切换器，三段上下全铺，各带小标题。
    var isStatic = false

    /// 透传给 `AnalysisSection` → `PivotPhaseBlock`，见 `ResultDetailView` 里
    /// `pageContentWidth` 的说明。
    var contentWidth: CGFloat?

    @State private var segment: Segment = .analysis

    enum Segment: String, CaseIterable, Identifiable {
        case analysis, signals, risk
        var id: String { rawValue }
        var title: String {
            switch self {
            case .analysis: return L("当前状态")
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

    /// 回退记录：曾经尝试把图表+图层开关固定在顶部、tab 内容单独套一个
    /// `.frame(maxHeight: .infinity)` 的 ScrollView 独立滚动——真机实测发现
    /// 图表+MACD+图例已经占掉大半屏，留给 tab 内容的"剩余空间"被挤成一个
    /// 只有几行高的小框，体验比之前更差，已经撤回。tab 内容和图表一起回到
    /// 外层共享的那个 ScrollView 里（见 ResultDetailView.body），这里只负责
    /// 切换器 + 当前选中的内容，不再自带 ScrollView。`.id(segment)` 保留：
    /// 让 SwiftUI 把每次切换都当成一棵新的内容树，不会把上一个 tab 的布局
    /// 状态带过来。
    private var interactiveSections: some View {
        VStack(spacing: 12) {
            SegmentTabBar(selection: $segment, title: title(for:))

            Group {
                switch segment {
                case .analysis:
                    AnalysisSection(analysis: analysis, contentWidth: contentWidth)
                case .signals:
                    SignalListSection(analysis: analysis, isStatic: isStatic)
                case .risk:
                    RiskSection(analysis: analysis)
                }
            }
            .id(segment)

            Button {
                switch segment {
                case .analysis: segment = .signals
                case .signals: segment = .risk
                case .risk: segment = .analysis
                }
            } label: {
                Label(nextTitle, systemImage: "arrow.right")
                    .font(.subheadline.weight(.semibold))
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .foregroundStyle(Theme.accent)
                    .background(Theme.surface, in: RoundedRectangle(cornerRadius: 10))
            }
            .buttonStyle(.plain)
        }
    }

    private var nextTitle: String {
        switch segment {
        case .analysis: return L("继续核对买卖点")
        case .signals: return L("查看风险与限制")
        case .risk: return L("返回当前状态")
        }
    }

    /// 长图布局：三段全铺，标题复用交互态的文案（买卖点/风险提示带数量）。
    private var staticSections: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader(L("当前状态"))
            AnalysisSection(analysis: analysis, contentWidth: contentWidth)

            sectionHeader(title(for: .signals))
            SignalListSection(analysis: analysis, isStatic: isStatic)

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
        case .analysis:
            return s.title
        case .signals:
            guard !analysis.signals.isEmpty else { return s.title }
            return "\(s.title) \(analysis.signals.count)"
        case .risk:
            let count = AnalysisInterpretation.riskCount(analysis)
            guard count > 0 else { return s.title }
            return "\(s.title) \(count)"
        }
    }
}
