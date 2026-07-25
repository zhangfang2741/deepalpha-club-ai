// Views/WordListView.swift
import SwiftUI

struct WordListView: View {
    @ObservedObject var viewModel: WordListViewModel
    @EnvironmentObject var nav: AppNavigationState
    var onRefresh: (() async -> Void)?

    /// 按单词首字母分组，用 Section 标题做 A/B/C 分组展示（不再提供右侧可拖动的
    /// 跳转条，那个反而挡内容）。非字母开头统一归到 "#"。
    private var sections: [(letter: String, words: [VocabularyWord])] {
        let grouped = Dictionary(grouping: viewModel.words) { indexLetter(for: $0.word) }
        return grouped.keys.sorted().map { letter in
            (letter, grouped[letter]!.sorted { $0.word.localizedCaseInsensitiveCompare($1.word) == .orderedAscending })
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if viewModel.isLoading && viewModel.words.isEmpty {
                // 只在完全没数据时显示占位 loading；已有数据时的后台刷新
                // 不能让列表内容被替换掉，否则从详情页返回时滚动位置会被重置到顶部。
                ProgressView().tint(Theme.accent).frame(maxWidth: .infinity)
            } else if viewModel.words.isEmpty {
                ContentUnavailableView(
                    "暂无生词",
                    systemImage: "book.closed",
                    description: Text("去拍照识别一些新单词吧")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollViewReader { proxy in
                    List {
                        ForEach(sections, id: \.letter) { section in
                            Section {
                                ForEach(section.words) { word in
                                    NavigationLink(destination: WordDetailView(word: word, listViewModel: viewModel)) {
                                        wordRow(word)
                                    }
                                    .buttonStyle(.pressable)
                                    .listRowBackground(Color.clear)
                                    .listRowSeparator(.hidden)
                                    .listRowInsets(EdgeInsets(top: 4, leading: 0, bottom: 4, trailing: 0))
                                }
                            } header: {
                                Text(section.letter)
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(Theme.textSecondary)
                                    .textCase(nil)
                            }
                            .id(section.letter)
                        }
                    }
                    .listStyle(.plain)
                    .scrollContentBackground(.hidden)
                    .refreshable {
                        if let onRefresh {
                            await onRefresh()
                        } else {
                            await viewModel.load()
                        }
                    }
                    // 拍照识别加入生词库后会跳到这个 tab 并高亮新词，滚到新词所在的
                    // 字母分组，不然高亮的词可能在屏幕外，用户根本看不到高亮在哪。
                    // allWords 的变化在 highlightedWordIDs 之后才到（跳转时先设置高亮，
                    // 列表要另外刷新才会真的包含新词），两个都要监听，谁后到用谁触发。
                    .onChange(of: nav.highlightedWordIDs) { _, _ in
                        scrollToHighlightedIfNeeded(proxy: proxy)
                    }
                    .onChange(of: viewModel.allWords.count) { _, _ in
                        scrollToHighlightedIfNeeded(proxy: proxy)
                    }
                }
            }
        }
    }

    private func scrollToHighlightedIfNeeded(proxy: ScrollViewProxy) {
        guard let firstID = nav.highlightedWordIDs.first,
              let word = viewModel.words.first(where: { $0.id == firstID }) else { return }
        withAnimation { proxy.scrollTo(indexLetter(for: word.word), anchor: .top) }
    }

    private func indexLetter(for word: String) -> String {
        guard let first = word.uppercased().first, first.isLetter else { return "#" }
        return String(first)
    }

    private func wordRow(_ word: VocabularyWord) -> some View {
        let isHighlighted = nav.highlightedWordIDs.contains(word.id)
        return HStack {
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
        .background(isHighlighted ? Theme.accent.opacity(0.25) : Theme.surface)
        .clipShape(.rect(cornerRadius: 10))
        .overlay {
            if isHighlighted {
                RoundedRectangle(cornerRadius: 10).strokeBorder(Theme.accent, lineWidth: 1.5)
            }
        }
        .animation(.easeOut(duration: 0.6), value: isHighlighted)
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
