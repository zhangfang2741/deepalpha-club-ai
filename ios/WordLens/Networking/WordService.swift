// Networking/WordService.swift
import Foundation

/// 拍照识别 + 生词库 + 复习，对应后端 /vocabulary/{recognize,words,review}。
enum WordService {
    static func recognize(imageData: Data) async throws -> RecognizeResponse {
        try await APIClient.shared.postMultipartImage("/recognize", imageData: imageData)
    }

    /// 混合识别：把 iOS 端 Apple Vision OCR 抠出的候选词交后端补音标/释义。
    static func enrich(words: [String]) async throws -> RecognizeResponse {
        struct Body: Encodable { let words: [String] }
        return try await APIClient.shared.postJSON("/enrich", body: Body(words: words))
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
}
