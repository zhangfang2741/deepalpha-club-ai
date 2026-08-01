// Services/TextRecognizer.swift
import Foundation
import ImageIO
import UIKit
@preconcurrency import Vision

/// 本地文字识别（Apple Vision OCR）。
///
/// 混合识别方案的客户端一环：印刷体的 OCR 用系统 `Vision` 做，又快又准、离线、
/// 免流量，识别质量明显好过让通用 LLM 直接看图。抠出候选英语单词后随图片一起
/// 传给后端 `/recognize`（`ocr_words` 参数），跟视觉 LLM 自己看图的结果取并集。
enum TextRecognizer {
    /// 对图片做 OCR 并抽取候选英语单词（大小写不敏感去重，最多 100 个）。
    ///
    /// OCR 抠不到任何词时返回空数组，调用方据此回退到「让 LLM 直接看图识别」，
    /// 保证模糊/手写等 Vision 不擅长的场景不漏。
    /// OCR 的兜底超时。Vision 正常几百毫秒就返回，超过这个时间基本可以认定
    /// 它卡住了——而 OCR 只是"锦上添花"的参考线索，超时就交空数组给后端退化成
    /// 纯看图识别，识别质量略降但流程不断。
    ///
    /// 没有这道兜底时的实际后果：调用方已经把 `isRecognizing` 置成 true，扫描
    /// 动画在转，但请求还没发出去——Vision 一卡就是"一直转、没进度、没结果、
    /// 也不报错"，用户完全看不出发生了什么。
    static let ocrTimeout: TimeInterval = 8

    static func recognizeWords(from imageData: Data) async -> [String] {
        guard let image = UIImage(data: imageData) else { return [] }
        return await recognizeWords(from: image)
    }

    static func recognizeWords(from image: UIImage, timeout: TimeInterval = ocrTimeout) async -> [String] {
        guard let cgImage = image.cgImage else { return [] }
        let orientation = CGImagePropertyOrientation(image.imageOrientation)
        let lines: [String] = await withCheckedContinuation { continuation in
            // 三个来源（识别完成 / perform 抛错 / 超时）竞争同一个 continuation，
            // 谁先到谁算数。多次 resume 是 Swift 运行时的致命错误，必须加锁去重。
            let resumer = SingleResumer(continuation)

            let request = VNRecognizeTextRequest { request, _ in
                let observations = request.results as? [VNRecognizedTextObservation] ?? []
                resumer.resume(with: observations.flatMap { $0.topCandidates(3).map(\.string) })
            }
            // .accurate 对印刷体识别率最高；开启语言纠正减少 OCR 拼写噪声。
            request.recognitionLevel = .accurate
            request.usesLanguageCorrection = true
            request.recognitionLanguages = ["en-US"]

            let handler = VNImageRequestHandler(cgImage: cgImage, orientation: orientation, options: [:])
            // perform 是同步阻塞调用，丢到后台队列，别卡住调用方（通常是主线程）。
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    try handler.perform([request])
                } catch {
                    resumer.resume(with: [])
                }
            }

            // 超时兜底。Vision 的 perform 不响应取消，超时后它那条后台线程还会
            // 跑完，但结果会被 SingleResumer 丢弃，不影响已经继续往下走的主流程。
            DispatchQueue.global(qos: .userInitiated).asyncAfter(deadline: .now() + timeout) {
                resumer.resume(with: [])
            }
        }

        return tokenize(lines)
    }

    /// 把 OCR 出来的整行文字拆成单词：只保留英文字母（含中间的连字符/撇号，如
    /// well-being、don't），过滤非英文与过短噪声，大小写不敏感去重。虚词的进一步
    /// 剔除和原形还原交给后端 LLM，这里只做粗筛。
    private static func tokenize(_ lines: [String]) -> [String] {
        var seen = Set<String>()
        var result: [String] = []
        for line in lines {
            let tokens = line.split { !($0.isLetter || $0 == "-" || $0 == "'") }
            for token in tokens {
                let word = String(token).trimmingCharacters(in: CharacterSet(charactersIn: "-'"))
                guard word.count >= 2 else { continue }
                // 必须全是 ASCII 字母（加连字符/撇号），滤掉混进来的非英文字符。
                guard word.allSatisfy({ ($0.isLetter && $0.isASCII) || $0 == "-" || $0 == "'" }) else { continue }
                let key = word.lowercased()
                if seen.insert(key).inserted {
                    result.append(word)
                    if result.count >= 100 { return result }
                }
            }
        }
        return result
    }
}

/// 保证 `CheckedContinuation` 只被 resume 一次。
///
/// Vision 的完成回调、`perform` 的抛错分支和超时定时器分别跑在不同线程上，都
/// 可能先到；`CheckedContinuation` 被 resume 第二次会直接 crash，所以用锁 +
/// 标志位做一次性闸门。
private final class SingleResumer: @unchecked Sendable {
    private let lock = NSLock()
    private var continuation: CheckedContinuation<[String], Never>?

    init(_ continuation: CheckedContinuation<[String], Never>) {
        self.continuation = continuation
    }

    func resume(with value: [String]) {
        lock.lock()
        let pending = continuation
        continuation = nil
        lock.unlock()
        pending?.resume(returning: value)
    }
}

private extension CGImagePropertyOrientation {
    init(_ orientation: UIImage.Orientation) {
        switch orientation {
        case .up:
            self = .up
        case .upMirrored:
            self = .upMirrored
        case .down:
            self = .down
        case .downMirrored:
            self = .downMirrored
        case .left:
            self = .left
        case .leftMirrored:
            self = .leftMirrored
        case .right:
            self = .right
        case .rightMirrored:
            self = .rightMirrored
        @unknown default:
            self = .up
        }
    }
}
