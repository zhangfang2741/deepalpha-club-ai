// Views/WordListView.swift
import SwiftUI

struct WordListView: View {
    @ObservedObject var viewModel: WordListViewModel

    private let filters: [(label: String, value: String?)] = [
        ("全部", nil), ("不认识", "new"), ("模糊", "fuzzy"), ("认识", "known"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("生词库").font(.headline).foregroundStyle(Theme.textPrimary)
                Spacer()
            }

            TextField("搜索单词", text: $viewModel.searchQuery)
                .padding(10)
                .background(Theme.surface)
                .foregroundStyle(Theme.textPrimary)
                .clipShape(.rect(cornerRadius: 8))
                .onSubmit { Task { await viewModel.load() } }

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(filters, id: \.label) { filter in
                        filterChip(filter.label, filter.value)
                    }
                }
            }

            if viewModel.isLoading {
                ProgressView().tint(Theme.accent).frame(maxWidth: .infinity)
            } else if viewModel.words.isEmpty {
                ContentUnavailableView(
                    "暂无生词",
                    systemImage: "book.closed",
                    description: Text("去拍照识别一些新单词吧")
                )
            } else {
                ForEach(viewModel.words) { word in
                    NavigationLink(destination: WordDetailView(word: word, listViewModel: viewModel)) {
                        wordRow(word)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private func filterChip(_ label: String, _ value: String?) -> some View {
        Button {
            viewModel.filterStatus = value
            Task { await viewModel.load() }
        } label: {
            Text(label)
                .font(.caption)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(viewModel.filterStatus == value ? Theme.accent : Theme.surface)
                .foregroundStyle(viewModel.filterStatus == value ? .white : Theme.textSecondary)
                .clipShape(Capsule())
        }
    }

    private func wordRow(_ word: VocabularyWord) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(word.word).fontWeight(.semibold).foregroundStyle(Theme.textPrimary)
                Text("/\(word.phoneticIpa)/ \(word.definitionZh)")
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(1)
            }
            Spacer()
            statusDot(word.status)
        }
        .padding()
        .background(Theme.surface)
        .clipShape(.rect(cornerRadius: 10))
    }

    private func statusDot(_ status: String) -> some View {
        let (color, label): (Color, String) = {
            switch status {
            case "known": return (Theme.known, "认识")
            case "fuzzy": return (Theme.fuzzy, "模糊")
            default: return (Theme.unknown, "不认识")
            }
        }()
        return HStack(spacing: 4) {
            Circle().fill(color).frame(width: 8, height: 8)
            Text(label).font(.caption2).foregroundStyle(Theme.textSecondary)
        }
    }
}
