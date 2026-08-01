// ViewModels/WordListViewModel.swift
import Foundation
import SwiftUI

@MainActor
final class WordListViewModel: ObservableObject {
    private static let deleteBatchSize = 5000

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
        guard filterPlaylistID != nil else { return statusFiltered }
        return statusFiltered.filter { word in
            // 第一次按需加载这个分组的词集，后续命中缓存
            playlistWords.contains(word.id)
        }
    }

    /// 选中分组的词 id 集合。需要按需加载，附在 allWords 上更省心。
    @Published private(set) var playlistWords: Set<String> = []
    @Published private(set) var isLoadingPlaylist = false

    /// 外部让出 chips 的便捷通道：清掉筛选 ID + 缓存。状态磁贴互斥逻辑
    /// 调它，避免外部直接 set 一个 private(set) 的属性。
    func clearPlaylistFilter() {
        filterPlaylistID = nil
        playlistWords = []
    }

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

    /// 批量删除：每 5000 个 ID 发一次请求，由服务端在单个事务中集合删除。
    /// 例如 3220 个词只需 1 次请求，不再创建 3220 个 Task 和 HTTP 连接。
    ///
    /// 删除以服务端成功为准：成功的 id 进 deletedIDs 用于本地移出，失败的
    /// 留在 selectedIDs 提示用户重试。
    ///
    /// 进度展示：进入时锁定 `total`，过程中每完成一个 word 累加
    /// `completed`，UI 显示 "正在删除 X / Y"。完成时 `deletionProgress`
    /// 置 nil。
    @discardableResult
    func deleteSelected(
        onProgress: @MainActor (Int, Int) -> Void = { _, _ in }
    ) async -> Bool {
        let idsToDelete = selectedIDs
        guard !idsToDelete.isEmpty else { return false }

        isDeletingSelected = true
        deletionProgress = (completed: 0, total: idsToDelete.count)
        errorMessage = nil
        defer {
            isDeletingSelected = false
            deletionProgress = nil
        }

        let idArray = Array(idsToDelete)
        var succeededIDs: Set<String> = []
        var completed = 0

        for start in stride(from: 0, to: idArray.count, by: Self.deleteBatchSize) {
            if Task.isCancelled { break }
            let end = min(start + Self.deleteBatchSize, idArray.count)
            let batch = Array(idArray[start..<end])
            do {
                _ = try await WordService.deleteWordsBatch(ids: batch)
                // 接口是幂等的：请求成功即代表这些 ID 在服务端已经不存在，包含
                // 被另一台设备提前删除的条目，因此整批都可以从本地安全移除。
                succeededIDs.formUnion(batch)
            } catch {
                // 单批失败不阻断后续批次；失败 ID 保持选中，用户可以直接重试。
            }
            completed += batch.count
            deletionProgress = (completed: completed, total: idsToDelete.count)
            onProgress(completed, idsToDelete.count)
        }
        let failedCount = idsToDelete.count - succeededIDs.count

        if !succeededIDs.isEmpty {
            if succeededIDs.count <= 100 {
                withAnimation(.easeInOut(duration: 0.35)) {
                    allWords.removeAll { succeededIDs.contains($0.id) }
                }
            } else {
                // 数千行同时执行退场动画会让 SwiftUI 主线程再次卡住，大批量删除
                // 直接更新数据；进度条已经提供了明确的操作反馈。
                allWords.removeAll { succeededIDs.contains($0.id) }
            }
        }

        selectedIDs.subtract(succeededIDs)
        if failedCount > 0 {
            errorMessage = "有 \(failedCount) 个单词删除失败，请稍后重试"
        }

        if selectedIDs.isEmpty {
            isSelecting = false
        }
        return !succeededIDs.isEmpty
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
