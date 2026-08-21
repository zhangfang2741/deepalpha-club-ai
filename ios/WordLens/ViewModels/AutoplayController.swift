// ViewModels/AutoplayController.swift
import Foundation
import UIKit

extension Notification.Name {
    static let pronouncerRemotePlay = Notification.Name("pronouncerRemotePlay")
    static let pronouncerRemotePause = Notification.Name("pronouncerRemotePause")
    static let pronouncerRemoteNext = Notification.Name("pronouncerRemoteNext")
    static let pronouncerRemotePrevious = Notification.Name("pronouncerRemotePrevious")
}

/// 自动播放要读哪个词和例句、能不能往前/往后走，由队列持有者回答。
///
/// 用协议而不是让 AutoplayController 直接持有队列：控制器只关心「当前词是什么」
/// 「还有没有下一个」，不该知道什么是复习队列、什么是评分。这样它既能被单独
/// 理解，也能在不搭一整套复习状态的前提下测试。
@MainActor
protocol AutoplayDataSource: AnyObject {
    /// 当前该读的词；nil 表示队列空了，播放应当停止。
    var autoplayCurrentWord: String? { get }
    /// 当前词的唯一标识。用它而不是词本身判断"换词了没"——同一个分组里可能有
    /// 拼写相同的两条记录，比字符串会误判成没换。
    var autoplayCurrentWordID: String? { get }
    /// 当前词的英文例句；nil 表示没有可朗读的例句。
    var autoplayCurrentExampleSentence: String? { get }
    var autoplayHasNext: Bool { get }
    var autoplayHasPrevious: Bool { get }
    /// 锁屏副标题，通常是当前播放列表的名字。
    var autoplaySubtitle: String { get }
    /// 读完规定遍数后是否要停下等用户操作（听写模式）。
    var autoplayWaitsForInput: Bool { get }
    func autoplayAdvance()
    func autoplayGoBack()
}

/// 自动连播的状态机：每个词读 N 遍，再读英文例句，最后自动切到下一个。
///
/// 从 ReviewViewModel 里整段抽出来的——原先它和「队列 + 评分」挤在同一个类里，
/// 后台任务、锁屏远程命令、播放节奏三件事互相缠着，改一处要通读全文件。现在
/// 自动播放相关的一切都在这里，ReviewViewModel 只剩队列本身的职责。
@MainActor
final class AutoplayController: ObservableObject {
    /// 是否正在自动播放。
    @Published private(set) var isPlaying = false
    /// 当前词读到第几遍（0 起），UI 显示「第 N / 3 遍」。
    @Published private(set) var passIndex = 0
    /// 单词三遍结束后正在朗读例句，供顶部进度状态同步展示。
    @Published private(set) var isReadingExample = false

    weak var dataSource: AutoplayDataSource?

    // MARK: - 学习额度闸门（免费用户每日限学 N 个新词）
    //
    // AutoplayController 本身不认识订阅/额度，靠这三个闭包把判断留给上层
    // （ReviewCardView 用 StoreManager + UsageTracker 接线）。不接线时闭包为
    // nil，行为与原来完全一致——保持控制器可独立测试。

    /// 换到某个词开始播之前问一次「这个新词能不能学」。返回 false 表示达到免费
    /// 上限、需要订阅：播放会停下并回调 `onLearningBlocked`。
    /// 标 @MainActor：闭包里要读 StoreManager / UsageTracker 这些主 actor 状态。
    var learningGate: (@MainActor (_ wordID: String) -> Bool)?
    /// 一个词完整读完（三遍）后回调，用来记「今日已学」。
    var onWordLearned: (@MainActor (_ wordID: String) -> Void)?
    /// 因额度用尽被拦截时回调（供 UI 弹订阅墙）。
    var onLearningBlocked: (@MainActor () -> Void)?

    /// 播放节奏（秒）。经验值：播 1 遍约 0.8s，遍间 0.6s 让听者跟上节奏、
    /// 词间 2s 给思考时间。
    private static let betweenPassesDelay: TimeInterval = 0.6
    private static let beforeExampleDelay: TimeInterval = 0.65
    private static let betweenWordsDelay: TimeInterval = 2.0
    static let passCount = 3

