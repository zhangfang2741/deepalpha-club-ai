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
