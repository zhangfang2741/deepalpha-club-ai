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

/// 单词发音播放器（单例）。
///
/// 数据源是有道词典发音接口 `https://dict.youdao.com/dictvoice?audio=<词>&type=<1|2>`，
/// 返回真人/词典级 mp3，重音准确、无需 key。首次播放后把音频缓存到 Caches 目录，
/// 再次点击直接读本地文件，几乎零延迟。网络失败时回退到系统合成语音，保证离线
/// 也能出声。
private enum Pronouncer {
    /// 必须持有强引用，否则 AVAudioPlayer 会被立即释放、还没出声就停了。
    private static var player: AVAudioPlayer?
    /// 网络失败时的离线兜底。
    private static let synthesizer = AVSpeechSynthesizer()
    private static let session = URLSession(configuration: .default)

    /// 不配置 AVAudioSession 的话，手机静音开关打开时会完全不出声——这是点小喇叭
    /// 没反应最常见的原因。用 `.playback` 类别让发音像音乐/视频一样忽略静音开关。
    /// `static let` 保证只在首次用到时配置一次。
    private static let configured: Void = {
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .default, options: [])
        try? AVAudioSession.sharedInstance().setActive(true)
    }()

    static func speak(_ word: String) {
        _ = configured
        let accent = PronunciationAccent.current
        let trimmed = word.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }

        if let data = cachedAudio(for: trimmed, accent: accent) {
            play(data, fallbackWord: trimmed)
            return
        }
        guard let url = remoteURL(for: trimmed, accent: accent) else {
            speakWithSynthesizer(trimmed)
            return
        }

        session.dataTask(with: url) { data, response, _ in
            let http = response as? HTTPURLResponse
            // 有道对查不到的词可能返回 200 但空 body，用非空 + 2xx 双重判断。
            guard let data, !data.isEmpty, (200..<300).contains(http?.statusCode ?? 0) else {
                DispatchQueue.main.async { speakWithSynthesizer(trimmed) }
                return
            }
            cacheAudio(data, for: trimmed, accent: accent)
            DispatchQueue.main.async { play(data, fallbackWord: trimmed) }
        }.resume()
    }

    private static func remoteURL(for word: String, accent: PronunciationAccent) -> URL? {
        var components = URLComponents(string: "https://dict.youdao.com/dictvoice")
        components?.queryItems = [
            URLQueryItem(name: "audio", value: word),
            URLQueryItem(name: "type", value: String(accent.youdaoType)),
        ]
        return components?.url
    }

    private static func play(_ data: Data, fallbackWord: String) {
        player?.stop()
        do {
            let newPlayer = try AVAudioPlayer(data: data)
            player = newPlayer
            newPlayer.play()
        } catch {
            // 缓存文件损坏或格式异常时兜底，保证点了小喇叭一定有声音。
            speakWithSynthesizer(fallbackWord)
        }
    }

    private static func speakWithSynthesizer(_ word: String) {
        let utterance = AVSpeechUtterance(string: word)
        let target = PronunciationAccent.current == .uk ? "en-GB" : "en-US"
        utterance.voice = AVSpeechSynthesisVoice(language: target)
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate
        synthesizer.stopSpeaking(at: .immediate)
        synthesizer.speak(utterance)
    }

    // MARK: - 本地缓存

    private static var cacheDirectory: URL? {
        let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
        guard let dir = base?.appendingPathComponent("word_pronunciation", isDirectory: true) else { return nil }
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    /// 缓存文件名按「词 + 口音」区分，大小写不敏感（避免 Apple / apple 各存一份）。
    private static func cacheURL(for word: String, accent: PronunciationAccent) -> URL? {
        let key = "\(word.lowercased())_\(accent.rawValue)"
        let safe = key.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? key
        return cacheDirectory?.appendingPathComponent("\(safe).mp3")
    }

    private static func cachedAudio(for word: String, accent: PronunciationAccent) -> Data? {
        guard let url = cacheURL(for: word, accent: accent) else { return nil }
        return try? Data(contentsOf: url)
    }

    private static func cacheAudio(_ data: Data, for word: String, accent: PronunciationAccent) {
        guard let url = cacheURL(for: word, accent: accent) else { return }
        try? data.write(to: url, options: .atomic)
    }
}

struct PronounceButton: View {
    let word: String

    var body: some View {
        // 图标按钮必须带文本标签才对 VoiceOver 友好，.labelStyle(.iconOnly) 保留视觉上
        // 只显示图标，但 VoiceOver 仍能读出"发音"。frame 保证达到 44x44 的最小点按区域
        // （生词库/复习卡片里这个按钮经常挨着别的文字，图标本身远小于 44pt）。
        Button("发音", systemImage: "speaker.wave.2.fill") {
            Pronouncer.speak(word)
        }
        .labelStyle(.iconOnly)
        .foregroundStyle(Theme.accent)
        .frame(minWidth: 44, minHeight: 44)
        .contentShape(.rect)
        .buttonStyle(.plain)
    }
}