    /// 后台串行驱动播放的 Task；停止时 cancel 掉、置 nil，下次启动时新建，
    /// 避免旧任务的 sleep / speak 残留。
    private var task: Task<Void, Never>?
    private var observers: [NSObjectProtocol] = []

    init() {
        // 锁屏 / 控制中心的播放键由 Pronouncer 转成通知广播，这里接住。
        // Pronouncer 因此不用反向依赖任何业务类型。
        observe(.pronouncerRemotePlay) { $0.start() }
        // 锁屏按暂停走 pause() 而不是 stop()：见 pause() 的注释，拆会话会让
        // App 在锁屏下直接被系统挂起。
        observe(.pronouncerRemotePause) { $0.pause() }
        observe(.pronouncerRemoteNext) { $0.skipToNext() }
        observe(.pronouncerRemotePrevious) { $0.skipToPrevious() }
    }

    deinit {
        // block-based observer 必须手动摘掉，否则 NotificationCenter 会一直持有它。
        // （原来在 ReviewViewModel 里加了监听却从没移除。）
        for observer in observers {
            NotificationCenter.default.removeObserver(observer)
        }
    }

    /// 远程命令的回调线程由 MediaPlayer 决定，不保证是主线程。
    ///
    /// 这里**不能**用 `MainActor.assumeIsolated`：它在断言不成立时是直接
    /// `fatalError`，等于给一条本来只需要切线程的路径埋了个崩溃点。用
    /// `Task { @MainActor in }` 显式切过去，怎么调都不会 trap。
    private func observe(_ name: Notification.Name, action: @escaping @MainActor (AutoplayController) -> Void) {
        let observer = NotificationCenter.default.addObserver(
            forName: name, object: nil, queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                guard let self else { return }
                action(self)
            }
        }
        observers.append(observer)
    }

    // MARK: - 控制

    /// 开始或从暂停恢复。会话还在（暂停态）时只翻状态、重开循环，不重建会话。
    func start() {
        guard !isPlaying, let word = dataSource?.autoplayCurrentWord else { return }
        isPlaying = true
        passIndex = 0
        isReadingExample = false
        if Pronouncer.shared.isNowPlayingSessionActive {
            Pronouncer.shared.resumeNowPlayingSession()
            Pronouncer.shared.updateNowPlayingTitle(word)
        } else {
            Pronouncer.shared.beginNowPlayingSession(
                title: word, subtitle: "\(AppConfig.displayName) · \(dataSource?.autoplaySubtitle ?? "复习")"
            )
        }
        task?.cancel()
        task = Task { [weak self] in
            await self?.runLoop()
        }
    }

    /// 暂停：停止读词，但**保留整个会话**（锁屏卡片、远程命令、静音保活轨都还在）。
    ///
    /// 这三样东西留着，App 才能在锁屏下继续存活、用户才点得到「继续播」。锁屏的
    /// 暂停键走这里而不是 stop()——走 stop() 会把音频整个停掉，而 App 在后台唯一
    /// 的存活理由就是「正在播音频」，音频一停 iOS 立刻挂起它，卡片也没了，用户
    /// 看到的就是「点了暂停整个 App 就退出了」。
    func pause() {
        task?.cancel()
        task = nil
        guard isPlaying else { return }
        isPlaying = false
        passIndex = 0
        isReadingExample = false
        Pronouncer.shared.pauseNowPlayingSession()
    }

    /// 彻底结束：连锁屏卡片一起收掉，音频焦点还给别的 App。
    /// 用在 App 内主动停止、换分组、评分、队列播完这些场景——那时用户人就在
    /// 前台，不存在"被系统挂起"的问题。
    func stop() {
        task?.cancel()
        task = nil
        isPlaying = false
        passIndex = 0
        isReadingExample = false
        Pronouncer.shared.endNowPlayingSession()
    }

    func toggle() {
        isPlaying ? stop() : start()
    }

    /// 听写重新作答或接受结果后，从当前词的第 1 遍重新启动循环。
    /// 保留现有 Now Playing 会话，只取消旧任务和当前短音频，避免锁屏控件闪烁。
    func restartCurrent() {
        guard isPlaying else { return }
        task?.cancel()
        Pronouncer.shared.stopCurrentPlayback()
        guard let word = dataSource?.autoplayCurrentWord else {
            stop()
            return
        }
        passIndex = 0
        isReadingExample = false
        Pronouncer.shared.updateNowPlayingTitle(word)
        task = Task { [weak self] in
            await self?.runLoop()
        }
    }

    /// 锁屏「下一首」：像切歌一样跳到下一个词，继续播。没在播的时候不响应——
    /// 那种情况下远程命令本来就是禁用的。
    func skipToNext() {
        guard isPlaying, dataSource?.autoplayHasNext == true else { return }
        restartLoop { $0.autoplayAdvance() }
    }

    func skipToPrevious() {
        guard isPlaying, dataSource?.autoplayHasPrevious == true else { return }
        restartLoop { $0.autoplayGoBack() }
    }

    /// 换词后重开循环：先 cancel 掉旧 Task（它正卡在某个 sleep 或等音频结束），
    /// 移动位置，再起一个新的从第 1 遍开始读。全程不碰 `isPlaying`，也不碰
    /// Now Playing 会话的 playbackState —— 锁屏按钮因此不会闪。
    private func restartLoop(_ move: (AutoplayDataSource) -> Void) {
        guard let dataSource else { return }
        task?.cancel()
        move(dataSource)
        passIndex = 0
        isReadingExample = false
        if let word = dataSource.autoplayCurrentWord {
            Pronouncer.shared.updateNowPlayingTitle(word)
        }
        task = Task { [weak self] in
            await self?.runLoop()
        }
    }

    // MARK: - 播放循环

    /// 后台运行需要三道保险同时到位：
    ///   1. Info.plist 声明 UIBackgroundModes=audio（系统允许后台音频）
    ///   2. Pronouncer 配 AVAudioSession .playback（音频本身继续播）
    ///   3. beginBackgroundTask 抓住系统给的额外 ~30s：`.playback` 下声音能继续
    ///      响，但 Task.sleep 那些停顿时间系统照样会把 App 挂起，需要后台时间撑过去
    private func runLoop() async {
        let bgBox = BackgroundTaskBox()
        bgBox.id = UIApplication.shared.beginBackgroundTask(withName: "review_autoplay") {
            bgBox.end()
        }
        defer { bgBox.end() }

        while isPlaying, !Task.isCancelled {
            guard let word = dataSource?.autoplayCurrentWord else {
                stop()
                return
            }

            // 学习额度闸门：这个新词能不能学？达到免费上限就停播 + 弹订阅墙。
            // 已学过的词 gate 会放行（不重复计数），所以复习旧词不受影响。
            let currentID = dataSource?.autoplayCurrentWordID
            if let currentID, let learningGate, !learningGate(currentID) {
                onLearningBlocked?()
                stop()
                return
            }

            Pronouncer.shared.updateNowPlayingTitle(word)

            // 读单词的同时就并行把例句音频预取缓存好（MiniMax 后端合成要几秒）。
            // 等三遍单词读完轮到例句时，直接命中缓存秒播，消掉「单词读完到句子出声」
            // 中间那段串行等待的长空档。预取是独立请求，不打断正在读的单词。
            if let example = dataSource?.autoplayCurrentExampleSentence {
                Pronouncer.shared.prefetchExampleSentence(example)
            }

            for pass in 0..<Self.passCount {
                if Task.isCancelled || !isPlaying { return }
                passIndex = pass
                await speakAndWait(word)
                if Task.isCancelled || !isPlaying { return }
                // 最后一遍之后不需要遍间停顿——词间停顿会接上
                if pass < Self.passCount - 1 {
                    try? await Task.sleep(for: .seconds(Self.betweenPassesDelay))
                }
            }

            if Task.isCancelled || !isPlaying { return }

            // 单词三遍读完 = 完整学过一遍：记一次「今日已学」（同词重复无副作用）。
            if let currentID { onWordLearned?(currentID) }

            // 单词读完三遍后，把例句的英文部分作为完整句子一次合成、一次播放。
            // 不拆词，TTS 才能根据整句上下文生成自然的停顿、连读和重音。
            if let example = dataSource?.autoplayCurrentExampleSentence {
                try? await Task.sleep(for: .seconds(Self.beforeExampleDelay))
                if Task.isCancelled || !isPlaying { return }
                isReadingExample = true
                Pronouncer.shared.updateNowPlayingTitle(L("例句 · %@", word))
                await speakAndWait(example, isExample: true)
                isReadingExample = false
                Pronouncer.shared.updateNowPlayingTitle(word)
                if Task.isCancelled || !isPlaying { return }
            }

            // 听写模式：读完就停在这个词，等用户写完提交，不自己往下走。
            if dataSource?.autoplayWaitsForInput == true {
                await waitUntilWordChanges()
                if Task.isCancelled || !isPlaying { return }
                guard dataSource?.autoplayCurrentWord != nil else {
                    stop()
                    return
                }
                continue
            }

            try? await Task.sleep(for: .seconds(Self.betweenWordsDelay))
            if Task.isCancelled || !isPlaying { return }

            guard dataSource?.autoplayHasNext == true else {
                stop()
                return
            }
            dataSource?.autoplayAdvance()
        }
    }

    /// 挂起到「当前词换掉」为止。
    ///
    /// 退出条件用的是词变了，而不是「用户确认输入了」：确认后只展示系统判断，
    /// 队列并未前进；用户右滑接受、评分成功并切到下一词后才退出等待。左滑重听
    /// 则由 restartCurrent() 取消旧循环，从当前词第 1 遍重新开始。队列播完时
    /// 当前词变 nil，同样 ≠ 原值，也能正常退出。
    ///
    /// 用轮询而不是 continuation：本文件的 speakAndWait 已经是轮询
    /// Pronouncer 状态的写法，保持一致；也免掉 continuation 必须恰好 resume
    /// 一次的生命周期坑（用户中途停播、切词的路径太多）。
    private func waitUntilWordChanges() async {
        let original = dataSource?.autoplayCurrentWordID
        while isPlaying, !Task.isCancelled, dataSource?.autoplayCurrentWordID == original {
            try? await Task.sleep(for: .milliseconds(120))
        }
    }

    /// 触发一次发音并 await 到播放真正结束。
    ///
    /// Pronouncer 用 `playingWord` 变 nil（AVAudioPlayerDelegate didFinish）表示
    /// 「读完了」，但没暴露 async API，所以这里轮询它。4s 兜底避免极端情况挂死。
    private func speakAndWait(_ text: String, isExample: Bool = false) async {
        let targetText = text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if isExample {
            Pronouncer.shared.speakExampleSentence(text)
        } else {
            Pronouncer.shared.speak(text)
        }
        // 单词通常不到 2 秒；例句还包含远程合成耗时和完整句长，给足 30 秒避免
        // 句子没读完就被下一个词打断。超时仍会继续队列，防止异常音频永久挂住。
        let deadline = Date.now.addingTimeInterval(isExample ? 30.0 : 6.0)
        while Pronouncer.shared.playingWord == targetText,
              Date.now < deadline, !Task.isCancelled {
            try? await Task.sleep(for: .milliseconds(80))
        }
    }
}

/// 让后台任务 ID 能在 beginBackgroundTask 的 expirationHandler 闭包和主函数
/// 之间共享——Swift 的局部 `var` 不能被 @escaping 闭包 mutate，必须用引用类型。
private final class BackgroundTaskBox: @unchecked Sendable {
    var id: UIBackgroundTaskIdentifier = .invalid

    func end() {
        guard id != .invalid else { return }
        UIApplication.shared.endBackgroundTask(id)
        id = .invalid
    }
}
