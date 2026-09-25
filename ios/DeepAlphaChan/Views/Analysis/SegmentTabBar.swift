import SwiftUI

/// 等宽入口带阅读目的；不对整段内容做高度动画，避免切换时挤动图表。
struct SegmentTabBar: View {
    @Binding var selection: ResultSegments.Segment
    let title: (ResultSegments.Segment) -> String

    var body: some View {
        HStack(alignment: .top, spacing: 6) {
            ForEach(ResultSegments.Segment.allCases) { segment in
                let selected = segment == selection
                Button { selection = segment } label: {
                    VStack(spacing: 6) {
                        Text(title(segment))
                            .font(.subheadline.weight(selected ? .semibold : .regular))
                            .foregroundStyle(selected ? Theme.textPrimary : Theme.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(subtitle(segment))
                            .font(.caption)
                            .foregroundStyle(Theme.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                        Capsule()
                            .fill(selected ? Theme.accent : .clear)
                            .frame(height: 2)
                    }
                    .frame(maxWidth: .infinity, minHeight: 44, maxHeight: .infinity)
                    .padding(.horizontal, 6)
                    .padding(.top, 10)
                    .padding(.bottom, 6)
                    .background(selected ? Theme.surfaceAlt : Theme.surface,
                                in: RoundedRectangle(cornerRadius: 10))
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(selected ? [.isSelected] : [])
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    private func subtitle(_ segment: ResultSegments.Segment) -> String {
        switch segment {
        case .analysis: return L("位置与依据")
        case .signals: return L("类型与确认")
        case .risk: return L("待确认与限制")
        }
    }
}
