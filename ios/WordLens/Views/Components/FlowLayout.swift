// Views/Components/FlowLayout.swift
import SwiftUI

/// 自动换行的横向流式布局：一行放不下就换到下一行。
///
/// 给分组 chip 用。原来那排 chip 放在横向 ScrollView 里，分组一多就得左右滑才
/// 能看全——既容易漏看，也让「选分组」这个动作多了一步找的成本。改用流式布局后
/// 所有分组一次全部铺开、位置固定不动，一眼看得到全部。
///
/// SwiftUI 没有内置的 flow layout（LazyVGrid 要求每列等宽，chip 宽度按文字长短
/// 变化，套上去会留下大片空白），所以用 Layout 协议自己排。
struct FlowLayout: Layout {
    var spacing: CGFloat = 8
    var lineSpacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        let rows = arrange(subviews: subviews, maxWidth: maxWidth)
        let height = rows.reduce(CGFloat.zero) { $0 + $1.height } +
            lineSpacing * CGFloat(max(rows.count - 1, 0))
        return CGSize(width: maxWidth == .infinity ? rows.map(\.width).max() ?? 0 : maxWidth,
                      height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let rows = arrange(subviews: subviews, maxWidth: bounds.width)
        var y = bounds.minY
        for row in rows {
            var x = bounds.minX
            for index in row.indices {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(
                    at: CGPoint(x: x, y: y + (row.height - size.height) / 2),
                    proposal: ProposedViewSize(size)
                )
                x += size.width + spacing
            }
            y += row.height + lineSpacing
        }
    }

    /// 把子视图按「累计宽度超出就换行」切成若干行。
    private func arrange(subviews: Subviews, maxWidth: CGFloat) -> [Row] {
        var rows: [Row] = []
        var current = Row()
        for index in subviews.indices {
            let size = subviews[index].sizeThatFits(.unspecified)
            let widthWithItem = current.indices.isEmpty
                ? size.width
                : current.width + spacing + size.width
            if !current.indices.isEmpty, widthWithItem > maxWidth {
                rows.append(current)
                current = Row()
                current.append(index: index, size: size, spacing: spacing)
            } else {
                current.append(index: index, size: size, spacing: spacing)
            }
        }
        if !current.indices.isEmpty { rows.append(current) }
        return rows
    }

    private struct Row {
        var indices: [Int] = []
        var width: CGFloat = 0
        var height: CGFloat = 0

        mutating func append(index: Int, size: CGSize, spacing: CGFloat) {
            width += indices.isEmpty ? size.width : spacing + size.width
            height = max(height, size.height)
            indices.append(index)
        }
    }
}
