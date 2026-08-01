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
    /// 删除进度：`completed` 是已经完成 (成功或失败) 的数量，`total` 是这一批
    /// 开始时的总数。在 deleteSelected 进入时锁定 total, 过程中持续更新
    /// completed, UI 显示 "正在删除 20 / 104". 完成时置 nil.
    @Published var deletionProgress: (completed: Int, total: Int)?

    /// 自定义分组筛选：只在生词库查到的词里筛选，所以状态保持 "无分组筛选" 即可。
    /// nil 表示不过滤，显示全部。
    @Published var filterPlaylistID: String?

    var words: [VocabularyWord] {
        let statusFiltered = allWords.filter { word in
            guard let filterStatus else { return true }
            return word.status == filterStatus
        }
        guard let filterPlaylistID else { return statusFiltered }
        return statusFiltered.filter { word in
            // 第一次按需加载这个分组的词集，后续命中缓存
            playlistWords.contains(word.id)
        }
    }

    /// 选中分组的词 id 集合。需要按需加载，附在 allWords 上更省心。
    @Published private(set) var playlistWords: Set<String> = []
    @Published private(set) var isLoadingPlaylist = false

    /// 加载某分组对应的词表 id 集合，结果缓存到 `playlistWords`。
    /// 切换分组筛选时调用；筛选回 nil 时清空缓存。
    ///
    /// **关键**：必须先同步清空 `playlistWords`，再去网络拉新值。中间那一帧如果
    /// 拿着旧分组的 id 集合去判断新分组的过滤，新老分组的交集几乎肯定是空，
    /// 列表就会闪一下"啥都没有"。UI 层面没法察觉是数据还没就位，看着像坏了。
    func loadPlaylistWords(id: String?) async {
        guard let id else {
            playlistWords = []
            return
        }
        // 立刻清掉旧集合：这一刻筛选会先把所有词挡掉，等新集合加载回来再放行。
        // 跟加载到一半的"老 id 误判新分组"相比，这种"先空再满"更接近真实进度。
        playlistWords = []
        isLoadingPlaylist = true
        defer { isLoadingPlaylist = false }
        do {
            let words = try await WordService.playlistWords(id: id)
            playlistWords = Set(words.map(\.id))
        } catch {
            playlistWords = []
        }
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
    ///
    /// 进度展示：进入时锁定 `total`，过程中每完成一个 word 累加
    /// `completed`，UI 显示 "正在删除 X / Y"。完成时 `deletionProgress`
    /// 置 nil。
    @discardableResult
    func deleteSelected() async -> Bool {
        let idsToDelete = selectedIDs
        guard !idsToDelete.isEmpty else { return false }

        isDeletingSelected = true
        deletionProgress = (completed: 0, total: idsToDelete.count)
        errorMessage = nil
        defer {
            isDeletingSelected = false
            deletionProgress = nil
        }

        let deletedIDs = await deleteWithConcurrency(
            idsToDelete,
            maxConcurrent: 6,
            total: idsToDelete.count
        ) { completed, _ in
            // 任务完成回调: 推进 UI 进度。@MainActor 的 ViewModel 直接更新
            // @Published, UI 立刻收到.
            self.deletionProgress = (completed: completed, total: idsToDelete.count)
        }
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

    /// 通用并发删除：传入一组 id 列表 + 上限并发数 + 进度回调, 返回成功删除的
    /// 子集. onProgress 在每个 word 完成时调用 (成功或失败都算一次完成),
    /// 第一个参数是已完成数量, 第二个是总数 —— 调用方用它更新 UI.
    ///
    /// asyncSemaphore 的 wait/signal 都用 await 显式调用——不能 defer 在
    /// actor-isolated 方法上 (Swift 不允许从非 actor context sync 调 actor
    /// 方法). 异常路径也要手动 signal, 不能用 defer 兜底.
    private func deleteWithConcurrency(
        _ ids: Set<String>,
        maxConcurrent: Int,
        total: Int,
        onProgress: @MainActor (Int, Int) -> Void
    ) async -> Set<String> {
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
            var completed = 0
            for await (id, ok) in group {
                completed += 1
                if ok { deleted.insert(id) }
                // onProgress 是 @MainActor — 调用点在 await 上下文, 这里
                // TaskGroup 的 outer await 自动在 await 时让 actor 切换
                // 满足 Swift 6 严格隔离规则.
                await onProgress(completed, total)
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
