// Views/Components/PronounceButton.swift
import AVFoundation
import Combine
import MediaPlayer
import SwiftUI

/// 发音口音偏好（存 UserDefaults，设置页可切换）。
///
/// 有道通过 type 参数区分英/美音；MiniMax 通过服务端配置的两套 voice ID 区分。
enum PronunciationAccent: String {
    case us
    case uk

    static var current: PronunciationAccent {
        get {
            let raw = UserDefaults.standard.string(forKey: "pronunciation_accent") ?? us.rawValue
            return PronunciationAccent(rawValue: raw) ?? .us
        }
        set {
            UserDefaults.standard.set(newValue.rawValue, forKey: "pronunciation_accent")
        }
    }

    /// 有道 `dictvoice` 的 type 参数：2=美音，1=英音。
    var youdaoType: Int { self == .uk ? 1 : 2 }
}

/// 发音语速偏好（存 UserDefaults，设置页可切换）。
///
/// 有道和 MiniMax 音频都用 `AVAudioPlayer` 倍速播放，不必按语速重复生成和缓存。
enum PronunciationRate: String, CaseIterable {
    case slow
    case normal
    case fast

    static var current: PronunciationRate {
        get {
            let raw = UserDefaults.standard.string(forKey: "pronunciation_rate") ?? normal.rawValue
            return PronunciationRate(rawValue: raw) ?? .normal
        }
        set {
            UserDefaults.standard.set(newValue.rawValue, forKey: "pronunciation_rate")
        }
    }

    /// `AVAudioPlayer.rate` 倍速（有效范围约 0.5–2.0）。
    ///
    /// MiniMax 的 fluent 整句在原始 1.0 倍下比有道词典音更紧凑，因此例句使用
    /// 独立校准后的倍率。“正常”使用 0.85，既保留自然连读，也更适合学习时跟读；
    /// 该调整发生在播放端，已经缓存的例句同样生效，不会重新消耗合成额度。
    func playbackRate(for purpose: PronunciationPurpose) -> Float {
        switch (purpose, self) {
        case (.word, .slow): return 0.75
        case (.word, .normal): return 1.0
        case (.word, .fast): return 1.35
        case (.sentence, .slow): return 0.60
        case (.sentence, .normal): return 0.85
        case (.sentence, .fast): return 1.0
        }
    }
}

enum PronunciationPurpose: String {
    case word
    case sentence
}

/// 是否在复习卡 / 单词详情出现时自动发音（存 UserDefaults，设置页可切换）。
///
/// 默认开：此前 master 已上线「点下一个自动读音」的无条件行为，把它统一收敛到这个
/// 开关后，默认保持原有体验，用户可在发音设置里关掉。
enum PronunciationAutoplay {
    private static let key = "pronunciation_autoplay"

    static var isEnabled: Bool {
        // 未设置过时返回 true（默认开）；设置过后按存的值。
        get {
            if UserDefaults.standard.object(forKey: key) == nil { return true }
            return UserDefaults.standard.bool(forKey: key)
        }
        set { UserDefaults.standard.set(newValue, forKey: key) }
    }
}

/// 内部发音源。用户无需手动选择：单词固定使用有道词典音，完整例句固定使用
/// 经自家后端中转的 MiniMax Speech HD。
enum PronunciationSource: String {
    case youdao
    case minimax

    /// MiniMax 走本项目后端，登录 token 随请求发送，供应商密钥不会下发到 App。
    var usesBackend: Bool { self == .minimax }
}

/// 单词发音播放器（单例）。
///
/// 单词由有道提供词典音，完整例句由 MiniMax 生成高清 MP3。首次播放后统一缓存到
/// Caches 目录，再次播放直接读取本地文件。这样既保留单词发音的准确性，也让例句
/// 具备自然的连读、停顿和重音。
///
/// 做成 ObservableObject（而不是之前的纯静态方法集合）：正在播放哪个词要是一份
/// 全局共享状态，不能只存在触发播放的那个 PronounceButton 自己的本地 @State 里。
/// 否则像"点下一个自动读音"这种不经过某个具体按钮点击的播放，画面上所有按钮的
/// 波纹动效都不会跟着动——它们各自的 isPlaying 压根不知道外面有播放发生。
@MainActor
final class Pronouncer: ObservableObject {
    static let shared = Pronouncer()
    private init() {}

