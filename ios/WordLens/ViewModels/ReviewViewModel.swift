// ViewModels/ReviewViewModel.swift
import Combine
import Foundation

/// 复习学习模式（存 UserDefaults，首页可切换）。只影响队列的排序/打乱，
/// 不改后端的 SM-2 调度——评分怎么算下次复习时间始终按 SM-2 来。
///
/// 对内置分组和自定义歌单同样生效：`.smart` 按到期时间、`.sequential` 按加入
/// 时间，任何来源的队列都有这两个字段。
enum ReviewMode: String, CaseIterable {
    case smart       // 智能复习：按到期时间（SM-2 默认）
    case random      // 随机乱序
    case hardFirst   // 难词优先：不认识 → 模糊 → 认识
    case sequential  // 加入顺序：按加入时间正序

    static var current: ReviewMode {
        get {
            let raw = UserDefaults.standard.string(forKey: "review_mode") ?? smart.rawValue
            return ReviewMode(rawValue: raw) ?? .smart
        }
        set { UserDefaults.standard.set(newValue.rawValue, forKey: "review_mode") }
    }

    var label: String {
        switch self {
        case .smart: return "智能复习"
        case .random: return "随机乱序"
        case .hardFirst: return "难词优先"
        case .sequential: return "加入顺序"
        }
    }

    /// 播放条那颗键用的图标，跟着当前模式变。每种图标都直接表达排序语义，
    /// 避免用户还要结合菜单文案猜当前播放方式。
    var systemImage: String {
        switch self {
        case .smart: return "sparkles"
        case .random: return "shuffle"
        case .hardFirst: return "exclamationmark.triangle.fill"
        // 播放条会把两枚 arrow.right 上下并排；这里保留单枚箭头作为系统图标后备。
        case .sequential: return "arrow.right"
        }
    }

    /// 难词优先的状态权重：不认识最靠前。
    private static func statusRank(_ status: String) -> Int {
        switch status {
        case "new": return 0
        case "fuzzy": return 1
        default: return 2  // known
        }
    }

    /// 按当前模式对队列重排。ISO8601 时间字符串按字典序即等价于按时间先后。
    func ordered(_ words: [VocabularyWord]) -> [VocabularyWord] {
        switch self {
        case .smart:
            return words.sorted { $0.nextReviewAt < $1.nextReviewAt }
        case .random:
            return words.shuffled()
        case .hardFirst:
            // 先按状态权重，同状态内再按到期时间，保证稳定可预期。
            return words.sorted {
                let l = ReviewMode.statusRank($0.status), r = ReviewMode.statusRank($1.status)
                return l != r ? l < r : $0.nextReviewAt < $1.nextReviewAt
            }
        case .sequential:
            return words.sorted { $0.createdAt < $1.createdAt }
        }
    }

    /// 自定义歌单的默认顺序应该是用户自己排的顺序（后端按 position 返回），
    /// 所以 `.smart` 对歌单不重排——「智能」在这里就是「按你排的来」。
    func ordered(_ words: [VocabularyWord], for selection: PlaylistSelection) -> [VocabularyWord] {
        if selection.isCustom, self == .smart { return words }
        return ordered(words)
    }
}

@MainActor
final class ReviewViewModel: ObservableObject {
    @Published var queue: [VocabularyWord] = []
    @Published var currentIndex = 0
    @Published var isFlipped = false
    @Published var isLoading = false
    @Published var isSubmitting = false
    @Published var errorMessage: String?
    @Published var totalCount = 0
    /// 本次已评分（提交成功）的词数。评过分的词会从 queue 里移除，所以用它而不是
    /// queue.count 来算进度和"复习完成"。
    @Published private(set) var reviewedCount = 0

    /// 当前学习模式（只影响队列排序，不改 SM-2 调度）。
    @Published private(set) var mode: ReviewMode = ReviewMode.current

    /// 当前在播哪一组词。变更由 switchPlaylist 统一走，顺带持久化。
    @Published private(set) var selection: PlaylistSelection = PlaylistSelection.current

    /// 当前播放列表的显示名（自定义歌单要靠面板加载到的歌单列表才能查到名字，
    /// 由 ReviewCardView 在歌单列表变化时回填）。
    @Published var selectionName: String = PlaylistSelection.current.displayName()

    /// 自动播放状态机。抽成独立对象后这里只负责把队列的「当前词 / 有没有下一个」
    /// 喂给它（见文件末尾的 AutoplayDataSource 实现）。
    let autoplay = AutoplayController()

    /// 卡片正面的 .task(id: word.id) 会检查它，决定是否跳过自己那一次 speak——
    /// 自动播放期间由状态机统一掌控节奏，卡片再抢发一次会变成听到 4 遍且节奏错乱。
    var suppressCardAutoSpeak: Bool { autoplay.isPlaying }

