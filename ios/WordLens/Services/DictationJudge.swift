// Services/DictationJudge.swift
import Foundation

/// 听写判定：把「用户写的」和「正确单词」比一比，给出三档评分。
///
/// 纯函数、零状态、零依赖——判定规则是这个功能里最容易出错、也最需要能单独
/// 验证的一块，所以从界面和状态机里彻底摘出来。
enum DictationJudge {
    /// 按答案长度决定最多容忍几个字母的差错才还算「模糊」。
    ///
    /// 不能只看绝对距离：`it` 写成 `at`、`cat` 写成 `cot`、`card` 写成 `cart`
    /// 都只差 1 个字母，但它们是彻头彻尾的另一个词，判「模糊」等于告诉用户
    /// "你差不多记住了"，是误导。词越短，一个字母的分量越重。
    ///
    /// - 1~4 个字母：一个错都不容，错了就是不认识
    /// - 5~7 个字母：容 1 个（`hous` → `house` 算笔误）
    /// - 8 个字母以上：容 2 个（`boundry` → `boundary`）
    static func maxFuzzyDistance(forAnswerLength length: Int) -> Int {
        switch length {
        case ..<5: return 0
        case ..<8: return 1
        default: return 2
        }
    }

    /// 归一化：小写 → 去首尾空白 → 删掉所有连字符 / 空格 / 下划线。
    ///
    /// 词库里 `online-shopping`、`modern-innovation` 这类复合词很多，用户可能写成
    /// `online shopping` 或 `onlineshopping`——那都是同一个词，不该因为分隔符
    /// 敲得不一样就判错。三种写法在这里全折成 `onlineshopping`。
    static func normalize(_ text: String) -> String {
        text.lowercased()
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .filter { $0 != "-" && $0 != " " && $0 != "_" }
    }

    /// 标准 Levenshtein 编辑距离（插入/删除/替换各算 1）。
    /// 用滚动数组，只保留上一行，单词长度这个量级完全够用。
    static func levenshtein(_ a: [Character], _ b: [Character]) -> Int {
        if a.isEmpty { return b.count }
        if b.isEmpty { return a.count }

        var previous = Array(0...b.count)
        var current = [Int](repeating: 0, count: b.count + 1)

        for i in 1...a.count {
            current[0] = i
            for j in 1...b.count {
                let cost = a[i - 1] == b[j - 1] ? 0 : 1
                current[j] = min(
                    previous[j] + 1,       // 删除
                    current[j - 1] + 1,    // 插入
                    previous[j - 1] + cost // 替换
                )
            }
            previous = current
        }
        return previous[b.count]
    }

    /// 判定一次听写。
    ///
    /// - 空输入 → 不认识
    /// - 归一化后完全一致 → 认识
    /// - 编辑距离在 `maxFuzzyDistance(forAnswerLength:)` 允许范围内 → 模糊
    /// - 其余 → 不认识
    static func judge(input: String, answer: String) -> ReviewRating {
        let normalizedInput = normalize(input)
        let normalizedAnswer = normalize(answer)

        guard !normalizedInput.isEmpty else { return .unknown }
        if normalizedInput == normalizedAnswer { return .known }

        let allowed = maxFuzzyDistance(forAnswerLength: normalizedAnswer.count)
        guard allowed > 0 else { return .unknown }

        let distance = levenshtein(Array(normalizedInput), Array(normalizedAnswer))
        return distance <= allowed ? .fuzzy : .unknown
    }
}
