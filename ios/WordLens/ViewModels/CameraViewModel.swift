// ViewModels/CameraViewModel.swift
import Foundation
import SwiftUI
import UIKit

@MainActor
final class CameraViewModel: ObservableObject {
    @Published var isRecognizing = false
    @Published var errorMessage: String?
    @Published var candidates: [RecognizedWord] = []
    @Published var selectedWords: Set<String> = []
    @Published var showResult = false
    /// 识别中展示的扫描态背景图，跟压缩后实际上传的 Data 无关，只用于 UI 反馈。
    @Published var capturedImage: UIImage?

    func recognize(imageData: Data) async {
        isRecognizing = true
        errorMessage = nil
        // 识别是本地 OCR + 视觉 LLM（还带重试）的耗时操作，等待期间如果屏幕自动
        // 锁屏，系统会挂起/限流后台网络活动，很容易把正在进行的上传请求直接掐断
        // （实测复现：NSURLErrorNetworkConnectionLost -1005）。识别期间禁止息屏。
        UIApplication.shared.isIdleTimerDisabled = true
        defer {
            isRecognizing = false
            UIApplication.shared.isIdleTimerDisabled = false
        }
        do {
            // 先本地 Apple Vision OCR（印刷体又快又准、免流量），把抠出的候选词连同
            // 图片一起发给后端：视觉 LLM 既自己看图识别、又参考 OCR 列表，综合取并集，
            // 两个来源互补以提高召回。OCR 抠不到词时就退化为纯看图识别。
            let ocrWords = await TextRecognizer.recognizeWords(from: imageData)
            let resp = try await WordService.recognize(imageData: imageData, ocrWords: ocrWords)
            candidates = resp.candidates
            // 已在生词库中的默认不勾选，其余默认全选
            selectedWords = Set(resp.candidates.filter { !$0.alreadyInLibrary }.map { $0.word })
            showResult = true
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "识别失败，请重新拍摄"
        }
    }

    func toggle(_ word: String) {
        if selectedWords.contains(word) {
            selectedWords.remove(word)
        } else {
            selectedWords.insert(word)
        }
    }

    /// 返回新建的单词行（而不只是数量），调用方要用 id 去生词库页做高亮定位。
    func addSelectedToLibrary() async -> (added: [VocabularyWord], skipped: [String]) {
        let toAdd = candidates
            .filter { selectedWords.contains($0.word) }
            .map { VocabularyWordCreate(word: $0.word, phoneticIpa: $0.phoneticIpa,
                                        partOfSpeech: $0.partOfSpeech, definitionZh: $0.definitionZh,
                                        etymology: $0.etymology, exampleSentence: $0.exampleSentence) }
        guard !toAdd.isEmpty else { return ([], []) }
        do {
            let resp = try await WordService.addWordsBatch(toAdd)
            reset()
            return (resp.created, resp.skippedExisting)
        } catch let error as APIError {
            errorMessage = error.message
            return ([], [])
        } catch {
            errorMessage = "加入生词库失败"
            return ([], [])
        }
    }

    func reset() {
        candidates = []
        selectedWords = []
        showResult = false
        capturedImage = nil
    }
}
