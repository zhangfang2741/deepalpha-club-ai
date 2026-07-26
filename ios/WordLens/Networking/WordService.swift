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
}
