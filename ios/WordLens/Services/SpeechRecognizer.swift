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
    /// 是否已经在 inputNode 上装过 tap。启动中途抛错时也要能准确拆掉，
    /// 否则下次 start 会重复安装 tap 直接崩。
    private var hasTap = false

    /// 识别时提示「会出现孤立字母」的上下文词表，只有 A–Z。
    private static let letterContext: [String] = (UnicodeScalar("A").value...UnicodeScalar("Z").value)
        .compactMap { UnicodeScalar($0).map { String(Character($0)) } }

    /// 停止说话后多久自动收音。流式识别的 isFinal 往往要等 endAudio 才来，
    /// 光靠它按钮会一直停在「正在听」，所以自己做静音判定。
    ///
    /// 2 秒是为拼读留的余量：逐个字母念时字母之间本来就有停顿，卡到 1.5 秒会在
    /// 用户还没拼完时就把麦克风关了。
    private static let silenceTimeout: Duration = .seconds(2)
    /// 全程一个字都没识别到时的兜底上限，避免麦克风无限开着。
    private static let maxListeningDuration: Duration = .seconds(15)

    private var silenceTask: Task<Void, Never>?
    private var timeoutTask: Task<Void, Never>?

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
    ///
    /// - Parameter forceOnDevice: 强制走本地模型。正常路径优先用云端（准确率明显更高），
    ///   只有云端识别失败（多半是断网）时才由内部回退调用一次，带上 true。
    func start(forceOnDevice: Bool = false) async {
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
            // 用 .default 而不是 .measurement：.measurement 会关掉系统的输入信号处理
            // （增益、降噪），手机拿在手上说话时录到的信号偏弱，识别准确率反而更差。
            try session.setCategory(.playAndRecord, mode: .default, options: [.duckOthers, .defaultToSpeaker])
            try session.setActive(true, options: .notifyOthersOnDeactivation)

            let request = SFSpeechAudioBufferRecognitionRequest()
            request.shouldReportPartialResults = true
            // 听写只要词本身，别让系统自动加标点。
            if #available(iOS 16.0, *) { request.addsPunctuation = false }
            // 关键：告诉识别器这是「一个短词」而不是「一段口述」。默认的 .unspecified
            // 会套用连续语流的语言模型，把孤立的单词硬拗成通顺的句子片段
            // （说 E 出来 he、说 bit 出来 be it），.search 面向短查询词，最贴近听写。
            request.taskHint = .search
            // 告诉识别器「这里会出现孤立的字母」。注意这里喂的只有 A–Z，不含任何
            // 待听写的单词——它提升的是字母识别率，不泄露答案，听写该错还是错。
            request.contextualStrings = Self.letterContext
            // 云端模型比本地模型准得多，默认走云端；只有云端失败才回退本地。
            request.requiresOnDeviceRecognition = forceOnDevice && recognizer.supportsOnDeviceRecognition
            self.request = request

            let inputNode = audioEngine.inputNode
            let format = inputNode.outputFormat(forBus: 0)
            inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak request] buffer, _ in
                request?.append(buffer)
            }
            hasTap = true
            audioEngine.prepare()
            try audioEngine.start()
            isListening = true

            // 兜底：一直没说话（或识别不出）也要自己关掉。
            timeoutTask = Task { [weak self] in
                try? await Task.sleep(for: Self.maxListeningDuration)
                guard !Task.isCancelled else { return }
                self?.stop()
            }

            task = recognizer.recognitionTask(with: request) { [weak self] result, error in
                Task { @MainActor in
                    guard let self else { return }
                    if let result {
                        self.transcript = Self.sanitize(result.bestTranscription.formattedString)
                        if result.isFinal {
                            self.stop()
                        } else {
                            // 每来一段新识别就把静音计时器往后推，直到用户真的说完。
                            self.scheduleSilenceStop()
                        }
                    }
                    if error != nil {
                        // isListening 已经是 false，说明是用户/静音判定主动停的，
                        // cancel 带出来的这个 error 不是真故障，别当失败处理。
                        guard self.isListening else { return }
                        self.stop()
                        // 云端识别失败（常见于断网）时，退到本地模型重试一次。
                        if !forceOnDevice, self.transcript.isEmpty,
                           self.recognizer?.supportsOnDeviceRecognition == true {
                            Task { await self.start(forceOnDevice: true) }
                        }
                    }
                }
            }
        } catch {
            errorMessage = "无法启动录音，请重试"
            stop()
        }
    }

    /// 清掉识别结果里的标点和多余空白：即使关了 addsPunctuation，云端偶尔还是会
    /// 带出 "E." "apple," 这种尾巴，直接进判定就成了拼写错误。只保留字母、连字符、
    /// 撇号和词间空格（复合词要用）。
    static func sanitize(_ text: String) -> String {
        let kept = text.map { ch -> Character in
            (ch.isLetter || ch == "-" || ch == "'") ? ch : " "
        }
        return String(kept)
            .split(separator: " ")
            .joined(separator: " ")
    }

    /// 静音 N 秒后自动收音；期间每来一次新的识别结果都会重置这个计时。
    private func scheduleSilenceStop() {
        silenceTask?.cancel()
        silenceTask = Task { [weak self] in
            try? await Task.sleep(for: Self.silenceTimeout)
            guard !Task.isCancelled else { return }
            self?.stop()
        }
    }

    /// 停止录音与识别，并把音频会话切回 .playback 还给发音播放器。
    /// 可重复调用（静音自动停、识别 final 回调、用户手动点按都会触发）。
    func stop() {
        silenceTask?.cancel()
        silenceTask = nil
        timeoutTask?.cancel()
        timeoutTask = nil

        if audioEngine.isRunning { audioEngine.stop() }
        if hasTap {
            audioEngine.inputNode.removeTap(onBus: 0)
            hasTap = false
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
