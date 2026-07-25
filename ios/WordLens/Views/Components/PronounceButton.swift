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
        let utterance = AVSpeechUtterance(string: word)
        utterance.voice = AVSpeechSynthesisVoice(language: PronunciationAccent.current.rawValue)
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate
        Speaker.synthesizer.stopSpeaking(at: .immediate)
        Speaker.synthesizer.speak(utterance)
    }
}
