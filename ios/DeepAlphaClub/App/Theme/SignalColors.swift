import SwiftUI
import DeepAlphaCore

/// polarity → 颜色（系统色自动适配暗黑模式，对齐 web 的 green/red/amber/blue）。
extension Polarity {
    var tint: Color {
        switch self {
        case .bull: .green
        case .bear: .red
        case .neutral: .orange
        }
    }
    var label: String {
        switch self {
        case .bull: "看多"
        case .bear: "看空"
        case .neutral: "中性"
        }
    }
}

extension VerdictSignal {
    var label: String {
        switch self {
        case .buy: "买入"
        case .sell: "卖出"
        case .hold: "观望"
        }
    }
    var tint: Color {
        switch self {
        case .buy: .green
        case .sell: .red
        case .hold: .orange
        }
    }
}

extension RunStatus {
    var label: String {
        switch self {
        case .idle: "空闲"
        case .running: "运行中"
        case .paused: "已暂停"
        case .completed: "已完成"
        case .cancelled: "已取消"
        case .failed: "已失败"
        case .interrupted: "中断"
        }
    }
    var tint: Color {
        switch self {
        case .idle, .cancelled: .gray
        case .running: .blue
        case .paused, .interrupted: .orange
        case .completed: .green
        case .failed: .red
        }
    }
}