    /// 当前正在播放的词（小写，跟 cacheURL 的 key 对齐），没有播放时为 nil。
    /// PronounceButton 拿自己的词（同样小写后）跟这个比较，决定要不要播波纹动效——
    /// 不管这次播放是被哪个按钮点出来的，还是像"下一个"那样代码直接触发的。
    @Published private(set) var playingWord: String?

    /// 必须持有强引用，否则 AVAudioPlayer 会被立即释放、还没出声就停了。
    private var player: AVAudioPlayer?
    private let session = URLSession(configuration: .default)
    private var requestTask: URLSessionDataTask?
    private var playbackRequestID = UUID()
    private lazy var delegate = PlaybackDelegate(owner: self)

    /// 不配置 AVAudioSession 的话，手机静音开关打开时会完全不出声——这是点小喇叭
    /// 没反应最常见的原因。用 `.playback` 类别让发音像音乐/视频一样忽略静音开关；
    /// mode 用 `.spokenAudio` 让系统知道这是"短停顿 + 持续朗读"模式，在自动播放
    /// 词间 2s 暂停时不会被其他 app 的音频提示"插队"; options 不加 .mixWithOthers，
    /// 这样复习期间不要和别的音频混着。
    ///
    /// .playback 也支持后台/息屏继续播放——前提是 Info.plist 的
    /// UIBackgroundModes 声明 audio。两件事必须同时到位，缺一不可。
    private lazy var configured: Void = {
        try? AVAudioSession.sharedInstance().setCategory(
            .playback, mode: .spokenAudio, options: []
        )
        setupRemoteCommandCenter()
    }()

    /// 每次真正要出声之前调一下：category 只需配置一次（`configured`），但
    /// **激活状态**不是一次性的——`endNowPlayingSession()` 会主动 setActive(false)
    /// 把音频焦点还给别的 App，之后再点小喇叭就得重新激活，否则静音开关打开时
    /// 又会没声音。setActive(true) 本身很便宜，重复调用无副作用。
    private func activateSessionIfNeeded() {
        _ = configured
        try? AVAudioSession.sharedInstance().setActive(true, options: [])
    }

    // MARK: - 锁屏 / 控制中心（Now Playing 会话）

    /// Now Playing 的生命周期跟「一次自动播放会话」绑定，**不是**跟单次音频绑定。
    ///
    /// 之前这里挂的是一个监听 `objectWillChange` 的长生命周期 Task：`playingWord`
    /// 一变就重设 nowPlayingInfo，每个词播完 `playingWord` 变 nil 就把 info 置成
    /// nil。自动播放每约 1 秒走一轮这个循环，系统于是反复判定「停播 → 又开始播」，
    /// 锁屏那个播放按钮就在播放/暂停两个图标之间来回闪。
    ///
    /// 现在改成显式的三个动作：会话开始建一次、切词只改标题、会话结束才清掉。
    /// 中间那些「一个词读完了」的空隙对系统完全不可见，按钮自然就稳住了。
    ///
    /// 另外，手动点小喇叭发音不会建立会话——单读一个词不该在锁屏留下媒体卡片。
    private var hasNowPlayingSession = false

    /// 开始一次自动播放会话：锁屏出现媒体卡片，播放键稳定显示为「暂停」。
    /// - Parameters:
    ///   - title: 当前单词
    ///   - subtitle: 播放列表名，让用户在锁屏也知道在播哪一组
    func beginNowPlayingSession(title: String, subtitle: String) {
        activateSessionIfNeeded()
        hasNowPlayingSession = true
        startKeepAlive()
        setRemoteCommandsEnabled(true)
        var info: [String: Any] = [:]
        info[MPMediaItemPropertyTitle] = title
        info[MPMediaItemPropertyArtist] = subtitle
        // 自动播放没有可 seek 的时间轴（每个词都是独立的短音频），声明成 live
        // 流，系统就不画进度条、也不会因为 elapsedTime 不推进而判定播放卡住。
        info[MPNowPlayingInfoPropertyIsLiveStream] = true
        info[MPNowPlayingInfoPropertyPlaybackRate] = 1.0
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
        MPNowPlayingInfoCenter.default().playbackState = .playing
    }

    // MARK: - 静音保活

