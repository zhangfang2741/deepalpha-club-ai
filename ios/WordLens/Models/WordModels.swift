// Models/WordModels.swift
import Foundation

/// 拍照识别出的候选词，对应后端 RecognizedWordSchema。
struct RecognizedWord: Codable, Identifiable {
    let word: String
    let phoneticIpa: String
    let partOfSpeech: String
    let definitionZh: String
    let etymology: String
    let exampleSentence: String
    let alreadyInLibrary: Bool

    var id: String { word }

    enum CodingKeys: String, CodingKey {
        case word
        case phoneticIpa = "phonetic_ipa"
        case partOfSpeech = "part_of_speech"
        case definitionZh = "definition_zh"
        case etymology
        case exampleSentence = "example_sentence"
        case alreadyInLibrary = "already_in_library"
    }
}

/// 对应后端 RecognizeResponse。
struct RecognizeResponse: Codable {
    let candidates: [RecognizedWord]
}

/// 生词库条目，对应后端 VocabularyWordResponse。
/// Hashable：WordListView 用 .navigationDestination(item:) 代替 NavigationLink
/// 去掉行右侧的箭头指示器，item-based 导航要求绑定的值类型是 Hashable。
struct VocabularyWord: Codable, Identifiable, Hashable {
    let id: String
    let word: String
    let phoneticIpa: String
    let partOfSpeech: String
    let definitionZh: String
    let etymology: String
    let exampleSentence: String
    let status: String
    let repetitionCount: Int
    let easinessFactor: Double
    let intervalDays: Int
    let nextReviewAt: String
    let lastReviewedAt: String?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, word, status
        case phoneticIpa = "phonetic_ipa"
        case partOfSpeech = "part_of_speech"
        case definitionZh = "definition_zh"
        case etymology
        case exampleSentence = "example_sentence"
        case repetitionCount = "repetition_count"
        case easinessFactor = "easiness_factor"
        case intervalDays = "interval_days"
        case nextReviewAt = "next_review_at"
        case lastReviewedAt = "last_reviewed_at"
        case createdAt = "created_at"
    }
}

/// 提交给 /words/batch 的单个词，对应后端 VocabularyWordCreate。
struct VocabularyWordCreate: Codable {
    let word: String
    let phoneticIpa: String
    let partOfSpeech: String
    let definitionZh: String
    let etymology: String
    let exampleSentence: String

    enum CodingKeys: String, CodingKey {
        case word
        case phoneticIpa = "phonetic_ipa"
        case partOfSpeech = "part_of_speech"
        case definitionZh = "definition_zh"
        case etymology
        case exampleSentence = "example_sentence"
    }
}

/// 对应后端 WordsBatchCreateResponse。
struct WordsBatchCreateResponse: Codable {
    let created: [VocabularyWord]
    let skippedExisting: [String]

    enum CodingKeys: String, CodingKey {
        case created
        case skippedExisting = "skipped_existing"
    }
}

/// 对应后端 VocabularyWordListResponse。
struct VocabularyWordListResponse: Codable {
    let words: [VocabularyWord]
}

/// 对应后端 ReviewQueueResponse。
struct ReviewQueueResponse: Codable {
    let words: [VocabularyWord]
}

/// 对应后端 ReviewSubmitResponse。
struct ReviewSubmitResponse: Codable {
    let word: VocabularyWord
}

/// 三档复习评分，对应后端 rating 字段（0/1/2）。
enum ReviewRating: Int, Equatable {
    case unknown = 0
    case fuzzy = 1
    case known = 2
}
