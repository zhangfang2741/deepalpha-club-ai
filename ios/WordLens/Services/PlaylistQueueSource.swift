// Services/PlaylistQueueSource.swift
import Foundation

/// 把「当前选中的播放列表」翻译成一队实际的单词。
///
/// 单独抽出来是为了让 ReviewViewModel 不用关心每种分组各走哪个接口——它只管
/// 「给我这一组的词」，队列来源以后要加（比如「最近加入的 50 个」）也只动这里。
enum PlaylistQueueSource {
    static func load(_ selection: PlaylistSelection) async throws -> [VocabularyWord] {
        switch selection {
        case .dueReview:
            return try await WordService.reviewQueue()
        case .status(let status):
            // 后端 /words?status= 已支持按状态筛选，不用新增端点。
            return try await WordService.listWords(status: status)
        case .custom(let id):
            // 歌单词表由后端按 position 排好，就是用户在编辑页排的播放顺序。
            return try await WordService.playlistWords(id: id)
        }
    }
}
