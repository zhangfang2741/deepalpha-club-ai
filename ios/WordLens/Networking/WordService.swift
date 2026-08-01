// Networking/WordService.swift
import Foundation

/// 拍照识别 + 生词库 + 复习，对应后端 /vocabulary/{recognize,words,review}。
enum WordService {
    /// 拍照识别：上传图片，并把本地 Apple Vision OCR 抠出的候选词一并带上，
    /// 让后端视觉 LLM 综合看图识别与 OCR 结果取并集。ocrWords 为空则纯看图识别。
    ///
    /// onPartial：识别还没跑完时，后端每推一批已识别出的候选词就回调一次，
    /// 用来在 UI 上展示实时进度（而不是等 5~15 秒才看到任何结果）。
    static func recognize(
        imageData: Data,
        ocrWords: [String] = [],
        onPartial: (@Sendable (RecognizeResponse) -> Void)? = nil
    ) async throws -> RecognizeResponse {
        let textFields = ocrWords.map { (name: "ocr_words", value: $0) }
        return try await APIClient.shared.postMultipartImage(
            "/recognize/stream",
            imageData: imageData,
            textFields: textFields,
            onPartial: onPartial
        )
    }

    static func addWordsBatch(_ words: [VocabularyWordCreate]) async throws -> WordsBatchCreateResponse {
        struct Body: Encodable { let words: [VocabularyWordCreate] }
        return try await APIClient.shared.postJSON("/words/batch", body: Body(words: words))
    }

    static func listWords(status: String? = nil, query: String? = nil) async throws -> [VocabularyWord] {
        var params: [String: String] = [:]
        if let status { params["status"] = status }
        if let query, !query.isEmpty { params["q"] = query }
        let resp: VocabularyWordListResponse = try await APIClient.shared.get("/words", query: params)
        return resp.words
    }

    static func wordDetail(id: String) async throws -> VocabularyWord {
        try await APIClient.shared.get("/words/\(id)")
    }

    static func deleteWord(id: String) async throws {
        struct DeleteResponse: Decodable { let deleted: Bool }
        let _: DeleteResponse = try await APIClient.shared.delete("/words/\(id)")
    }

    static func reviewQueue() async throws -> [VocabularyWord] {
        let resp: ReviewQueueResponse = try await APIClient.shared.get("/review/queue")
        return resp.words
    }

    static func submitReview(wordId: String, rating: ReviewRating) async throws -> VocabularyWord {
        struct Body: Encodable { let rating: Int }
        let resp: ReviewSubmitResponse = try await APIClient.shared.postJSON(
            "/words/\(wordId)/review", body: Body(rating: rating.rawValue)
        )
        return resp.word
    }

    // MARK: - 播放列表（歌单）

    static func stats() async throws -> VocabularyStats {
        try await APIClient.shared.get("/stats")
    }

    static func listPlaylists() async throws -> [Playlist] {
        let resp: PlaylistListResponse = try await APIClient.shared.get("/playlists")
        return resp.playlists
    }

    static func createPlaylist(name: String, wordIDs: [String]) async throws -> Playlist {
        struct Body: Encodable {
            let name: String
            let wordIds: [String]
            enum CodingKeys: String, CodingKey {
                case name
                case wordIds = "word_ids"
            }
        }
        return try await APIClient.shared.postJSON("/playlists", body: Body(name: name, wordIds: wordIDs))
    }

    /// 改名 / 整体替换词表。两个参数都可选，传 nil 表示这一项不动（对应后端
    /// PATCH 的语义），所以 Body 里用 `encodeIfPresent` 而不是默认编码——
    /// 显式编码出 `null` 会被后端当成「传了 None」，语义一样，但省掉字段更干净。
    static func updatePlaylist(id: String, name: String? = nil, wordIDs: [String]? = nil) async throws -> Playlist {
        struct Body: Encodable {
            let name: String?
            let wordIds: [String]?
            enum CodingKeys: String, CodingKey {
                case name
                case wordIds = "word_ids"
            }
            func encode(to encoder: Encoder) throws {
                var container = encoder.container(keyedBy: CodingKeys.self)
                try container.encodeIfPresent(name, forKey: .name)
                try container.encodeIfPresent(wordIds, forKey: .wordIds)
            }
        }
        return try await APIClient.shared.patchJSON("/playlists/\(id)", body: Body(name: name, wordIds: wordIDs))
    }

    /// 把一批词并入歌单末尾（生词库多选「加入歌单」用）。走独立接口而不是
    /// updatePlaylist：那边是整体替换，客户端得先把歌单现有词表拉下来再拼。
    static func addWordsToPlaylist(id: String, wordIDs: [String]) async throws -> Playlist {
        struct Body: Encodable {
            let wordIds: [String]
            enum CodingKeys: String, CodingKey { case wordIds = "word_ids" }
        }
        return try await APIClient.shared.postJSON("/playlists/\(id)/words", body: Body(wordIds: wordIDs))
    }

    static func deletePlaylist(id: String) async throws {
        struct DeleteResponse: Decodable { let deleted: Bool }
        let _: DeleteResponse = try await APIClient.shared.delete("/playlists/\(id)")
    }

    static func playlistWords(id: String) async throws -> [VocabularyWord] {
        let resp: VocabularyWordListResponse = try await APIClient.shared.get("/playlists/\(id)/words")
        return resp.words
    }
}
