// Services/SpeechRecognizer.swift
import AVFoundation
import Foundation
import Speech

/// 语音听写：录下用户说的单词并用 iOS 语音识别转成文字，交给 DictationJudge 判对错。
///
/// 只做「说 → 文字」这一件事，判定沿用现有的 DictationJudge（识别结果写进
/// ReviewViewModel.dictationInput，后续确认/判定链路完全不变）。做成
/// ObservableObject 而不是散在视图里，是因为「在不在听」「识别到什么」要驱动 UI
/// 上麦克风按钮的动效和实时文字，得是一份可观察的状态。
///
/// 音频会话：识别期间要切成 .playAndRecord 才能录音，结束后主动切回 .playback
/// 还给 Pronouncer——发音和录音抢的是同一个 AVAudioSession，不还回去下次点小喇叭
/// 可能没声音。
@MainActor
final class SpeechRecognizer: ObservableObject {
    /// 是否正在听（录音+识别中），驱动麦克风按钮的动效。
    @Published private(set) var isListening = false
    /// 实时识别到的文字（partial + final 都往这里更新）。
    @Published private(set) var transcript = ""
    /// 出错或权限被拒时的提示，供 UI 展示。
    @Published private(set) var errorMessage: String?

    /// 英文听写固定用 en-US。识别器在部分机型/语言包缺失时可能为 nil。
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private let audioEngine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?

    /// 识别器当前是否可用（网络/语言包等原因可能暂时不可用）。
    var isAvailable: Bool { recognizer?.isAvailable ?? false }

    /// 请求语音识别 + 麦克风两项权限，任一被拒都算失败。
    private func requestAuthorization() async -> Bool {
        let speechStatus = await withCheckedContinuation { cont in
            SFSpeechRecognizer.requestAuthorization { cont.resume(returning: $0) }
        }
        guard speechStatus == .authorized else { return false }
        return await withCheckedContinuation { cont in
            AVAudioApplication.requestRecordPermission { cont.resume(returning: $0) }
        }
    }

    /// 开始一次语音听写：申请权限 → 配录音会话 → 启动引擎与识别任务。
    /// 识别结果（含中途 partial）实时写进 transcript；拿到 final 或出错自动停止。
    func start() async {
        guard !isListening else { return }
        errorMessage = nil
        transcript = ""

        guard await requestAuthorization() else {
            errorMessage = "需要麦克风和语音识别权限，可在系统设置里开启"
            return
        }
        guard let recognizer, recognizer.isAvailable else {
            errorMessage = "语音识别暂不可用，请稍后再试"
            return
        }

        // 录音要用输入设备，先把正在播放的发音停掉，避免占着音频链路。
        Pronouncer.shared.stopCurrentPlayback()

        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .measurement, options: [.duckOthers, .defaultToSpeaker])
            try session.setActive(true, options: .notifyOthersOnDeactivation)

            let request = SFSpeechAudioBufferRecognitionRequest()
            request.shouldReportPartialResults = true
            // 听写只要词本身，别让系统自动加标点。
            if #available(iOS 16.0, *) { request.addsPunctuation = false }
            // 有本地识别能力就用本地：更快、离线、不上传音频。
            if recognizer.supportsOnDeviceRecognition { request.requiresOnDeviceRecognition = true }
            self.request = request

            let inputNode = audioEngine.inputNode
            let format = inputNode.outputFormat(forBus: 0)
            inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak request] buffer, _ in
                request?.append(buffer)
            }
            audioEngine.prepare()
            try audioEngine.start()
            isListening = true

            task = recognizer.recognitionTask(with: request) { [weak self] result, error in
                Task { @MainActor in
                    guard let self else { return }
                    if let result {
                        self.transcript = result.bestTranscription.formattedString
                        if result.isFinal { self.stop() }
                    }
                    if error != nil { self.stop() }
                }
            }
        } catch {
            errorMessage = "无法启动录音，请重试"
            stop()
        }
    }

    /// 停止录音与识别，并把音频会话切回 .playback 还给发音播放器。
    /// 可重复调用（识别 final 回调和用户手动点按可能都会触发）。
    func stop() {
        if audioEngine.isRunning {
            audioEngine.stop()
            audioEngine.inputNode.removeTap(onBus: 0)
        }
        request?.endAudio()
        task?.cancel()
        request = nil
        task = nil
        isListening = false
        // 把类别切回发音用的 .playback；Pronouncer 下次发音会自己 setActive。
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .spokenAudio, options: [])
    }
}
