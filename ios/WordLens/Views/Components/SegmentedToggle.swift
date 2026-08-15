// Views/Components/SegmentedToggle.swift
import SwiftUI

/// 胶囊分段切换器。
///
/// 复用复习页「只听 / 听写」那套视觉：深色底 + 描边胶囊，选中项填充主题蓝。
/// 系统的 `.pickerStyle(.segmented)` 在这个深色主题里显得很突兀——它自带浅灰
/// 背景和不受控的圆角，和 App 其余部分（Theme.surface + Theme.border 描边）
/// 完全是两套语言。
///
/// 与复习页那个的差别：这里的分段要放整词（「手机号」「邮箱」），所以宽度按内容
/// 自适应并均分，而不是固定 44pt 的图标位。
struct SegmentedToggle<T: Hashable>: View {
    let options: [T]
    let label: (T) -> String
    @Binding var selection: T

    /// 让选中态胶囊在两个分段之间滑动，而不是生硬地闪现。
    @Namespace private var indicator

    var body: some View {
        HStack(spacing: 0) {
            ForEach(options, id: \.self) { option in
                let isSelected = selection == option
                Button {
                    withAnimation(.easeInOut(duration: 0.22)) { selection = option }
                } label: {
                    Text(label(option))
                        .font(.subheadline.weight(isSelected ? .semibold : .regular))
                        .foregroundStyle(isSelected ? .white : Theme.textSecondary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 9)
                        .background {
                            if isSelected {
                                Capsule()
                                    .fill(Theme.accent)
                                    .matchedGeometryEffect(id: "seg", in: indicator)
                            }
                        }
                        .contentShape(.rect)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(label(option))
                .accessibilityAddTraits(isSelected ? [.isSelected] : [])
            }
        }
        .padding(3)
        .background(Capsule().fill(Theme.surface))
        .overlay(Capsule().strokeBorder(Theme.border, lineWidth: 1))
        .accessibilityElement(children: .contain)
    }
}
