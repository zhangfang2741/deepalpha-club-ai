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
    ///
    /// 视觉上做了"先缓冲淡出，再真正删"的拆开：
    /// 1. 先把要删的 id 从 allWords 里移除，触发 List 的 transition 动画（行滑
    ///    出 + 淡出，0.35s），让用户看到删除动作在发生，不会有"按完突然少一片"
    ///    的卡死感；
    /// 2. 真正的 DELETE 请求用 detached Task 在后台跑，删完后该词的 isDeleting
    ///    标记也就无意义了。
    /// 选过的 id 必须保留到动画结束再清——如果立刻清，selectedIDs 会跟列表脱节
    /// 几帧，UI 会闪烁。
    func deleteSelected() async {
        let idsToDelete = selectedIDs
        guard !idsToDelete.isEmpty else { return }

        withAnimation(.easeInOut(duration: 0.35)) {
            allWords.removeAll { idsToDelete.contains($0.id) }
        }
        // 等动画播完再清选中态——否则 toolbar 上的"删除所选 (N)"会瞬间从 N 跳 0，
        // 用户感知不到动画正在进行。
        try? await Task.sleep(for: .milliseconds(360))

        Task.detached(priority: .userInitiated) {
            for id in idsToDelete {
                try? await WordService.deleteWord(id: id)
            }
        }

        selectedIDs.removeAll()
        isSelecting = false
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
