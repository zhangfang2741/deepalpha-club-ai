// ViewModels/PlaylistViewModel.swift
import Foundation

/// 播放列表面板的状态：各分组的词数 + 自定义歌单列表 + 歌单增删改。
///
/// 只管「有哪些组、各有多少词」，不碰当前播放队列本身——那是 ReviewViewModel
/// 的事。两者通过一个 PlaylistSelection 值对接。
@MainActor
final class PlaylistViewModel: ObservableObject {
    @Published private(set) var stats: VocabularyStats = .empty
    @Published private(set) var playlists: [Playlist] = []
    @Published private(set) var isLoading = false
    @Published var errorMessage: String?

    /// 当前正在删除的分组 ID——行内 UI 拿来降透明 + 禁用按钮，避免用户在
    /// 删除请求飞行期间又去操作这一行。`load()` 完成后会自动清掉。
    @Published private(set) var deletingPlaylistID: String?


    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            // 两个请求互不依赖，并发拿，面板打开就不用等两个 RTT。
            async let statsTask = WordService.stats()
            async let playlistsTask = WordService.listPlaylists()
            stats = try await statsTask
            playlists = try await playlistsTask
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "加载播放列表失败"
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
            await load()
            return playlist
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "创建分组失败"
        }
        return nil
    }

    @discardableResult
    func updatePlaylist(id: String, name: String? = nil, wordIDs: [String]? = nil) async -> Bool {
        errorMessage = nil
        do {
            _ = try await WordService.updatePlaylist(id: id, name: name, wordIDs: wordIDs)
            await load()
            return true
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "保存分组失败"
        }
        return false
    }

    @discardableResult
    func addWords(to playlistID: String, wordIDs: [String]) async -> Bool {
        errorMessage = nil
        do {
            _ = try await WordService.addWordsToPlaylist(id: playlistID, wordIDs: wordIDs)
            await load()
            return true
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "加入分组失败"
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
            // 无论成功失败都要清掉，load() 之前就清也是对的（成功后 load 会重置
            // 整个 playlists；失败后这一行依然存在，需要恢复可点状态）。
            deletingPlaylistID = nil
        }
        do {
            try await WordService.deletePlaylist(id: id)
            await load()
            return true
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "删除分组失败"
        }
        return false
    }
}