    // MARK: - 听写

    /// 学习方式：只听 / 听写。切换即时生效，并把当前词的听写相位重置。
    @Published private(set) var studyMode: StudyMode = StudyMode.current

    /// 听写相位：等输入 / 已判定。切词时重置回 .input。
    @Published private(set) var dictationPhase: DictationPhase = .input

    /// 输入框里的内容。
    @Published var dictationInput: String = ""

    var isDictation: Bool { studyMode == .dictation }

    func changeStudyMode(to mode: StudyMode) {
        guard mode != studyMode else { return }
        studyMode = mode
        StudyMode.current = studyMode
        resetDictation()
    }

    private func resetDictation() {
        dictationInput = ""
        dictationPhase = .input
    }

    /// 判定这一次听写并提交。
    ///
    /// 亮答案停 1.5 秒再提交，是为了让用户看清正确拼写和自己写的差在哪；这段
    /// 时间里连播状态机正卡在「等当前词换掉」的轮询上，不会抢跑。
    func submitDictation() async {
        guard isDictation, dictationPhase.isInput, let word = currentWord else { return }
        // 空输入禁止提交——「确定」按钮已经替用户挡住了，但键盘回车（TextField
        // 的 onSubmit）会绕过按钮直接进这里，所以再补一道。两道屏障一道语义。
        let typed = dictationInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !typed.isEmpty else { return }
        let rating = DictationJudge.judge(input: typed, answer: word.word)
        // 把词和输入一起快照进相位——亮答案期间界面只认这份快照，不会因为队列
        // 在提交时前进而闪出下一个词的拼写。
        dictationPhase = .revealed(word: word, input: typed, rating: rating)
        Haptics.rating(rating)

        try? await Task.sleep(for: .seconds(1.5))
        // 停留期间用户可能已经手动切词/停播了，确认还停在同一个词才提交。
        guard currentWord?.id == word.id, case .revealed = dictationPhase else { return }
        // keepAutoplay: 听写模式下评分是流程的一环，不该像手点评分那样打断连播。
        await submit(rating, keepAutoplay: true)
        resetDictation()
    }

    /// TabView 切走再切回来会让这个 tab 重新走一遍 appear，.task 也会跟着重新
    /// 触发；如果每次都无条件调 loadQueue()（会把 currentIndex 清零），用户刚
    /// 翻到第 5 个词，切一下 tab 回来就被打回第一个。用这个标记让 .task 只在
    /// 本次进程里真正加载一次，后续切 tab 回来不再重置进度；下拉刷新走的还是
    /// loadQueue()，仍然是一次完整重置，语义上也说得通（用户主动要求刷新）。
    private var hasLoadedOnce = false

    /// 切换卡片的滑动方向：-1 = 下一个往右滑出（"上一步"）、+1 = 下一个往左
    /// 滑出（"下一步"）。每次 goTo/goToNext/submit 都改一次，UI 的 .transition
    /// 据此决定入场方向；idempotent 的 onAppear 加载不会动它。
    @Published private(set) var transitionDirection: Int = 1

    /// 转发 autoplay 的变更给自己的订阅者。AutoplayController 是个独立的
    /// ObservableObject，SwiftUI 不会因为它是本对象的一个 `let` 属性就自动
    /// 跟着刷新——播放按钮的图标、「第 N / 3 遍」这些都读的是它的状态，必须
    /// 手动把 objectWillChange 串起来，视图层才不用同时订阅两个对象。
    private var cancellables: Set<AnyCancellable> = []

    init() {
        autoplay.dataSource = self
        autoplay.objectWillChange
            .sink { [weak self] _ in self?.objectWillChange.send() }
            .store(in: &cancellables)
    }

    var currentWord: VocabularyWord? {
        guard currentIndex < queue.count else { return nil }
        return queue[currentIndex]
    }

    /// 评过分的词会即时从 queue 移除，所以"全部过完"= 队列已空且这次至少评过一个。
    /// （队列一开始就空是"这一组没有词"，不是"完成"，靠 reviewedCount 区分。）
    var isFinished: Bool { queue.isEmpty && reviewedCount > 0 }

    /// 「上一个/下一个」只是浏览，不提交评分——跟 submit() 的自动前进是两码事。
    /// canGoNext 卡在 queue.count - 1，不让浏览走到"复习完成"那一屏，
    /// 那个只应该由实际提交评分触发。
    var canGoPrevious: Bool { currentIndex > 0 }
    var canGoNext: Bool { currentIndex < queue.count - 1 }

    func goToPrevious() {
        guard canGoPrevious else { return }
        transitionDirection = -1
        currentIndex -= 1
        isFlipped = false
        resetDictation()
        // 用户主动切词时停掉自动播放——让用户接管节奏
        autoplay.stop()
    }

