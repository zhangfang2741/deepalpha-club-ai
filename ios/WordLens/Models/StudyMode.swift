// Models/StudyMode.swift
import Foundation

/// 学习方式：只听 or 听写（存 UserDefaults，首页顶部可切换）。
///
/// 沿用仓库里既有的偏好项写法（ReviewMode / PronunciationSource 都是 enum +
/// 静态 current + UserDefaults）。默认只听，保证老用户升级后行为不变。
///
/// 跟 `ReviewMode`（队列排序方式）是两个正交的维度：ReviewMode 决定「按什么
/// 顺序过这些词」，StudyMode 决定「每个词怎么过」。
enum StudyMode: String, CaseIterable {
    /// 只听：卡片正面显示单词，翻卡看释义再评分——现有行为。
    case listenOnly
    /// 听写：单词藏起来，卡片本身是填写框，写完自动判定并评分。
    case dictation

    private static let key = "study_mode"

    static var current: StudyMode {
        get {
            let raw = UserDefaults.standard.string(forKey: key) ?? listenOnly.rawValue
            return StudyMode(rawValue: raw) ?? .listenOnly
        }
        set { UserDefaults.standard.set(newValue.rawValue, forKey: key) }
    }

    var label: String {
        switch self {
        case .listenOnly: return "只听"
        case .dictation: return "听写"
        }
    }

    var systemImage: String {
        switch self {
        case .listenOnly: return "headphones"
        case .dictation: return "square.and.pencil"
        }
    }

    var toggled: StudyMode {
        self == .listenOnly ? .dictation : .listenOnly
    }
}

/// 听写模式下每个词经历的两个相位。
///
/// `.revealed` 把「被判定的那个词」和「用户当时写的内容」一起快照进来，而不是
/// 让界面去读 `currentWord` / `dictationInput`：提交评分会把当前词移出队列、
/// currentWord 立刻指向下一个词，界面若跟着读实时值，就会在切换的缝隙里闪出
/// **下一个词**的正确拼写——听写模式下这等于提前泄题。快照之后，亮答案期间
/// 显示什么完全跟队列的时序无关。
enum DictationPhase: Equatable {
    /// 卡片是填写框，等用户写。
    case input
    /// 已判定：亮出正确答案 + 结果，短暂停留后自动进下一词。
    case revealed(word: VocabularyWord, input: String, rating: ReviewRating)

    var isInput: Bool {
        if case .input = self { return true }
        return false
    }

    var rating: ReviewRating? {
        if case .revealed(_, _, let rating) = self { return rating }
        return nil
    }
}
