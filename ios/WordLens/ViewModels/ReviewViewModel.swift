// ViewModels/ReviewViewModel.swift
import Foundation

@MainActor
final class ReviewViewModel: ObservableObject {
    @Published var queue: [VocabularyWord] = []
    @Published var currentIndex = 0
    @Published var isFlipped = false
    @Published var isLoading = false
    @Published var isSubmitting = false
    @Published var errorMessage: String?
    @Published var totalCount = 0

    /// TabView 切走再切回来会让这个 tab 重新走一遍 appear，.task 也会跟着重新
    /// 触发；如果每次都无条件调 loadQueue()（会把 currentIndex 清零），用户刚
    /// 翻到第 5 个词，切一下 tab 回来就被打回第一个。用这个标记让 .task 只在
    /// 本次进程里真正加载一次，后续切 tab 回来不再重置进度；下拉刷新走的还是
    /// loadQueue()，仍然是一次完整重置，语义上也说得通（用户主动要求刷新）。
    private var hasLoadedOnce = false

    var currentWord: VocabularyWord? {
        guard currentIndex < queue.count else { return nil }
        return queue[currentIndex]
    }

    var isFinished: Bool { !queue.isEmpty && currentIndex >= queue.count }

    /// 「上一个/下一个」只是浏览，不提交评分——跟 submit() 的自动前进是两码事。
    /// canGoNext 卡在 queue.count - 1，不让浏览走到"今日复习完成"那一屏，
    /// 那个只应该由实际提交评分触发。
    var canGoPrevious: Bool { currentIndex > 0 }
    var canGoNext: Bool { currentIndex < queue.count - 1 }

    func goToPrevious() {
        guard canGoPrevious else { return }
        currentIndex -= 1
        isFlipped = false
    }

    func goToNext() {
        guard canGoNext else { return }
        currentIndex += 1
        isFlipped = false
    }

    /// 给 .task 用：本次进程只真正加载一次，切 tab 回来时是空操作，不打断
    /// 用户当前翻到哪个词的进度。
    func loadQueueIfNeeded() async {
        guard !hasLoadedOnce else { return }
        hasLoadedOnce = true
        await loadQueue()
    }

    func loadQueue() async {
        isLoading = true
        errorMessage = nil
        currentIndex = 0
        isFlipped = false
        defer { isLoading = false }
        do {
            queue = try await WordService.reviewQueue()
            totalCount = queue.count
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "加载复习队列失败"
        }
    }

    func flip() {
        isFlipped.toggle()
    }

    func submit(_ rating: ReviewRating) async {
        guard let word = currentWord else { return }
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            _ = try await WordService.submitReview(wordId: word.id, rating: rating)
            currentIndex += 1
            isFlipped = false
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "提交复习结果失败"
        }
    }
}
