// Models/PlaylistModels.swift
import Foundation

/// 自定义歌单，对应后端 PlaylistResponse。
struct Playlist: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let wordCount: Int
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, name
        case wordCount = "word_count"
        case createdAt = "created_at"
    }
}

/// 对应后端 PlaylistListResponse。
struct PlaylistListResponse: Codable {
    let playlists: [Playlist]
}

/// 生词库各分组计数，对应后端 VocabularyStatsResponse。
/// 播放列表面板靠它在每个分组旁显示词数，不必把整个生词库拉下来自己数。
struct VocabularyStats: Codable {
    let dueCount: Int
    let newCount: Int
    let fuzzyCount: Int
    let knownCount: Int
    let totalCount: Int

    static let empty = VocabularyStats(dueCount: 0, newCount: 0, fuzzyCount: 0, knownCount: 0, totalCount: 0)

    enum CodingKeys: String, CodingKey {
        case dueCount = "due_count"
        case newCount = "new_count"
        case fuzzyCount = "fuzzy_count"
        case knownCount = "known_count"
        case totalCount = "total_count"
    }
}

/// 当前在播的是哪一组词。
///
/// 内置分组（待复习 / 三个状态）都能由既有查询算出来，不落库；只有 `.custom`
/// 指向后端存的歌单。整个 App 里「当前播放列表」就靠这一个值表达——复习卡的
/// 队列来源、标题、空态文案、锁屏显示的副标题全从它派生。
///
/// Codable 用来存 UserDefaults：重启 App 后仍停在上次选的组，跟音乐 App 记住
/// 你上次听的歌单是一个道理。
enum PlaylistSelection: Hashable, Codable {
    case dueReview
    case status(String)   // "new" / "fuzzy" / "known"
    case custom(String)   // 歌单 id

    private static let storageKey = "current_playlist_selection"

    /// 上次选的组；没存过、或存的歌单已被删（解码失败）时回落到待复习。
    static var current: PlaylistSelection {
        get {
            guard let data = UserDefaults.standard.data(forKey: storageKey),
                  let value = try? JSONDecoder().decode(PlaylistSelection.self, from: data) else {
                return .dueReview
            }
            return value
        }
        set {
            guard let data = try? JSONEncoder().encode(newValue) else { return }
            UserDefaults.standard.set(data, forKey: storageKey)
        }
    }

    /// 内置分组的固定名字；自定义歌单的名字要查 `Playlist.name`，所以这里返回
    /// nil，由 `displayName(playlists:)` 补上。
    private var builtinName: String? {
        switch self {
        case .dueReview: return "待复习"
        case .status("new"): return "不认识"
        case .status("fuzzy"): return "模糊"
        case .status("known"): return "认识"
        case .status: return "生词"
        case .custom: return nil
        }
    }

    /// 展示用名字。自定义歌单需要传入已加载的歌单列表来查名字；查不到（比如歌单
    /// 刚被另一台设备删掉）时给一个中性兜底，不会崩也不会显示成一串 uuid。
    func displayName(playlists: [Playlist] = []) -> String {
        if let builtinName { return builtinName }
        if case .custom(let id) = self {
            return playlists.first { $0.id == id }?.name ?? "歌单"
        }
        return "生词"
    }

    /// 队列为空时的提示文案 —— 待复习和其它分组的「空」含义完全不同。
    var emptyTitle: String {
        switch self {
        case .dueReview: return "今天没有待复习的单词"
        case .status: return "这个分组里还没有单词"
        case .custom: return "这个歌单还没有单词"
        }
    }

    var emptyDescription: String {
        switch self {
        case .dueReview, .status: return "去拍照识别一些新单词吧"
        case .custom: return "在播放列表里编辑歌单，把想背的词加进来"
        }
    }

    /// 全部评分完的提示文案。
    var finishedTitle: String {
        switch self {
        case .dueReview: return "今日复习完成 🎉"
        case .status, .custom: return "这一组过完了 🎉"
        }
    }

    /// 是不是用户自建的歌单（决定面板里显不显示编辑/删除操作）。
    var isCustom: Bool {
        if case .custom = self { return true }
        return false
    }
}