    /// 连播期间循环播放的静音音频，作用是让音频引擎**一刻不停**。
    ///
    /// 只设 `playbackState = .playing` 是不够的：iOS 判断"这个 App 是不是在放
    /// 音频"最终看的是它有没有真的在出声。我们的音频是一个词一个 AVAudioPlayer，
    /// 词间还有 0.6～2 秒的静默空档——每个词播完那一刻音频就断了，系统据此把锁屏
    /// 按钮翻回"播放"，下一个词开始又翻成"暂停"，于是一个词闪一次。
    ///
    /// 垫一条无限循环的静音轨之后，整个会话期间音频引擎连续运转，系统看到的就是
    /// 一段不间断的播放，按钮稳定停在"暂停"。附带好处：`audio` 后台模式下持续
    /// 出声的 App 不会被挂起，词间那些 Task.sleep 不再依赖 beginBackgroundTask
    /// 那 ~30 秒的额度。
    private var keepAlivePlayer: AVAudioPlayer?

    private func startKeepAlive() {
        guard keepAlivePlayer == nil, let data = Self.silentWAVData(seconds: 1) else { return }
        guard let player = try? AVAudioPlayer(data: data) else { return }
        player.numberOfLoops = -1  // 无限循环
        player.volume = 1.0        // 音频数据本身就是静音，不靠调音量
        player.play()
        keepAlivePlayer = player
    }

    private func stopKeepAlive() {
        keepAlivePlayer?.stop()
        keepAlivePlayer = nil
    }

    /// 生成一段纯静音的 PCM WAV（16 bit / 单声道 / 44.1kHz）。
    /// AVAudioPlayer 需要一份完整的音频文件数据，直接在内存里拼一个最小 WAV
    /// 就够了，不用往 bundle 里塞一个静音 mp3。
    private static func silentWAVData(seconds: Int) -> Data? {
        let sampleRate = 44_100
        let channels = 1
        let bitsPerSample = 16
        let byteRate = sampleRate * channels * bitsPerSample / 8
        let blockAlign = channels * bitsPerSample / 8
        let dataSize = byteRate * seconds

        var data = Data()
        func appendUInt32(_ value: UInt32) { withUnsafeBytes(of: value.littleEndian) { data.append(contentsOf: $0) } }
        func appendUInt16(_ value: UInt16) { withUnsafeBytes(of: value.littleEndian) { data.append(contentsOf: $0) } }

        data.append(contentsOf: Array("RIFF".utf8))
        appendUInt32(UInt32(36 + dataSize))
        data.append(contentsOf: Array("WAVE".utf8))
        data.append(contentsOf: Array("fmt ".utf8))
        appendUInt32(16)                       // fmt chunk 长度
        appendUInt16(1)                        // PCM
        appendUInt16(UInt16(channels))
        appendUInt32(UInt32(sampleRate))
        appendUInt32(UInt32(byteRate))
        appendUInt16(UInt16(blockAlign))
        appendUInt16(UInt16(bitsPerSample))
        data.append(contentsOf: Array("data".utf8))
        appendUInt32(UInt32(dataSize))
        data.append(Data(count: dataSize))     // 全 0 即静音
        return data
    }

    /// 切到下一个词：只改标题，`playbackState` 原样不动。
    /// 这是「不闪」的关键——任何对 playbackState 的重设都会让锁屏按钮抖一下。
    func updateNowPlayingTitle(_ title: String) {
        guard hasNowPlayingSession else { return }
        var info = MPNowPlayingInfoCenter.default().nowPlayingInfo ?? [:]
        info[MPMediaItemPropertyTitle] = title
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
    }

    /// 暂停：**只翻状态，不拆会话**。
    ///
    /// 锁屏媒体卡片、远程命令、静音保活轨全部保留——这三样东西留着，App 才能在
    /// 锁屏下继续存活、用户才点得到「继续播」。之前锁屏按暂停直接走的是
    /// `endNowPlayingSession()`，把音频整个停掉，而 App 在后台唯一的存活理由就是
    /// 「正在播音频」：音频一停 iOS 立刻挂起它，卡片也没了，用户看到的就是
    /// 「点了暂停整个 App 就退出了」。
    func pauseNowPlayingSession() {
        stopCurrentPlayback()
        guard hasNowPlayingSession else { return }
        var info = MPNowPlayingInfoCenter.default().nowPlayingInfo ?? [:]
        info[MPNowPlayingInfoPropertyPlaybackRate] = 0.0
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
        MPNowPlayingInfoCenter.default().playbackState = .paused
    }

    /// 从暂停恢复：同样只翻状态。
    func resumeNowPlayingSession() {
        guard hasNowPlayingSession else { return }
        var info = MPNowPlayingInfoCenter.default().nowPlayingInfo ?? [:]
        info[MPNowPlayingInfoPropertyPlaybackRate] = 1.0
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
        MPNowPlayingInfoCenter.default().playbackState = .playing
    }

