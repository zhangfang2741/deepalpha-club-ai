// ViewModels/CameraViewModel.swift
import Foundation
import SwiftUI

@MainActor
final class CameraViewModel: ObservableObject {
    @Published var isRecognizing = false
    @Published var errorMessage: String?
    @Published var candidates: [RecognizedWord] = []
    @Published var selectedWords: Set<String> = []
    @Published var showResult = false

    func recognize(imageData: Data) async {
        isRecognizing = true
        errorMessage = nil
        defer { isRecognizing = false }
        do {
            let resp = try await WordService.recognize(imageData: imageData)
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

    func addSelectedToLibrary() async -> (added: Int, skipped: [String]) {
        let toAdd = candidates
            .filter { selectedWords.contains($0.word) }
            .map { VocabularyWordCreate(word: $0.word, phoneticIpa: $0.phoneticIpa,
                                        partOfSpeech: $0.partOfSpeech, definitionZh: $0.definitionZh,
                                        etymology: $0.etymology, exampleSentence: $0.exampleSentence) }
        guard !toAdd.isEmpty else { return (0, []) }
        do {
            let resp = try await WordService.addWordsBatch(toAdd)
            reset()
            return (resp.created.count, resp.skippedExisting)
        } catch let error as APIError {
            errorMessage = error.message
            return (0, [])
        } catch {
            errorMessage = "加入生词库失败"
            return (0, [])
        }
    }

    func reset() {
        candidates = []
        selectedWords = []
        showResult = false
    }
}
