// Views/Components/PronounceButton.swift
import AVFoundation
import SwiftUI

/// 发音口音偏好（存 UserDefaults，设置页可切换）。
///
/// 之前这里是「男声/女声」，因为老实现用系统合成语音 `AVSpeechSynthesizer`，
/// 发音本身不准、而且和拍照识别时 LLM 生成的音标（不区分口音）对不上，选英/美
/// 口音只会误导用户。现在改成拉取有道词典的真人发音音频（`dictvoice`），口音是
/// 音频文件里实打实的区别，所以把选项换回**英音/美音**才真正有意义。
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
/// 有道音频用 `AVAudioPlayer` 的倍速播放实现，不必按语速重新拉流、也不影响缓存
/// （同一份 mp3 变速播放即可）；系统合成语音兜底时换算成对应的 utterance rate。
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
    var playbackRate: Float {
        switch self {
        case .slow: return 0.75
        case .normal: return 1.0
        case .fast: return 1.35
        }
    }

    /// 系统合成语音兜底时的 `utterance.rate`（0…1，默认约 0.5），按同样的快慢
    /// 换算并夹紧到系统允许区间。
    var synthesizerRate: Float {
        let base = AVSpeechUtteranceDefaultSpeechRate
        let scaled: Float
        switch self {
        case .slow: scaled = base * 0.7
        case .normal: scaled = base
        case .fast: scaled = base * 1.3
        }
        return min(max(scaled, AVSpeechUtteranceMinimumSpeechRate), AVSpeechUtteranceMaximumSpeechRate)
    }
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

/// 发音源偏好（存 UserDefaults，设置页可切换）。
///
/// 不同来源音质/风格不同，用户可按喜好选：
/// - `youdao`：有道词典音，常见词是真人录音、生僻词退化成合成（"不正宗"多来自这些）。
/// - `google`：Google 翻译 TTS，神经网络合成，咬字清晰、任意词都有、风格统一。
/// - `system`：Apple 系统语音，优先选已安装的「优质/增强」神经语音，完全离线、最自然，
///   但若系统里没下载优质语音会退化成默认合成音（需到系统设置里下载）。
/// - `azure`：高清——Azure 神经 TTS，经后端中转（key 只在服务端）。质量稳定地高一档、
///   词句通吃；后端未配置 Azure key 时会 503，客户端回退到系统合成音。
enum PronunciationSource: String, CaseIterable {
    case youdao
    case google
    case system
    case azure

    static var current: PronunciationSource {
        get {
            let raw = UserDefaults.standard.string(forKey: "pronunciation_source") ?? youdao.rawValue
            return PronunciationSource(rawValue: raw) ?? .youdao
        }
        set {
            UserDefaults.standard.set(newValue.rawValue, forKey: "pronunciation_source")
        }
    }

    /// 是否走本地系统合成（不联网、不缓存 mp3）。
    var isSystem: Bool { self == .system }

    /// 是否走本项目后端（需带登录 token）。目前只有 azure「高清」源。
    var usesBackend: Bool { self == .azure }
}

