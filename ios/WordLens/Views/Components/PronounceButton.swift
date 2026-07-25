// Views/Components/PronounceButton.swift
import SwiftUI
import AVFoundation

/// 发音偏好（存 UserDefaults，设置页可切换）。
enum PronunciationAccent: String {
    case american = "en-US"
    case british = "en-GB"

    static var current: PronunciationAccent {
        get {
            let raw = UserDefaults.standard.string(forKey: "pronunciation_accent") ?? american.rawValue
            return PronunciationAccent(rawValue: raw) ?? .american
        }
        set {
            UserDefaults.standard.set(newValue.rawValue, forKey: "pronunciation_accent")
        }
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
        Button {
            speak()
        } label: {
            Image(systemName: "speaker.wave.2.fill")
                .foregroundColor(Theme.accent)
        }
        .buttonStyle(.plain)
    }

    private func speak() {
        Speaker.ensureConfigured()
        let utterance = AVSpeechUtterance(string: word)
        utterance.voice = AVSpeechSynthesisVoice(language: PronunciationAccent.current.rawValue)
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate
        Speaker.synthesizer.stopSpeaking(at: .immediate)
        Speaker.synthesizer.speak(utterance)
    }
}
