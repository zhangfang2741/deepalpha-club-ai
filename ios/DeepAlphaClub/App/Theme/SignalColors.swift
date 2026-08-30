import SwiftUI
import DeepAlphaCore

/// polarity → 颜色。语义见 Theme 里的说明：绿=看多、红=看空（对齐 web 版交易台）。
extension Polarity {
    var tint: Color {
        switch self {
        case .bull: Theme.bull
        case .bear: Theme.bear
        case .neutral: Theme.neutral
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
        case .buy: Theme.bull
        case .sell: Theme.bear
        case .hold: Theme.neutral
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
        case .idle, .cancelled: Theme.textSecondary
        case .running: Theme.accent
        case .paused, .interrupted: Theme.warning
        case .completed: Theme.success
        case .failed: Theme.danger
        }
    }
}