    /// 会话是否还在（暂停时仍为 true，只有真正结束才 false）。
    var isNowPlayingSessionActive: Bool { hasNowPlayingSession }

    /// 结束会话：锁屏媒体卡片消失，音频焦点还给别的 App。
    func endNowPlayingSession() {
        stopCurrentPlayback()
        guard hasNowPlayingSession else { return }
        hasNowPlayingSession = false
        stopKeepAlive()
        setRemoteCommandsEnabled(false)
        MPNowPlayingInfoCenter.default().playbackState = .stopped
        MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
        // 会话期间独占了音频（category 没开 .mixWithOthers），停下来就该让出去，
        // 否则用户切回音乐 App 会发现被我们压着。
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    /// 远程命令只在自动播放会话期间可用：常驻 enabled 的话，App 一启动锁屏就
    /// 可能出现一个什么都控制不了的媒体控件。
    private func setRemoteCommandsEnabled(_ enabled: Bool) {
        let center = MPRemoteCommandCenter.shared()
        center.playCommand.isEnabled = enabled
        center.pauseCommand.isEnabled = enabled
        center.nextTrackCommand.isEnabled = enabled
        center.previousTrackCommand.isEnabled = enabled
    }

    /// 注册锁屏「播放 / 暂停 / 上一首 / 下一首」的 target（只注册一次，启用与否
    /// 由 setRemoteCommandsEnabled 控制）。
    ///
    /// 这里不直接 import AutoplayController，而是发 Notification 让它自己去响应——
    /// Pronouncer 是个纯发音器，不该知道什么是「复习」「播放列表」。
    private func setupRemoteCommandCenter() {
        let center = MPRemoteCommandCenter.shared()
        center.playCommand.addTarget { _ in
            NotificationCenter.default.post(name: .pronouncerRemotePlay, object: nil)
            return .success
        }
        center.pauseCommand.addTarget { _ in
            NotificationCenter.default.post(name: .pronouncerRemotePause, object: nil)
            return .success
        }
        center.nextTrackCommand.addTarget { _ in
            NotificationCenter.default.post(name: .pronouncerRemoteNext, object: nil)
            return .success
        }
        center.previousTrackCommand.addTarget { _ in
            NotificationCenter.default.post(name: .pronouncerRemotePrevious, object: nil)
            return .success
        }
        setRemoteCommandsEnabled(false)
    }

    /// 仅当用户开启了「自动发音」时才朗读，供复习卡/单词详情出现时调用。
    func speakIfAutoplayEnabled(_ word: String) {
        guard PronunciationAutoplay.isEnabled else { return }
        speak(word)
    }

    func speak(_ word: String) {
        activateSessionIfNeeded()
        let accent = PronunciationAccent.current
        let trimmed = word.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            playingWord = nil
            return
        }
        stopCurrentPlayback()
        let requestID = UUID()
        playbackRequestID = requestID
        playingWord = trimmed.lowercased()

        fetchAndPlay(
            trimmed,
            chain: [.youdao],
            accent: accent,
            purpose: .word,
            requestID: requestID
        )
    }