/// 单词发音播放器（单例）。
///
/// 数据源是有道词典发音接口 `https://dict.youdao.com/dictvoice?audio=<词>&type=<1|2>`，
/// 返回真人/词典级 mp3，重音准确、无需 key。首次播放后把音频缓存到 Caches 目录，
/// 再次点击直接读本地文件，几乎零延迟。网络失败时回退到系统合成语音，保证离线
/// 也能出声。
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
    /// 网络失败时的离线兜底。
    private let synthesizer = AVSpeechSynthesizer()
    private let session = URLSession(configuration: .default)
    private lazy var delegate = PlaybackDelegate(owner: self)

    /// 不配置 AVAudioSession 的话，手机静音开关打开时会完全不出声——这是点小喇叭
    /// 没反应最常见的原因。用 `.playback` 类别让发音像音乐/视频一样忽略静音开关。
    private lazy var configured: Void = {
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .default, options: [])
        try? AVAudioSession.sharedInstance().setActive(true)
    }()

    /// 仅当用户开启了「自动发音」时才朗读，供复习卡/单词详情出现时调用。
    func speakIfAutoplayEnabled(_ word: String) {
        guard PronunciationAutoplay.isEnabled else { return }
        speak(word)
    }

    func speak(_ word: String) {
        _ = configured
        let source = PronunciationSource.current
        let accent = PronunciationAccent.current
        let trimmed = word.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            playingWord = nil
            return
        }
        playingWord = trimmed.lowercased()

        // 系统优质语音：本地合成，不联网、不缓存 mp3。
        if source.isSystem {
            speakWithSynthesizer(trimmed)
            return
        }

        if let data = cachedAudio(for: trimmed, source: source, accent: accent) {
            play(data, fallbackWord: trimmed)
            return
        }
        guard let request = remoteRequest(for: trimmed, source: source, accent: accent) else {
            speakWithSynthesizer(trimmed)
            return
        }

        session.dataTask(with: request) { [weak self] data, response, _ in
            let http = response as? HTTPURLResponse
            // 查不到的词部分源会返回 200 但空 body / 非音频，用非空 + 2xx 双重判断，
            // 失败一律回退系统合成音，保证点了一定有声。
            guard let data, !data.isEmpty, (200..<300).contains(http?.statusCode ?? 0) else {
                Task { @MainActor in self?.speakWithSynthesizer(trimmed) }
                return
            }
            self?.cacheAudio(data, for: trimmed, source: source, accent: accent)
            Task { @MainActor in self?.play(data, fallbackWord: trimmed) }
        }.resume()
    }

    /// 播放真正结束（AVAudioPlayerDelegate / AVSpeechSynthesizerDelegate 回调）时清空
    /// playingWord，波纹动效跟着停。不在这里做"打断上一个"的特殊处理——播放新词前
    /// player?.stop()/synthesizer.stopSpeaking() 已经会触发旧 delegate 回调，自然把
    /// playingWord 清成 nil，再被下面 speak() 里设的新值覆盖，顺序上没有竞态。
    fileprivate func handleFinished() {
        playingWord = nil
    }

    private func remoteRequest(for word: String, source: PronunciationSource, accent: PronunciationAccent) -> URLRequest? {
        guard let url = remoteURL(for: word, source: source, accent: accent) else { return nil }
        var request = URLRequest(url: url)
        // Google TTS 不带常见 UA 时可能 403；统一带一个桌面 UA，对其它源无害。
        request.setValue("Mozilla/5.0", forHTTPHeaderField: "User-Agent")
        // 走后端的源（azure「高清」）需要登录 token。
        if source.usesBackend, let token = KeychainStore.loadToken() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    private func remoteURL(for word: String, source: PronunciationSource, accent: PronunciationAccent) -> URL? {
        switch source {
        case .youdao:
            var components = URLComponents(string: "https://dict.youdao.com/dictvoice")
            components?.queryItems = [
                URLQueryItem(name: "audio", value: word),
                URLQueryItem(name: "type", value: String(accent.youdaoType)),
            ]
            return components?.url
        case .google:
            // client=tw-ob 免 token；tl 指定语言，英音传 en-gb，其余用 en（偏美音）。
            var components = URLComponents(string: "https://translate.google.com/translate_tts")
            components?.queryItems = [
                URLQueryItem(name: "ie", value: "UTF-8"),
                URLQueryItem(name: "client", value: "tw-ob"),
                URLQueryItem(name: "tl", value: accent == .uk ? "en-gb" : "en"),
                URLQueryItem(name: "q", value: word),
            ]
            return components?.url
        case .azure:
            // 走本项目后端 /vocabulary/tts，由服务端调 Azure（key 不下发到 App）。
            let base = AppConfig.baseURL.appendingPathComponent(AppConfig.apiPrefix + "/tts")
            var components = URLComponents(url: base, resolvingAgainstBaseURL: false)
            components?.queryItems = [
                URLQueryItem(name: "word", value: word),
                URLQueryItem(name: "accent", value: accent == .uk ? "uk" : "us"),
            ]
            return components?.url
        case .system:
            return nil  // 系统语音走本地合成，不联网
        }
    }

    private func play(_ data: Data, fallbackWord: String) {
        player?.stop()
        do {
            let newPlayer = try AVAudioPlayer(data: data)
            newPlayer.delegate = delegate
            // enableRate 必须在 play() 前打开，rate 才会生效（同一份 mp3 变速播放）。
            newPlayer.enableRate = true
            newPlayer.rate = PronunciationRate.current.playbackRate
            player = newPlayer
            newPlayer.play()
        } catch {
            // 缓存文件损坏或格式异常时兜底，保证点了小喇叭一定有声音。
            speakWithSynthesizer(fallbackWord)
        }
    }

    private func speakWithSynthesizer(_ word: String) {
        let utterance = AVSpeechUtterance(string: word)
        utterance.voice = bestEnglishVoice(PronunciationAccent.current)
        utterance.rate = PronunciationRate.current.synthesizerRate
        synthesizer.delegate = delegate
        synthesizer.stopSpeaking(at: .immediate)
        synthesizer.speak(utterance)
    }

    /// 选目标口音下音质最好的英语语音：优先「优质(premium)」，其次「增强(enhanced)」，
    /// 再退回默认。系统语音源和联网失败兜底都用它，尽量自然。用户在系统设置里下载了
    /// 优质/增强英语语音后，这里会自动用上。
    private func bestEnglishVoice(_ accent: PronunciationAccent) -> AVSpeechSynthesisVoice? {
        let lang = accent == .uk ? "en-GB" : "en-US"
        let candidates = AVSpeechSynthesisVoice.speechVoices().filter { $0.language == lang }
        return candidates.first { $0.quality == .premium }
            ?? candidates.first { $0.quality == .enhanced }
            ?? candidates.first
            ?? AVSpeechSynthesisVoice(language: lang)
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
    private func cacheURL(for word: String, source: PronunciationSource, accent: PronunciationAccent) -> URL? {
        let key = "\(word.lowercased())_\(source.rawValue)_\(accent.rawValue)"
        let safe = key.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? key
        return cacheDirectory?.appendingPathComponent("\(safe).mp3")
    }

    private func cachedAudio(for word: String, source: PronunciationSource, accent: PronunciationAccent) -> Data? {
        guard let url = cacheURL(for: word, source: source, accent: accent) else { return nil }
        return try? Data(contentsOf: url)
    }

    private func cacheAudio(_ data: Data, for word: String, source: PronunciationSource, accent: PronunciationAccent) {
        guard let url = cacheURL(for: word, source: source, accent: accent) else { return }
        try? data.write(to: url, options: .atomic)
    }
}

/// 桥接 AVAudioPlayer / AVSpeechSynthesizer 的播放结束回调到 Pronouncer.handleFinished()，
/// 驱动按钮的播放态动画在音频真正读完时才停，而不是猜一个固定时长。
private final class PlaybackDelegate: NSObject, AVAudioPlayerDelegate, AVSpeechSynthesizerDelegate {
    private weak var owner: Pronouncer?
    init(owner: Pronouncer) { self.owner = owner }

    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor [owner] in owner?.handleFinished() }
    }

    func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        Task { @MainActor [owner] in owner?.handleFinished() }
    }

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        Task { @MainActor [owner] in owner?.handleFinished() }
    }

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
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
