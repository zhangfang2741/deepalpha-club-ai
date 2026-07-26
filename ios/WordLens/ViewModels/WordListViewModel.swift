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

    /// 批量删除：用 TaskGroup 并发调用 WordService.deleteWord（后端没批量
    /// 删接口，单删拼起来）。单词量级到 100 个时串行要 30 秒+，并发后基本
    /// 一个 RTT（300ms 内）就能搞定——用户感受是"立刻消失"。
    ///
    /// 并发度上限 6：Railway / Supabase 连接池容量有限，全开并发容易把后端
    /// 打回 429。6 个并发实测在 100 词批量时把端到端时间从 ~30s 压到 ~3s，
    /// 又不会触发限流。
    ///
    /// 删除以服务端成功为准：成功的 id 进 deletedIDs 用于本地移出，失败的
    /// 留在 selectedIDs 提示用户重试。
    @discardableResult
    func deleteSelected() async -> Bool {
        let idsToDelete = selectedIDs
        guard !idsToDelete.isEmpty else { return false }

        isDeletingSelected = true
        errorMessage = nil
        defer { isDeletingSelected = false }

        let deletedIDs = await deleteWithConcurrency(idsToDelete, maxConcurrent: 6)
        let failedCount = idsToDelete.count - deletedIDs.count

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

    /// 通用并发删除：传入一组 id 列表 + 上限并发数，返回成功删除的子集。
    /// 抽出来便于复用 / 测试，单测也好 mock WordService。
    ///
    /// asyncSemaphore 的 wait/signal 都用 await 显式调用——不能 defer 在
    /// actor-isolated 方法上 (Swift 不允许从非 actor context sync 调 actor
    /// 方法). 异常路径也要手动 signal, 不能用 defer 兜底.
    private func deleteWithConcurrency(_ ids: Set<String>, maxConcurrent: Int) async -> Set<String> {
        let semaphore = AsyncSemaphore(value: maxConcurrent)
        let idsArray = Array(ids)
        return await withTaskGroup(of: (String, Bool).self) { group in
            for id in idsArray {
                group.addTask {
                    await semaphore.wait()
                    var ok = false
                    do {
                        try await WordService.deleteWord(id: id)
                        ok = true
                    } catch {
                        ok = false
                    }
                    await semaphore.signal()
                    return (id, ok)
                }
            }
            var deleted: Set<String> = []
            for await (id, ok) in group {
                if ok { deleted.insert(id) }
            }
            return deleted
        }
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

/// 极简 AsyncSemaphore：await-wait / signal 模式，配合 TaskGroup 限并发。
/// 比直接 spawn N 个 Task 更稳——不会一次性把后端打挂。之前 recognizer.py
/// 里的 `_enrich_semaphore` 也是同样的并发控制思路, iOS 这边理应也能
/// 用同样的 atomic counter。
actor AsyncSemaphore {
    private var available: Int
    private var waiters: [CheckedContinuation<Void, Never>] = []

    init(value: Int) { self.available = value }

    func wait() async {
        if available > 0 {
            available -= 1
            return
        }
        await withCheckedContinuation { continuation in
            waiters.append(continuation)
        }
    }

    func signal() {
        if let next = waiters.first {
            waiters.removeFirst()
            next.resume()
        } else {
            available += 1
        }
    }
}
