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

    /// 预览某个分组的词表：用户在正在播放页点了别的分组标签，先把那一组的词
    /// 拉出来给他看，**但不动当前正在播的队列**——真正切过去要他再点一次
    /// 「切换到这一组」。这样点标签只是"翻着看看"，不会误操作把正在背的
    /// 队列冲掉。
    @Published private(set) var previewWords: [VocabularyWord] = []
    @Published private(set) var isLoadingPreview = false
    /// 当前 previewWords 属于哪个分组，避免请求乱序时把上一组的结果显示上去。
    private var previewToken: PlaylistSelection?

    func loadPreview(_ selection: PlaylistSelection) async {
        previewToken = selection
        isLoadingPreview = true
        previewWords = []
        defer { isLoadingPreview = false }
        let words = (try? await PlaylistQueueSource.load(selection)) ?? []
        // 请求回来时用户可能已经点到别的分组了，只认最后一次的结果。
        guard previewToken == selection else { return }
        previewWords = words
    }

    func clearPreview() {
        previewToken = nil
        previewWords = []
    }

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
        errorMessage = nil
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
