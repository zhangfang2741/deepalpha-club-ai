import SwiftUI

/// 窄屏的三面板切换器。
///
/// 没用系统 `Picker(.segmented)`：那个控件没法给单个分段挂角标，而窄屏一次只
/// 看得到一个面板——裁决在「决策」页出来时，正盯着「推理」页的人完全不知道。
/// 角标就是为这件事存在的。
struct PaneSelector<Pane: Hashable & Identifiable>: View {
    let panes: [Pane]
    @Binding var selection: Pane
    /// 需要提示「有新内容」的分段
    let badged: Set<Pane>
    let label: (Pane) -> String

    var body: some View {
        HStack(spacing: 4) {
            ForEach(panes) { pane in
                Button {
                    selection = pane
                } label: {
                    Text(label(pane))
                        .font(.subheadline.weight(selection == pane ? .semibold : .regular))
                        .foregroundStyle(selection == pane ? Theme.textPrimary : Theme.textSecondary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                        .background(
                            selection == pane ? Theme.surfaceAlt : Color.clear,
                            in: RoundedRectangle(cornerRadius: 8))
                        .overlay(alignment: .topTrailing) {
                            if badged.contains(pane) && selection != pane {
                                Circle()
                                    .fill(Theme.bull)
                                    .frame(width: 7, height: 7)
                                    .padding(.top, 5)
                                    .padding(.trailing, 10)
                            }
                        }
                }
                .buttonStyle(.plain)
            }
        }
        .padding(3)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 11))
    }
}
