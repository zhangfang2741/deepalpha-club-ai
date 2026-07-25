// Views/Components/PronounceButton.swift
import SwiftUI
import AVFoundation

/// 发音音色偏好（存 UserDefaults，设置页可切换）。
///
/// 之前是英式/美式选项，但音标是拍照识别时 LLM 一次性生成的，跟这个选项完全
/// 无关（详见 app/services/vocabulary/recognizer.py 的 prompt，没有区分口音），
/// 选它只会让用户误以为音标也会跟着变。系统 TTS 唯一真正受选项影响的是发音，
/// 所以换成男声/女声更符合实际效果。
enum PronunciationVoiceGender: String {
    case female
    case male

    static var current: PronunciationVoiceGender {
        get {
            let raw = UserDefaults.standard.string(forKey: "pronunciation_voice_gender") ?? female.rawValue
            return PronunciationVoiceGender(rawValue: raw) ?? .female
        }
        set {
            UserDefaults.standard.set(newValue.rawValue, forKey: "pronunciation_voice_gender")
        }
    }

    /// 优先选英式/美式英语里性别匹配的语音，找不到就退回系统默认 en-US 语音。
    var voice: AVSpeechSynthesisVoice? {
        let targetGender: AVSpeechSynthesisVoiceGender = self == .male ? .male : .female
        let candidates = AVSpeechSynthesisVoice.speechVoices().filter {
            $0.language.hasPrefix("en") && $0.gender == targetGender
        }
        return candidates.first { $0.language == "en-US" } ?? candidates.first
            ?? AVSpeechSynthesisVoice(language: "en-US")
    }
}

/// 单例合成器，避免每次点击都新建（新建会打断上一次朗读）。
private enum Speaker {
    static let synthesizer = AVSpeechSynthesizer()

    /// 不配置 AVAudioSession 的话，AVSpeechSynthesizer 默认走的类别在手机
    /// 静音开关打开时会完全不出声——这是最容易踩的坑，点小喇叭没反应通常
    /// 就是这个。用 `.playback` 类别让朗读像音乐/视频一样忽略静音开关。
    /// `static let` 保证只在首次用到 Speaker 时配置一次。
    private static let configured: Void = {
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .default, options: [])
        try? AVAudioSession.sharedInstance().setActive(true)
    }()

    static func ensureConfigured() {
        _ = configured
    }
}

struct PronounceButton: View {
    let word: String

    var body: some View {
        // 图标按钮必须带文本标签才对 VoiceOver 友好，.labelStyle(.iconOnly) 保留视觉上
        // 只显示图标，但 VoiceOver 仍能读出"发音"。frame 保证达到 44x44 的最小点按区域
        // （生词库/复习卡片里这个按钮经常挨着别的文字，图标本身远小于 44pt）。
        Button("发音", systemImage: "speaker.wave.2.fill", action: speak)
            .labelStyle(.iconOnly)
            .foregroundStyle(Theme.accent)
            .frame(minWidth: 44, minHeight: 44)
            .contentShape(.rect)
            .buttonStyle(.plain)
    }

    private func speak() {
        Speaker.ensureConfigured()
        let utterance = AVSpeechUtterance(string: word)
        utterance.voice = PronunciationVoiceGender.current.voice
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate
        Speaker.synthesizer.stopSpeaking(at: .immediate)
        Speaker.synthesizer.speak(utterance)
    }
}