    /// 自动播放专用的整句发音。例句始终使用 MiniMax 整句 TTS，才能保留自然的
    /// 连读、停顿和重音；有道的 dictvoice 不支持完整句子。
    func speakExampleSentence(_ sentence: String) {
        activateSessionIfNeeded()
        let trimmed = sentence.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            playingWord = nil
            return
        }
        stopCurrentPlayback()
        let requestID = UUID()
        playbackRequestID = requestID
        playingWord = trimmed.lowercased()
        fetchAndPlay(
            trimmed,
            chain: [.minimax],
            accent: PronunciationAccent.current,
            purpose: .sentence,
            requestID: requestID
        )
    }

    /// 沿降级链依次尝试；全部失败时结束本次播放，让自动播放可以继续往下走。
    private func fetchAndPlay(
        _ word: String,
        chain: [PronunciationSource],
        accent: PronunciationAccent,
        purpose: PronunciationPurpose,
        requestID: UUID
    ) {
        guard playbackRequestID == requestID else { return }
        guard let source = chain.first else {
            handleFinished()
            return
        }
        let rest = Array(chain.dropFirst())

        if let data = cachedAudio(for: word, source: source, accent: accent, purpose: purpose) {
            play(data, purpose: purpose)
            return
        }
        guard let request = remoteRequest(for: word, source: source, accent: accent) else {
            fetchAndPlay(
                word,
                chain: rest,
                accent: accent,
                purpose: purpose,
                requestID: requestID
            )
            return
        }

        let task = session.dataTask(with: request) { [weak self] data, response, error in
            if (error as? URLError)?.code == .cancelled { return }
            let http = response as? HTTPURLResponse
            // 查不到的词部分源会返回 200 但空 body / 非音频，用非空 + 2xx 双重判断。
            guard let data, !data.isEmpty, (200..<300).contains(http?.statusCode ?? 0) else {
                Task { @MainActor in
                    guard let self, self.playbackRequestID == requestID else { return }
                    self.fetchAndPlay(
                        word,
                        chain: rest,
                        accent: accent,
                        purpose: purpose,
                        requestID: requestID
                    )
                }
                return
            }
            Task { @MainActor in
                guard let self, self.playbackRequestID == requestID else { return }
                self.cacheAudio(data, for: word, source: source, accent: accent, purpose: purpose)
                self.play(data, purpose: purpose)
            }
        }
        requestTask = task
        task.resume()
    }

    /// 播放真正结束或所有远程源均失败时清空 playingWord，波纹动效跟着停止。
    ///
    /// 自动播放状态机（ReviewViewModel.runAutoplayLoop）通过 polling
    /// `Pronouncer.shared.playingWord` 探测音频结束，不在这里挂回调——保持
    /// Pronouncer 不依赖具体业务（它本来就不该知道什么是"复习"）。
    fileprivate func handleFinished() {
        playingWord = nil
    }

    /// 停止当前发音并取消尚未完成的远程音频请求。Tab 切换时必须同时取消请求，
    /// 否则页面虽然已经离开，旧请求返回后仍会延迟开始播放。
    func stopCurrentPlayback() {
        playbackRequestID = UUID()
        requestTask?.cancel()
        requestTask = nil
        player?.stop()
        player = nil
        playingWord = nil
    }

    private func remoteRequest(
        for word: String,
        source: PronunciationSource,
        accent: PronunciationAccent
    ) -> URLRequest? {
        guard let url = remoteURL(for: word, source: source, accent: accent) else { return nil }
        var request = URLRequest(url: url)
        request.setValue("audio/mpeg", forHTTPHeaderField: "Accept")
        // 走后端的 MiniMax 源需要登录 token。
        if source.usesBackend, let token = KeychainStore.loadToken() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    private func remoteURL(
        for word: String,
        source: PronunciationSource,
        accent: PronunciationAccent
    ) -> URL? {
        switch source {
        case .youdao:
            var components = URLComponents(string: "https://dict.youdao.com/dictvoice")
            components?.queryItems = [
                URLQueryItem(name: "audio", value: word),
                URLQueryItem(name: "type", value: String(accent.youdaoType)),
            ]
            return components?.url
        case .minimax:
            // 走本项目后端 /vocabulary/tts，由服务端调用 MiniMax（key 不下发到 App）。
            let base = AppConfig.baseURL.appendingPathComponent(AppConfig.apiPrefix + "/tts")
            var components = URLComponents(url: base, resolvingAgainstBaseURL: false)
            components?.queryItems = [
                URLQueryItem(name: "word", value: word),
                URLQueryItem(name: "accent", value: accent == .uk ? "uk" : "us"),
                // 服务端/CDN 缓存按 URL 区分；升级到 44.1kHz / 256kbps + fluent 后
                // 更新版本，避免命中旧的低码率例句音频。
                URLQueryItem(name: "voice_profile", value: "sentence-hq-fluent-v2"),
            ]
            return components?.url
        }
    }

    private func play(_ data: Data, purpose: PronunciationPurpose) {
        requestTask = nil
        player?.stop()
        do {
            let newPlayer = try AVAudioPlayer(data: data)
            newPlayer.delegate = delegate
            // Apple 要求 enableRate 必须在 prepareToPlay() 前打开。显式预缓冲后
            // 再设置 rate，避免由 play() 隐式准备时难以判断倍率是否真正进入播放器。
            newPlayer.enableRate = true
            guard newPlayer.prepareToPlay() else {
                handleFinished()
                return
            }
            newPlayer.rate = PronunciationRate.current.playbackRate(for: purpose)
            player = newPlayer
            guard newPlayer.play() else {
                player = nil
                handleFinished()
                return
            }
        } catch {
            // 缓存损坏或响应并非有效音频时结束本次播放；不再回退到已删除的系统语音。
            handleFinished()
        }
    }

    // MARK: - 本地缓存

    private var cacheDirectory: URL? {
        let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
        guard let dir = base?.appendingPathComponent("word_pronunciation", isDirectory: true) else { return nil }
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    /// 缓存文件名按「词 + 发音源 + 口音」区分，大小写不敏感（避免 Apple / apple 各存
    /// 一份，也避免不同源/口音的音频互相覆盖）。
    private func cacheURL(
        for word: String,
        source: PronunciationSource,
        accent: PronunciationAccent,
        purpose: PronunciationPurpose
    ) -> URL? {
        // 保留旧的单词缓存 key；只有例句增加命名空间，升级后不需要重下全部单词音频。
        let namespace = purpose == .sentence ? "sentence_" : ""
        // MiniMax 例句已升级到 44.1kHz / 256kbps + fluent；缓存版本同步递增，
        // 防止升级后继续播放本地旧的低码率文件。有道单词音频继续复用原缓存。
        let sourceVersion = source == .minimax ? "_sentence_hq_fluent_v2" : ""
        let key = "\(namespace)\(word.lowercased())_\(source.rawValue)\(sourceVersion)_\(accent.rawValue)"
        let safe = key.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? key
        return cacheDirectory?.appendingPathComponent("\(safe).mp3")
    }

    private func cachedAudio(
        for word: String,
        source: PronunciationSource,
        accent: PronunciationAccent,
        purpose: PronunciationPurpose
    ) -> Data? {
        guard let url = cacheURL(
            for: word, source: source, accent: accent, purpose: purpose
        ) else { return nil }
        return try? Data(contentsOf: url)
    }

    private func cacheAudio(
        _ data: Data,
        for word: String,
        source: PronunciationSource,
        accent: PronunciationAccent,
        purpose: PronunciationPurpose
    ) {
        guard let url = cacheURL(
            for: word, source: source, accent: accent, purpose: purpose
        ) else { return }
        try? data.write(to: url, options: .atomic)
    }
}

/// 桥接 AVAudioPlayer 的播放结束回调到 Pronouncer.handleFinished()，
/// 驱动按钮的播放态动画在音频真正读完时才停，而不是猜一个固定时长。
private final class PlaybackDelegate: NSObject, AVAudioPlayerDelegate {
    private weak var owner: Pronouncer?
    init(owner: Pronouncer) { self.owner = owner }

    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor [owner] in owner?.handleFinished() }
    }

    func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        Task { @MainActor [owner] in owner?.handleFinished() }
    }
}

