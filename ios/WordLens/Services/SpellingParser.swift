// Services/SpellingParser.swift
import Foundation

/// 把「逐个字母拼读」的语音识别结果还原成一个单词。
///
/// 通用语音识别没有「拼读」这个概念。用户念 A-P-P-L-E，它按自然语言去理解，回来的
/// 可能是 `a p p l e`、`APPLE`、`AP PLE`，也可能是把字母名当成词的 `eh pee pee el ee`
/// （c-a-t 更常见的形态是 `see a tea`）。这一层负责把这些形态统一折回 `apple`，
/// 再交给 DictationJudge 判定。
///
/// 纯函数、零状态、零依赖——和 DictationJudge 一样，规则密集且极易写错，所以单独
/// 成文件、单独测（见 Tests/main.swift）。
enum SpellingParser {
    /// 判定为「拼读」所需的字母 token 占比。
    ///
    /// 不能只要有一个 token 像字母就按拼读处理：`sea food` 里 `sea` 是 C 的同音词，
    /// 但整句是两个真词，硬转就成了 `cfood`。要求多数 token 都像字母，才认定用户
    /// 是在一个一个字母地念。
    private static let spellingRatio = 0.6

    /// 字母名的常见识别形态 → 字母本身。只收多字符形态，单个字母由 `letter(for:)`
    /// 直接放行。`are`/`you`/`sea` 这类本身就是常用词的条目靠 `spellingRatio` 兜底，
    /// 不会在正常语句里被误转。
    private static let letterNames: [String: Character] = [
        "ay": "a", "eh": "a", "hey": "a",
        "be": "b", "bee": "b",
        "see": "c", "sea": "c", "cee": "c",
        "dee": "d",
        "ee": "e",
        "ef": "f", "eff": "f",
        "gee": "g", "jee": "g",
        "aitch": "h", "haitch": "h", "each": "h",
        "eye": "i", "aye": "i",
        "jay": "j",
        "kay": "k", "cay": "k",
        "el": "l", "ell": "l",
        "em": "m",
        "en": "n",
        "oh": "o", "owe": "o",
        "pee": "p", "pea": "p",
        "cue": "q", "queue": "q", "kew": "q",
        "ar": "r", "are": "r",
        "es": "s", "ess": "s",
        "tee": "t", "tea": "t",
        "you": "u", "yu": "u", "ewe": "u",
        "vee": "v",
        "doubleu": "w", "doubleyou": "w",
        "ex": "x", "eks": "x",
        "why": "y", "wye": "y",
        "zee": "z", "zed": "z",
    ]

    /// W 读作 "double u"，识别器多半会切成两个 token，先合成一个再往下走。
    private static let doubleUTails: Set<String> = ["u", "you", "yu", "w"]

    /// 拆成小写 token：字母以外的一切（空格、连字符、标点）都当分隔符。
    static func tokenize(_ text: String) -> [String] {
        text.lowercased()
            .split(whereSeparator: { !$0.isLetter })
            .map(String.init)
    }

    /// 单个 token 对应哪个字母；不像字母就返回 nil。
    static func letter(for token: String) -> Character? {
        if token.count == 1, let ch = token.first, ch.isLetter { return ch }
        return letterNames[token]
    }

    /// 还原一次拼读输入。不像拼读的输入原样放行（只做小写化和去分隔符）。
    static func parse(_ transcript: String) -> String {
        let tokens = mergeDoubleU(tokenize(transcript))

        // 只有一个 token 时一律当整词：`bee` 既是 B 的读法也是一个真单词，
        // 这种没有上下文可依据的情况下，把用户听到的原词交回去更安全。
        guard tokens.count > 1 else { return tokens.first ?? "" }

        let letterLike = tokens.filter { letter(for: $0) != nil }.count
        guard Double(letterLike) / Double(tokens.count) >= spellingRatio else {
            // 不是拼读：直接拼起来。分隔符本来就会被 DictationJudge.normalize 抹掉，
            // 这里去掉只是让输入框里显示得干净些。
            return tokens.joined()
        }

        // 是拼读：能认出的字母换成字母，认不出的 token 原样留着——它多半是识别器把
        // 连续几个字母并成的块（`AP` `PLE`），删掉反而丢信息。
        return tokens.map { letter(for: $0).map(String.init) ?? $0 }.joined()
    }

    private static func mergeDoubleU(_ tokens: [String]) -> [String] {
        var result: [String] = []
        var index = 0
        while index < tokens.count {
            if tokens[index] == "double",
               index + 1 < tokens.count,
               doubleUTails.contains(tokens[index + 1]) {
                result.append("w")
                index += 2
            } else {
                result.append(tokens[index])
                index += 1
            }
        }
        return result
    }
}