    func goToNext() {
        guard canGoNext else { return }
        transitionDirection = 1
        currentIndex += 1
        isFlipped = false
        resetDictation()
        autoplay.stop()
    }

    /// 跳到队列里的某个词。方向按前后关系推，让切卡动画的入场方向跟用户的直觉
    /// 一致（跳到靠后的词 = 往前走）。
    ///
    /// - Parameter play: true 表示「从这个词开始播」——首页顶部的播放队列下拉框
    ///   点词就是这个语义。false 只是把卡片翻到那个词。
    func jump(to word: VocabularyWord, play: Bool = false) {
        guard let index = queue.firstIndex(where: { $0.id == word.id }) else { return }
        if index != currentIndex {
            transitionDirection = index > currentIndex ? 1 : -1
            currentIndex = index
            isFlipped = false
            resetDictation()
        }
        // 先停再起：连播状态机正卡在上一个词的某一遍上，不停掉的话新词要等它
        // 把当前这轮走完才轮得到。
        autoplay.stop()
        if play { autoplay.start() }
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
        reviewedCount = 0
        isFlipped = false
        transitionDirection = 1
        resetDictation()
        autoplay.stop()
        defer { isLoading = false }
        do {
            let words = try await PlaylistQueueSource.load(selection)
            queue = mode.ordered(words, for: selection)
            totalCount = queue.count
        } catch let error as APIError {
            errorMessage = error.message
            // 歌单在别的设备上被删掉时会 404——回落到待复习，免得卡在一个
            // 永远加载不出来的组里。
            if error.statusCode == 404, selection.isCustom {
                await switchPlaylist(.dueReview, name: PlaylistSelection.dueReview.displayName())
            }
        } catch {
            errorMessage = "加载单词列表失败"
        }
    }

    /// 切换播放列表：停播、重置进度、按新来源重新加载。
    func switchPlaylist(_ newSelection: PlaylistSelection, name: String) async {
        selection = newSelection
        selectionName = name
        PlaylistSelection.current = newSelection
        hasLoadedOnce = true
        await loadQueue()
    }

    func flip() {
        isFlipped.toggle()
    }

    /// 切换学习模式：把剩余（未评分）的队列按新模式重排，并从头开始。已评分的词
    /// 早就移出队列，不受影响；不重新请求后端。
    func changeMode(_ newMode: ReviewMode) {
        guard newMode != mode else { return }
        mode = newMode
        ReviewMode.current = newMode
        autoplay.stop()
        queue = newMode.ordered(queue, for: selection)
        currentIndex = 0
        isFlipped = false
        resetDictation()
        transitionDirection = 1
    }

    /// 提交一次评分。
    ///
    /// - Parameter keepAutoplay: 默认 false——手点三档评分意味着用户要接管节奏，
    ///   评完就该停下。听写模式传 true：那里评分是自动流程的一环，停了连播就断了。
    func submit(_ rating: ReviewRating, keepAutoplay: Bool = false) async {
        guard let word = currentWord else { return }
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            _ = try await WordService.submitReview(wordId: word.id, rating: rating)
            reviewedCount += 1
            // 评过分的词直接从队列移除——不管在哪个分组里，评完就算过了这一遍，
            // 这样"上一个"退不回去、也不会重复评分。删除后同一个 currentIndex
            // 天然指向原来的下一个词，不再自增；只有删掉的是队尾时才会越界，
            // clamp 回最后一个（队列空则 0，配合 isFinished 显示完成）。
            queue.remove(at: currentIndex)
            if currentIndex >= queue.count {
                currentIndex = max(0, queue.count - 1)
            }
            transitionDirection = 1
            isFlipped = false
            if !keepAutoplay {
                // 评分完自动停止连播——进入下一个词后由用户决定要不要继续播
                autoplay.stop()
            }
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "提交复习结果失败"
        }
    }
}

// MARK: - AutoplayDataSource

extension ReviewViewModel: AutoplayDataSource {
    var autoplayCurrentWord: String? { currentWord?.word }
    var autoplayCurrentWordID: String? { currentWord?.id }
    var autoplayCurrentExampleSentence: String? { currentWord?.englishExampleSentence }
    var autoplayHasNext: Bool { canGoNext }
    var autoplayHasPrevious: Bool { canGoPrevious }
    var autoplaySubtitle: String { selectionName }
    /// 听写模式下读完 3 遍不能自动往下走，得停在这个词等用户写完。
    var autoplayWaitsForInput: Bool { isDictation }

    func autoplayAdvance() {
        guard canGoNext else { return }
        transitionDirection = 1
        currentIndex += 1
        isFlipped = false
        resetDictation()
    }

    func autoplayGoBack() {
        guard canGoPrevious else { return }
        transitionDirection = -1
        currentIndex -= 1
        isFlipped = false
        resetDictation()
    }
}
