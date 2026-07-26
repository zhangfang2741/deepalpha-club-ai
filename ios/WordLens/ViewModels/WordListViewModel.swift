// ViewModels/WordListViewModel.swift
import Foundation
import SwiftUI

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
    @Published var isDeletingSelected = false

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

    @discardableResult
    func delete(_ word: VocabularyWord) async -> Bool {
        do {
            try await WordService.deleteWord(id: word.id)
            allWords.removeAll { $0.id == word.id }
            return true
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "删除失败"
        }
        return false
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
    /// 也顺带避免并发请求打满限流。删除以服务端成功为准，成功删掉哪些词，
    /// 本地列表就移除哪些词；失败项留在选择态里并提示用户重试。
    @discardableResult
    func deleteSelected() async -> Bool {
        let idsToDelete = selectedIDs
        guard !idsToDelete.isEmpty else { return false }

        isDeletingSelected = true
        errorMessage = nil
        defer { isDeletingSelected = false }

        var deletedIDs: Set<String> = []
        var failedCount = 0
        for id in idsToDelete {
            do {
                try await WordService.deleteWord(id: id)
                deletedIDs.insert(id)
            } catch {
                failedCount += 1
            }
        }

        if !deletedIDs.isEmpty {
            withAnimation(.easeInOut(duration: 0.35)) {
                allWords.removeAll { deletedIDs.contains($0.id) }
            }
        }

        selectedIDs.subtract(deletedIDs)
        if failedCount > 0 {
            errorMessage = "有 \(failedCount) 个单词删除失败，请稍后重试"
        }

        if selectedIDs.isEmpty {
            isSelecting = false
        }
        return !deletedIDs.isEmpty
    }

    /// 三态全选：未全选 → 全选；当前全选 → 全不选；部分选 → 选完所有可见的。
    /// 选的是当前 `words`（已应用 status 筛选和搜索），不是 allWords——避免
    /// "点全选后切到筛选状态发现没选"的违和感。
    var isAllSelected: Bool {
        !words.isEmpty && selectedIDs.count == words.count
    }

    var isPartiallySelected: Bool {
        !selectedIDs.isEmpty && !isAllSelected
    }

    func toggleSelectAll() {
        if isAllSelected {
            selectedIDs.removeAll()
        } else {
            selectedIDs = Set(words.map(\.id))
        }
    }

    /// 详情页提交评分后，后端会返回更新后的词（含新 status / nextReviewAt 等），
    /// 用它原地替换 allWords 里对应那一行——保证返回列表时筛选数字、状态点都
    /// 跟实际一致（点"认识"再回来，状态点应从"不认识"变成"认识"）。
    func updateWord(_ updated: VocabularyWord) {
        if let idx = allWords.firstIndex(where: { $0.id == updated.id }) {
            allWords[idx] = updated
        }
    }
}
