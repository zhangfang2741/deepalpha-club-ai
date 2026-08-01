// Views/ReviewModeIcon.swift
import SwiftUI

/// 播放顺序图标。加入顺序使用上下平行的双右箭头，和交叉的随机乱序形成对照。
struct ReviewModeIcon: View {
    let mode: ReviewMode

    var body: some View {
        Group {
            if mode == .sequential {
                ZStack {
                    Image(systemName: "arrow.right")
                        .offset(y: -4.5)
                    Image(systemName: "arrow.right")
                        .offset(y: 4.5)
                }
                .font(.system(size: 15, weight: .semibold))
            } else {
                Image(systemName: mode.systemImage)
                    .font(.system(size: 20, weight: .semibold))
            }
        }
        .accessibilityHidden(true)
    }
}
