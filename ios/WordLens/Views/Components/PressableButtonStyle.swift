// Views/Components/PressableButtonStyle.swift
import SwiftUI

/// 统一的按钮按压反馈：按下时轻微缩小+变暗，松开弹回。
///
/// 项目里大部分按钮是自定义背景色的整块视图（不是系统默认样式），没显式指定
/// buttonStyle 时要么完全没反馈、要么用 `.plain` 主动去掉了系统默认的按压效果——
/// 点哪里都跟没点一样。统一套这一个 style 而不是每个按钮各自写一遍缩放动画。
struct PressableButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.96 : 1.0)
            .opacity(configuration.isPressed ? 0.7 : 1.0)
            .animation(.easeOut(duration: 0.15), value: configuration.isPressed)
    }
}

extension ButtonStyle where Self == PressableButtonStyle {
    static var pressable: PressableButtonStyle { PressableButtonStyle() }
}
