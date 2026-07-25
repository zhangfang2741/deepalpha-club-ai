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
    static func recognizeWords(from imageData: Data) async -> [String] {
        guard let image = UIImage(data: imageData) else { return [] }
        return await recognizeWords(from: image)
    }

    static func recognizeWords(from image: UIImage) async -> [String] {
        guard let cgImage = image.cgImage else { return [] }
        let orientation = CGImagePropertyOrientation(image.imageOrientation)
        let lines: [String] = await withCheckedContinuation { continuation in
            let request = VNRecognizeTextRequest { request, _ in
                let observations = request.results as? [VNRecognizedTextObservation] ?? []
                let texts = observations.flatMap { $0.topCandidates(3).map(\.string) }
                continuation.resume(returning: texts)
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
                    continuation.resume(returning: [])
                }
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
