import SwiftUI

/// 阶段节点以细圆环、中心圆点和文字字重标记状态，保留足够的点击范围。
struct QuantStageNode: View {
    let stage: QuantLifecycleStage
    let isCurrent: Bool
    let vertical: Bool

    var body: some View {
        Group {
            if vertical {
                HStack(spacing: 12) {
                    marker
                    Text(stage.title).font(QuantTypography.body)
                    Spacer()
                }
                .padding(.horizontal, 8)
                .frame(minHeight: 44)
            } else {
                VStack(spacing: 5) {
                    HStack(spacing: 0) {
                        Rectangle().fill(stage == .intro ? Color.clear : Theme.border).frame(height: 1)
                        marker
                        Rectangle().fill(stage == .decline ? Color.clear : Theme.border).frame(height: 1)
                    }
                    Text(stage.shortTitle).font(QuantTypography.caption.weight(isCurrent ? .semibold : .regular))
                }
                .padding(.vertical, 4)
                .frame(maxWidth: .infinity, minHeight: 44)
            }
        }
        .foregroundStyle(isCurrent ? Theme.accent : Theme.textSecondary)
        .contentShape(Rectangle())
    }

    private var marker: some View {
        ZStack {
            Circle().fill(isCurrent ? Theme.accent : Theme.surfaceAlt)
            Circle().stroke(isCurrent ? Theme.accent : Theme.border, lineWidth: isCurrent ? 1.5 : 1)
            if isCurrent {
                Circle().fill(Theme.textPrimary).frame(width: 3, height: 3)
            }
        }
        .frame(width: 10, height: 10)
        .accessibilityHidden(true)
    }
}
