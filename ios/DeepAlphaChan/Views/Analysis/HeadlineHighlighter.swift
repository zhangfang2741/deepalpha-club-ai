import SwiftUI

/// 把「当前状态」摘要（`structureHeadline`/`narrative.headline`）里的缠论术语
/// 按结构类别着色。
///
/// 后端只给纯文本，没有也不该给富文本标记——着色是纯展示层的事，不该让后端
/// 为了 UI 样式去拼 Markdown/HTML。
///
/// 颜色和「查看判断依据」展开区里 `StructureLayerRow` 的色标用同一套映射
/// （笔=蓝/线段=橙/中枢=紫/背驰=粉/买点=红/卖点=绿）：同一张卡片里，摘要句子里的
/// 「线段」和下面判断依据里「线段」这个标签必须是同一个颜色，用户才不会
/// 看着像两套互不相干的系统。不要在这两处各自发明一套配色。
enum HeadlineHighlighter {
    private struct Rule {
        let pattern: String
        let color: Color
    }

    private static let rules: [Rule] = [
        Rule(pattern: "(上升|下降|向上|向下)?线段|\\b[Ss]egments?\\b", color: Theme.segment),
        Rule(pattern: "(上升|下降|向上|向下)?笔|\\b[Ss]trokes?\\b", color: Theme.stroke),
        Rule(pattern: "中枢|\\b[Pp]ivots?\\b", color: Theme.pivotFill),
        Rule(pattern: "(顶背驰|底背驰|背驰|[Dd]ivergence)", color: Theme.divergence),
        Rule(pattern: "[一二三]买(（候选）)?|[123](st|nd|rd) Buy", color: Theme.up),
        Rule(pattern: "[一二三]卖(（候选）)?|[123](st|nd|rd) Sell", color: Theme.down),
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
