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
    /// 听写：单词藏起来，写完自动判定；右滑接受结论，左滑重新听写。
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
        case .listenOnly: return L("只听")
        case .dictation: return L("听写")
        }
    }

    var systemImage: String {
        switch self {
        case .listenOnly: return "headphones"
        case .dictation: return "square.and.pencil"
        }
    }
}

/// 听写模式下每个词经历的两个相位。
///
/// `.revealed` 把「被判定的那个词」和「用户当时写的内容」一起快照进来，而不是
/// 让界面去读 `currentWord` / `dictationInput`。系统判定后先停在结果页，右滑接受
/// 才提交并切词，左滑则丢弃结论重新听写；快照保证整个决策期间展示内容稳定。
enum DictationPhase: Equatable {
    /// 卡片是填写框，等用户写。
    case input
    /// 已判定：亮出正确答案 + 结果，等待用户右滑接受或左滑重新听写。
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
