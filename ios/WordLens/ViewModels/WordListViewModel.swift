// ViewModels/WordListViewModel.swift
import Foundation

@MainActor
final class WordListViewModel: ObservableObject {
    @Published var words: [VocabularyWord] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var filterStatus: String?
    @Published var searchQuery = ""

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            words = try await WordService.listWords(status: filterStatus, query: searchQuery)
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "加载生词库失败"
        }
    }

    func delete(_ word: VocabularyWord) async {
        do {
            try await WordService.deleteWord(id: word.id)
            words.removeAll { $0.id == word.id }
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "删除失败"
        }
    }
}
