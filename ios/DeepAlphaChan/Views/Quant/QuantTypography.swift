import SwiftUI

/// 向分析师评级的 15pt 标题、13pt 正文和 11pt 辅助信息对齐，保留动态字号。
enum QuantTypography {
    static let summary = Font.headline.weight(.semibold)
    static let title = Font.subheadline.weight(.semibold)
    static let body = Font.footnote
    static let emphasis = Font.footnote.weight(.semibold)
    static let value = Font.subheadline.weight(.semibold)
    static let caption = Font.caption
    static let metadata = Font.caption2
}
