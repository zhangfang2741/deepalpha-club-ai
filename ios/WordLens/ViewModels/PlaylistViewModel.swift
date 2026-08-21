// ViewModels/PlaylistViewModel.swift
import Foundation

/// 播放列表面板的状态：各分组的词数 + 自定义歌单列表 + 歌单增删改。
///
/// 只管「有哪些组、各有多少词」，不碰当前播放队列本身——那是 ReviewViewModel
/// 的事。两者通过一个 PlaylistSelection 值对接。
@MainActor
final class PlaylistViewModel: ObservableObject {
    private static let playlistCacheTTL: TimeInterval = 30

    @Published private(set) var stats: VocabularyStats = .empty
    @Published private(set) var playlists: [Playlist] = []
    @Published private(set) var isLoadingPlaylists = false
    @Published private(set) var isLoadingStats = false
    @Published var errorMessage: String?

    /// 当前正在删除的分组 ID——行内 UI 拿来降透明 + 禁用按钮，避免用户在
    /// 删除请求飞行期间又去操作这一行。删除请求结束后会自动清掉。
    @Published private(set) var deletingPlaylistID: String?

    private var playlistsLoadedAt: Date?
    private var playlistsLoadTask: Task<[Playlist], Error>?
    private var playlistsLoadID: UUID?
    private var statsLoadTask: Task<VocabularyStats, Error>?
    private var statsLoadID: UUID?

    var isLoading: Bool { isLoadingPlaylists || isLoadingStats }

    /// 同时刷新统计和自定义分组。两个接口互不依赖，并行请求；分组列表一返回就
    /// 立即写入，不再被较慢的统计接口挡住。
    func load(forcePlaylists: Bool = false) async {
        errorMessage = nil
        async let statsLoad: Void = loadStats()
        async let playlistsLoad: Void = loadPlaylists(force: forcePlaylists)
        _ = await (statsLoad, playlistsLoad)
    }

    /// 只加载自定义分组。30 秒内复用已有结果；空列表也会缓存，因此新用户反复
    /// 打开分组管理不会每次都重新等待网络。并发调用会共用同一个 Task。
    func loadPlaylists(force: Bool = false) async {
        if !force,
           let playlistsLoadedAt,
           Date.now.timeIntervalSince(playlistsLoadedAt) < Self.playlistCacheTTL {
            return
        }

        let loadID: UUID
        let task: Task<[Playlist], Error>
        if let existingTask = playlistsLoadTask, let existingID = playlistsLoadID {
            loadID = existingID
            task = existingTask
        } else {
            loadID = UUID()
            task = Task { try await WordService.listPlaylists() }
            playlistsLoadID = loadID
            playlistsLoadTask = task
            isLoadingPlaylists = true
            errorMessage = nil
        }

        defer {
            if playlistsLoadID == loadID {
                playlistsLoadID = nil
                playlistsLoadTask = nil
                isLoadingPlaylists = false
            }
        }

        do {
            playlists = try await task.value
            playlistsLoadedAt = .now
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = L("加载分组失败")
        }
    }

    /// 统计供学习页和生词库状态区域使用，分组管理页不依赖它。
    func loadStats() async {
        let loadID: UUID
        let task: Task<VocabularyStats, Error>
        if let existingTask = statsLoadTask, let existingID = statsLoadID {
            loadID = existingID
            task = existingTask
        } else {
            loadID = UUID()
            task = Task { try await WordService.stats() }
            statsLoadID = loadID
            statsLoadTask = task
            isLoadingStats = true
        }

        defer {
            if statsLoadID == loadID {
                statsLoadID = nil
                statsLoadTask = nil
                isLoadingStats = false
            }
        }

        do {
            stats = try await task.value
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = L("加载分组统计失败")
        }
    }

    /// 某个分组有多少词，用于面板每行右侧的计数。
    func count(for selection: PlaylistSelection) -> Int {
        switch selection {
        case .dueReview: return stats.dueCount
        case .status("new"): return stats.newCount
        case .status("fuzzy"): return stats.fuzzyCount
        case .status("known"): return stats.knownCount
        case .status: return 0
        case .custom(let id): return playlists.first { $0.id == id }?.wordCount ?? 0
        }
    }

    func name(for selection: PlaylistSelection) -> String {
        selection.displayName(playlists: playlists)
    }

    @discardableResult
    func createPlaylist(name: String, wordIDs: [String]) async -> Playlist? {
        errorMessage = nil
        do {
            let playlist = try await WordService.createPlaylist(name: name, wordIDs: wordIDs)
            store(playlist)
            return playlist
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = L("创建分组失败")
        }
        return nil
    }

    @discardableResult
    func updatePlaylist(id: String, name: String? = nil, wordIDs: [String]? = nil) async -> Bool {
        errorMessage = nil
        do {
            let playlist = try await WordService.updatePlaylist(id: id, name: name, wordIDs: wordIDs)
            store(playlist)
            return true
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = L("保存分组失败")
        }
        return false
    }

    @discardableResult
    func addWords(to playlistID: String, wordIDs: [String]) async -> Bool {
        errorMessage = nil
        do {
            let playlist = try await WordService.addWordsToPlaylist(id: playlistID, wordIDs: wordIDs)
            store(playlist)
            return true
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = L("加入分组失败")
        }
        return false
    }

    @discardableResult
    func deletePlaylist(id: String) async -> Bool {
        // 立刻标记「正在删」——行 UI 拿到这个状态立刻降透明 + 禁用点按，用户
        // 看到「真在删」而不是以为还没动手。同时避免用户在请求飞行期间重复点。
        errorMessage = nil
        deletingPlaylistID = id
        defer {
            // 无论成功失败都要恢复这一行的可操作状态。
            deletingPlaylistID = nil
        }
        do {
            try await WordService.deletePlaylist(id: id)
            playlists.removeAll { $0.id == id }
            playlistsLoadedAt = .now
            return true
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = L("删除分组失败")
        }
        return false
    }

    private func store(_ playlist: Playlist) {
        if let index = playlists.firstIndex(where: { $0.id == playlist.id }) {
            playlists[index] = playlist
        } else {
            playlists.insert(playlist, at: 0)
        }
        playlistsLoadedAt = .now
    }
}
