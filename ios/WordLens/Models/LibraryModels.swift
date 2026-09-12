// Models/LibraryModels.swift
import Foundation

/// 内置词库单本，对应后端 LibraryBookSchema。
struct VocabularyLibraryBook: Codable, Identifiable, Hashable {
    let id: String
    let title: String
    let wordCount: Int

    enum CodingKeys: String, CodingKey {
        case id, title
        case wordCount = "word_count"
    }
}

/// 内置词库分组（如「四六级」「出国留学」），对应后端 LibraryGroupSchema。
struct VocabularyLibraryGroup: Codable, Identifiable, Hashable {
    let key: String
    let title: String
    let books: [VocabularyLibraryBook]

    var id: String { key }
}

/// 对应后端 LibraryListResponse。
struct LibraryListResponse: Codable {
    let groups: [VocabularyLibraryGroup]
}

/// 导入内置词库结果，对应后端 LibraryImportResponse。
///
/// imported 为真正并入生词库的新词数；skipped 为因已存在被跳过的词数（其记忆
/// 进度保留不变）。playlist* 描述导入时按词库名自动建/刷新的歌单——用户可在
/// 首页切到它单独复习这本、单独查看进度。
struct LibraryImportResult: Codable {
    let imported: Int
    let skipped: Int
    let playlistName: String
    let playlistWordCount: Int

    enum CodingKeys: String, CodingKey {
        case imported, skipped
        case playlistName = "playlist_name"
        case playlistWordCount = "playlist_word_count"
    }
}
