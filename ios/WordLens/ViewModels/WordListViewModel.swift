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

    @Published var isSelecting = false
    @Published var selectedIDs: Set<String> = []

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

    func toggleSelecting() {
        isSelecting.toggle()
        if !isSelecting { selectedIDs.removeAll() }
    }

    func toggleSelection(_ word: VocabularyWord) {
        if selectedIDs.contains(word.id) {
            selectedIDs.remove(word.id)
        } else {
            selectedIDs.insert(word.id)
        }
    }

    /// 后端没有批量删除接口，逐个调用单删；个人生词库量级不大，串行足够，
    /// 也顺带避免并发请求打满限流。任何一个失败都不影响其它词继续删。
    func deleteSelected() async {
        let ids = selectedIDs
        for id in ids {
            try? await WordService.deleteWord(id: id)
        }
        allWords.removeAll { ids.contains($0.id) }
        selectedIDs.removeAll()
        isSelecting = false
    }
}