struct PronounceButton: View {
    let word: String
    @ObservedObject private var pronouncer = Pronouncer.shared
    @State private var tapPulse = false

    private var isPlaying: Bool {
        pronouncer.playingWord == word.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

    var body: some View {
        // 图标按钮必须带文本标签才对 VoiceOver 友好，.labelStyle(.iconOnly) 保留视觉上
        // 只显示图标，但 VoiceOver 仍能读出"发音"。frame 保证达到 44x44 的最小点按区域
        // （生词库/复习卡片里这个按钮经常挨着别的文字，图标本身远小于 44pt）。
        Button("发音", systemImage: "speaker.wave.2.fill") {
            // 点击瞬间的回弹反馈，跟"是否正在播放"的波纹动效是两回事——不管这次播放
            // 最终成不成功，点下去那一下都应该有反馈。
            tapPulse = true
            pronouncer.speak(word)
        }
        .labelStyle(.iconOnly)
        // 播放时喇叭波纹用系统内置的 variableColor 动效，跟着共享的 playingWord 状态
        // 自动开关——不管这次播放是点这个按钮触发的，还是别处代码直接调 speak() 触发的
        // （比如复习卡片切到下一个词自动读音），只要词对得上就会动。
        .symbolEffect(.variableColor.iterative, isActive: isPlaying)
        .scaleEffect(tapPulse ? 1.25 : 1.0)
        .foregroundStyle(Theme.accent)
        .frame(minWidth: 44, minHeight: 44)
        .contentShape(.rect)
        .buttonStyle(.plain)
        .animation(.spring(response: 0.2, dampingFraction: 0.4), value: tapPulse)
        .onChange(of: tapPulse) { _, newValue in
            guard newValue else { return }
            Task {
                try? await Task.sleep(for: .milliseconds(150))
                tapPulse = false
            }
        }
    }
}
