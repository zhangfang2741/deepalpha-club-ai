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

    /// 自动播放状态机：开启后从当前词开始，每个词朗读 3 遍（遍间 0.6s 停顿），
    /// 切下一个词前等 2s。手动打断（点喇叭 / 切词 / 评分）会自动退出。
    @Published var isAutoplay = false
    /// 自动播放期间给 UI 显示"X / Y"进度，比 currentIndex 更直观。
    @Published private(set) var autoplayWordIndex = 0

    /// 自动播放启动后置 true：卡片正面的 .task(id: word.id) 会检查它，决定是
    /// 否跳过自己那一次 speak——避免状态机的"第 1 遍"被它先发抢占，导致用户
    /// 听到的变成 4 遍且前两遍节奏错乱。
    @Published private(set) var suppressCardAutoSpeak = false

    /// TabView 切走再切回来会让这个 tab 重新走一遍 appear，.task 也会跟着重新
    /// 触发；如果每次都无条件调 loadQueue()（会把 currentIndex 清零），用户刚
    /// 翻到第 5 个词，切一下 tab 回来就被打回第一个。用这个标记让 .task 只在
    /// 本次进程里真正加载一次，后续切 tab 回来不再重置进度；下拉刷新走的还是
    /// loadQueue()，仍然是一次完整重置，语义上也说得通（用户主动要求刷新）。
    private var hasLoadedOnce = false

    /// 自动播放用的"我刚才正在播的遍数"：每个词 0..2，第 3 遍播完就切下一个。
    /// 用 published 是为了 UI 能显示"第 N 遍"提示词。
    @Published private(set) var autoplayPassIndex = 0

    /// 自动播放的停顿节奏（秒）。这些是经过手感调整的经验值——播 1 遍约 0.8s，
    /// 遍间 0.6s 让听者跟上节奏、词间 2s 给思考时间。
    private static let betweenPassesDelay: TimeInterval = 0.6
    private static let betweenWordsDelay: TimeInterval = 2.0
    private static let autoplayPassCount = 3

    /// 后台串行驱动自动播放的 Task 引用；停止时 cancel 掉、置 nil，下次再启动
    /// 时新建——避免旧任务的 sleep / speak 残留。
    private var autoplayTask: Task<Void, Never>?

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
        // 用户主动切词时停掉自动播放——让用户接管节奏
        stopAutoplay()
    }

    func goToNext() {
        guard canGoNext else { return }
        currentIndex += 1
        isFlipped = false
        stopAutoplay()
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
        stopAutoplay()
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
            // 评分完自动停止连播——进入下一个词后由用户决定要不要继续播
            stopAutoplay()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "提交复习结果失败"
        }
    }

    // MARK: - 自动播放

    /// 启动自动播放：从当前词开始，每个词读 3 遍、词间停顿。
    func startAutoplay() {
        guard !queue.isEmpty, currentIndex < queue.count else { return }
        // 已经在播就忽略，避免重复触发
        guard !isAutoplay else { return }
        isAutoplay = true
        suppressCardAutoSpeak = true
        autoplayWordIndex = currentIndex
        autoplayPassIndex = 0
        autoplayTask?.cancel()
        autoplayTask = Task { [weak self] in
            await self?.runAutoplayLoop()
        }
    }

    /// 停掉自动播放：取消后台 Task、清状态。当前正在播的那一次不会被立刻掐断
    /// （AVAudioPlayer 没暴露 cancel-and-silence API），但下一次状态推进会被
    /// guard 拦下来。
    func stopAutoplay() {
        autoplayTask?.cancel()
        autoplayTask = nil
        if isAutoplay {
            isAutoplay = false
            suppressCardAutoSpeak = false
            autoplayPassIndex = 0
        }
    }

    /// 自动播放主循环：每个词 3 遍 + 词间停顿。用 await Pronouncer.shared.speak()
    /// 的串行调用推进——Pronouncer 自己有"播完回调"但不暴露 async API，所以这里
    /// 用"播完回调 + 短 sleep"的轮询模式等音频结束。
    private func runAutoplayLoop() async {
        while isAutoplay, currentIndex < queue.count, !Task.isCancelled {
            autoplayWordIndex = currentIndex
            let word = queue[currentIndex]
            for pass in 0..<Self.autoplayPassCount {
                if Task.isCancelled || !isAutoplay { return }
                autoplayPassIndex = pass
                await speakAndWait(word.word)
                if Task.isCancelled || !isAutoplay { return }
                // 3 遍里的最后一遍之后不需要遍间停顿——词间停顿会接上
                if pass < Self.autoplayPassCount - 1 {
                    try? await Task.sleep(for: .seconds(Self.betweenPassesDelay))
                }
            }
            if Task.isCancelled || !isAutoplay { return }
            try? await Task.sleep(for: .seconds(Self.betweenWordsDelay))
            // 推进到下一个词；如果已经到队列尾就停
            if currentIndex < queue.count - 1 {
                currentIndex += 1
                isFlipped = false
            } else {
                stopAutoplay()
                return
            }
        }
    }

    /// 触发 Pronouncer 播放一个词，并 await 到播放真正结束。
    /// Pronouncer 的 playingWord 变 nil（AVAudioPlayerDelegate didFinish）作为
    /// "结束"信号。短 sleep 防止 audioPlayerDidFinishPlaying 还没回调就被下一句
    /// 抢占（极端快连发的边界情况）。4s 兜底避免极端情况下挂死。
    private func speakAndWait(_ word: String) async {
        let targetWord = word.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        Pronouncer.shared.speak(word)
        let deadline = Date().addingTimeInterval(4.0)
        while Pronouncer.shared.playingWord == targetWord,
              Date() < deadline, !Task.isCancelled {
            try? await Task.sleep(for: .milliseconds(80))
        }
    }
}
