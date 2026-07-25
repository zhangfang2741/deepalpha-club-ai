// ViewModels/WordListViewModel.swift
import Foundation

@MainActor
final class WordListViewModel: ObservableObject {
    /// 服务端只按 searchQuery 过滤，不按 status 过滤——status 过滤在客户端做（见
    /// `words`），这样切换"不认识/模糊/认识"是纯本地筛选、不用等网络请求，而且
    /// 统计数字（每个状态各多少个）能一直按全量数据算，不会被当前选中的筛选
    /// 状态带偏（之前 status 是服务端过滤时，切到"模糊"后"不认识"的数字会被
    /// 误显示成 0，因为拉回来的列表本来就只剩"模糊"了）。
    @Published var allWords: [VocabularyWord] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var filterStatus: String?
    @Published var searchQuery = ""

    var words: [VocabularyWord] {
        guard let filterStatus else { return allWords }
        return allWords.filter { $0.status == filterStatus }
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            allWords = try await WordService.listWords(query: searchQuery.isEmpty ? nil : searchQuery)
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "加载生词库失败"
        }
    }

    func delete(_ word: VocabularyWord) async {
        do {
            try await WordService.deleteWord(id: word.id)
            allWords.removeAll { $0.id == word.id }
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "删除失败"
        }
    }
}
