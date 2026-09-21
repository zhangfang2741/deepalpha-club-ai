import SwiftUI

/// 把大白话摘要（`narrative.headline`）里的缠论术语按关键词着色。
///
/// 后端只给纯文本，没有也不该给富文本标记——着色是纯展示层的事，不该让
/// `narrative.py` 为了 UI 样式去拼 Markdown/HTML。颜色复用 `Theme` 里已有的
/// 图层图例色（笔/线段/中枢的叠加色本来就是蓝/橙/紫），保证这里的高亮和图表
/// 图层开关用的是同一套颜色语言，不会出现"文字里线段是紫色，图上线段是橙色"
/// 这种自相矛盾。
enum HeadlineHighlighter {
    private struct Rule {
        let pattern: String
        let color: Color
    }

    // 顺序无所谓：各规则匹配的关键词互不重叠（笔/线段/中枢/背驰/买卖点是不同的词）。
    private static let rules: [Rule] = [
        Rule(pattern: "(上升|下降|向上|向下)?线段", color: Theme.segment),
        Rule(pattern: "(上升|下降|向上|向下)?笔", color: Theme.stroke),
        Rule(pattern: "中枢", color: Theme.pivotFill),
        Rule(pattern: "(顶背驰|底背驰|背驰)", color: Theme.segment),
        Rule(pattern: "[一二三](买)(（候选）)?", color: Theme.up),   // 买点=偏多，跟涨跌配色一致（红涨）
        Rule(pattern: "[一二三](卖)(（候选）)?", color: Theme.down), // 卖点=偏空（绿跌）
    ]

    /// 对纯文本做关键词着色，匹配不到任何关键词时原样返回（不着色，不报错）。
    static func highlight(_ text: String) -> AttributedString {
        var attributed = AttributedString(text)
        for rule in rules {
            guard let regex = try? NSRegularExpression(pattern: rule.pattern) else { continue }
            let matches = regex.matches(in: text, range: NSRange(text.startIndex..., in: text))
            for match in matches {
                guard let swiftRange = Range(match.range, in: text),
                      let attrRange = Range(swiftRange, in: attributed) else { continue }
                attributed[attrRange].foregroundColor = rule.color
            }
        }
        return attributed
    }
}
