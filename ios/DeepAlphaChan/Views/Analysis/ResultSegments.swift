import SwiftUI

/// 图表下方的分段内容：整体分析 / 买卖点 / 风险提示。
///
/// 三段读法不同故分段：整体分析是整体读法、买卖点是逐条明细、风险提示单独摘出来——
/// 原先风险提示折叠在整体分析卡片里，容易被当成结论的一部分顺手划过，现在单独
/// 成一个 tab，和另外两段并列，想看风险时才点进来，也更显眼。
struct ResultSegments: View {
    let analysis: ChanAnalysis

    /// 渲染进分享长图时传 true：静态图里没有切换交互，长图要的是完整内容而不是
    /// 用户当下选中的那一段，所以不走切换器，三段上下全铺，各带小标题。
    var isStatic = false

    @State private var segment: Segment = .analysis

    enum Segment: String, CaseIterable, Identifiable {
        case analysis, signals, risk
        var id: String { rawValue }
        var title: String {
            switch self {
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
                    AnalysisSection(analysis: analysis)
                case .signals:
                    SignalListSection(analysis: analysis)
                case .risk:
                    RiskSection(analysis: analysis)
                }
            }
            .id(segment)
        }
    }

    /// 长图布局：三段全铺，标题复用交互态的文案（买卖点/风险提示带数量）。
    private var staticSections: some View {
        VStack(alignment: .leading, spacing: 12) {
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
        case .analysis:
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

/// 深色圆角胶囊分段条：选中项浮一块次级底色，替代系统默认的
/// `UISegmentedControl` 桥接样式（浅灰选中背景，和全 App 的深色投研风格不搭）。
private struct SegmentTabBar: View {
    @Binding var selection: ResultSegments.Segment
    let title: (ResultSegments.Segment) -> String

    var body: some View {
        HStack(spacing: 4) {
            ForEach(ResultSegments.Segment.allCases) { seg in
                let isSelected = seg == selection
                Button {
                    withAnimation(.easeInOut(duration: 0.15)) { selection = seg }
                } label: {
                    Text(title(seg))
                        .font(.system(size: 14, weight: isSelected ? .semibold : .regular))
                        .foregroundColor(isSelected ? Theme.textPrimary : Theme.textSecondary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .background(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .fill(isSelected ? Theme.surfaceAlt : Color.clear)
                        )
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(isSelected ? [.isSelected] : [])
            }
        }
        .padding(4)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}
