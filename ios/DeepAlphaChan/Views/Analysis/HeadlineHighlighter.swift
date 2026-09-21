import SwiftUI

/// 把大白话摘要（`narrative.headline`）里的缠论术语按结构级别着色。
///
/// 后端只给纯文本，没有也不该给富文本标记——着色是纯展示层的事，不该让
/// `narrative.py` 为了 UI 样式去拼 Markdown/HTML。
///
/// 着色规则（对照设计稿反推确认）：**大级别结构**（线段/中枢/背驰，这些是
/// 描述"大盘面在哪个阶段"的词）用橙色；**小级别/当下细节**（笔、买卖点信号、
/// 价格相对中枢的位置描述）用紫色。不是多空二分，也不是简单的固定关键词
/// 表——「现价站上中枢上方」这类价格位置从句要整句染紫色，即使句子中间出现
/// 了单独该染橙色的「中枢」二字，也要跟着从句走紫色，所以价格位置规则必须
/// 放在最后整体覆盖（`highlight` 按数组顺序应用，后应用的规则覆盖先应用的）。
enum HeadlineHighlighter {
    private struct Rule {
        let pattern: String
        let color: Color
    }

    private static let rules: [Rule] = [
        // 大级别结构：线段 / 中枢 / 背驰
        Rule(pattern: "(上升|下降|向上|向下)?线段", color: Theme.segment),
        Rule(pattern: "中枢", color: Theme.segment),
        Rule(pattern: "(顶背驰|底背驰|背驰)", color: Theme.segment),
        // 小级别/当下细节：笔、买卖点信号
        Rule(pattern: "(上升|下降|向上|向下)?笔", color: Theme.pivotFill),
        Rule(pattern: "[一二三](买|卖)(（候选）)?", color: Theme.pivotFill),
        // 价格位置从句：整句染色，放最后覆盖从句内被前面规则单独染色的词
        // （如「现价站上中枢上方」里的「中枢」不能被单独染成橙色）
        Rule(pattern: "现价[^，。！]{0,24}?(上方|下方|以上|以下)", color: Theme.pivotFill),
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
