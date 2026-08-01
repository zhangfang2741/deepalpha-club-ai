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

    /// 例句字段由识别服务按「英文例句 + 中文翻译」生成。自动播放只朗读第一个汉字
    /// 之前的英文部分，避免把翻译也交给英语音色念出来；只有英文、没有翻译的旧数据
    /// 同样可以直接使用。
    var englishExampleSentence: String? {
        let trimmed = exampleSentence.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }

        let englishSlice: Substring
        if let scalarIndex = trimmed.unicodeScalars.firstIndex(where: Self.isCJK),
           let stringIndex = scalarIndex.samePosition(in: trimmed) {
            englishSlice = trimmed[..<stringIndex]
        } else {
            englishSlice = trimmed[...]
        }

        // 中文翻译常用括号、破折号或斜杠隔开，把这些残留分隔符从英文结尾去掉。
        let separators = CharacterSet.whitespacesAndNewlines.union(
            CharacterSet(charactersIn: "（([【—–-:：/|")
        )
        let english = String(englishSlice).trimmingCharacters(in: separators)
        guard english.rangeOfCharacter(from: .letters) != nil else { return nil }
        return english
    }

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

    private static func isCJK(_ scalar: UnicodeScalar) -> Bool {
        switch scalar.value {
        case 0x3400...0x4DBF, 0x4E00...0x9FFF, 0xF900...0xFAFF,
             0x20000...0x2FA1F:
            return true
        default:
            return false
        }
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
