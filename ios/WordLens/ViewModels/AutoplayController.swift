// ViewModels/AutoplayController.swift
import Foundation
import UIKit

extension Notification.Name {
    static let pronouncerRemotePlay = Notification.Name("pronouncerRemotePlay")
    static let pronouncerRemotePause = Notification.Name("pronouncerRemotePause")
    static let pronouncerRemoteNext = Notification.Name("pronouncerRemoteNext")
    static let pronouncerRemotePrevious = Notification.Name("pronouncerRemotePrevious")
}

/// 自动播放要读哪个词、能不能往前/往后走，由队列的持有者（ReviewViewModel）回答。
///
/// 用协议而不是让 AutoplayController 直接持有队列：控制器只关心「当前词是什么」
/// 「还有没有下一个」，不该知道什么是复习队列、什么是评分。这样它既能被单独
/// 理解，也能在不搭一整套复习状态的前提下测试。
@MainActor
protocol AutoplayDataSource: AnyObject {
    /// 当前该读的词；nil 表示队列空了，播放应当停止。
    var autoplayCurrentWord: String? { get }
    var autoplayHasNext: Bool { get }
    var autoplayHasPrevious: Bool { get }
    /// 锁屏副标题，通常是当前播放列表的名字。
    var autoplaySubtitle: String { get }
    func autoplayAdvance()
    func autoplayGoBack()
}

/// 自动连播的状态机：每个词读 N 遍，遍间短停顿、词间长停顿，读完自动切下一个。
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

    weak var dataSource: AutoplayDataSource?

    /// 播放节奏（秒）。经验值：播 1 遍约 0.8s，遍间 0.6s 让听者跟上节奏、
    /// 词间 2s 给思考时间。
    private static let betweenPassesDelay: TimeInterval = 0.6
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
        observe(.pronouncerRemotePause) { $0.stop() }
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

    private func observe(_ name: Notification.Name, action: @escaping @MainActor (AutoplayController) -> Void) {
        let observer = NotificationCenter.default.addObserver(
            forName: name, object: nil, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self else { return }
                action(self)
            }
        }
        observers.append(observer)
    }

    // MARK: - 控制

    func start() {
        guard !isPlaying, let word = dataSource?.autoplayCurrentWord else { return }
        isPlaying = true
        passIndex = 0
        Pronouncer.shared.beginNowPlayingSession(
            title: word, subtitle: "鹦鹉学舌 · \(dataSource?.autoplaySubtitle ?? "复习")"
        )
        task?.cancel()
        task = Task { [weak self] in
            await self?.runLoop()
        }
    }

    /// 停掉自动播放。当前正在响的那一声不会被立刻掐断（AVAudioPlayer 没有
    /// cancel-and-silence 的 API），但状态机的下一次推进会被 guard 拦下来。
    func stop() {
        task?.cancel()
        task = nil
        guard isPlaying else { return }
        isPlaying = false
        passIndex = 0
        Pronouncer.shared.endNowPlayingSession()
    }

    func toggle() {
        isPlaying ? stop() : start()
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
            Pronouncer.shared.updateNowPlayingTitle(word)

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
            try? await Task.sleep(for: .seconds(Self.betweenWordsDelay))
            if Task.isCancelled || !isPlaying { return }

            guard dataSource?.autoplayHasNext == true else {
                stop()
                return
            }
            dataSource?.autoplayAdvance()
        }
    }

    /// 触发一次发音并 await 到播放真正结束。
    ///
    /// Pronouncer 用 `playingWord` 变 nil（AVAudioPlayerDelegate didFinish）表示
    /// 「读完了」，但没暴露 async API，所以这里轮询它。4s 兜底避免极端情况挂死。
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
