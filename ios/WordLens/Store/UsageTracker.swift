// Store/UsageTracker.swift
import Foundation

/// 免费用户每日额度追踪（端上，UserDefaults 按自然日归零）。
///
/// 两类额度：
///   - 拍照识别：每天最多 `freeDailyPhotoLimit` 次（按成功发起的识别计次）。
///   - 学习单词：每天最多学 `freeDailyWordLimit` 个「不同」的新词。同一个词当天
///     重复学不重复计数，只有学第 N+1 个新词时才被拦截。
///
/// 说明：端上计数便于快速实现，但可被重装/改时间绕过；如需严格限制，可改由
/// 后端按用户维度校验（后续加固）。订阅用户完全不受这里限制（调用方用
/// `StoreManager.isSubscribed` 短路，不进这里的判断）。
@MainActor
final class UsageTracker: ObservableObject {
    /// 今日已用掉的拍照识别次数。
    @Published private(set) var photosUsedToday = 0
    /// 今日已学过的单词 ID 集合。
    @Published private(set) var learnedWordIDsToday: Set<String> = []

    private let defaults = UserDefaults.standard
    private let dateKey = "free_usage_date"
    private let photoKey = "free_usage_photos"
    private let wordsKey = "free_usage_learned_words"

    var photoLimit: Int { AppConfig.freeDailyPhotoLimit }
    var wordLimit: Int { AppConfig.freeDailyWordLimit }

    var photosRemaining: Int { max(0, photoLimit - photosUsedToday) }
    var wordsLearnedToday: Int { learnedWordIDsToday.count }
    var wordsRemaining: Int { max(0, wordLimit - wordsLearnedToday) }

    init() { rolloverIfNeeded() }

    /// 供 UI 主动对齐日期：额度判定本身会在 `canTakePhoto()` / `canLearn()` 里
    /// rollover，但那要等用户先动手。展示用量的视图出现时调一次，避免 App 跨过
    /// 午夜仍停在前台时显示昨天的数字。
    func refresh() { rolloverIfNeeded() }

    private var todayString: String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        return f.string(from: Date())
    }

    /// 跨天则把两类额度都清零。每次读写前都先调，保证过了午夜自动重置。
    private func rolloverIfNeeded() {
        if defaults.string(forKey: dateKey) != todayString {
            defaults.set(todayString, forKey: dateKey)
            defaults.removeObject(forKey: photoKey)
            defaults.removeObject(forKey: wordsKey)
            photosUsedToday = 0
            learnedWordIDsToday = []
        } else {
            photosUsedToday = defaults.integer(forKey: photoKey)
            learnedWordIDsToday = Set(defaults.stringArray(forKey: wordsKey) ?? [])
        }
    }

    // MARK: - 拍照识别

    /// 今天还能不能免费拍照识别。
    func canTakePhoto() -> Bool {
        rolloverIfNeeded()
        return photosUsedToday < photoLimit
    }

    /// 记录一次拍照识别。
    func recordPhoto() {
        rolloverIfNeeded()
        photosUsedToday += 1
        defaults.set(photosUsedToday, forKey: photoKey)
    }

    // MARK: - 学习单词

    /// 这个词今天能不能学：已学过（不重复计）或今日新词额度未用尽。
    func canLearn(wordID: String) -> Bool {
        rolloverIfNeeded()
        if wordID.isEmpty { return true }
        return learnedWordIDsToday.contains(wordID) || learnedWordIDsToday.count < wordLimit
    }

    /// 记录学过一个词（同一个词重复调用无副作用）。
    func recordLearned(wordID: String) {
        rolloverIfNeeded()
        guard !wordID.isEmpty, !learnedWordIDsToday.contains(wordID) else { return }
        learnedWordIDsToday.insert(wordID)
        defaults.set(Array(learnedWordIDsToday), forKey: wordsKey)
    }
}
