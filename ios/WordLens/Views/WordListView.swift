// Views/WordListView.swift
import SwiftUI

struct WordListView: View {
    @ObservedObject var viewModel: WordListViewModel
    var onRefresh: (() async -> Void)?

    private let filters: [(label: String, value: String?)] = [
        ("全部", nil), ("不认识", "new"), ("模糊", "fuzzy"), ("认识", "known"),
    ]

    /// 按单词首字母分组，供右侧字母索引条定位（类似系统通讯录）。非字母开头统一归到 "#"。
    private var sections: [(letter: String, words: [VocabularyWord])] {
        let grouped = Dictionary(grouping: viewModel.words) { indexLetter(for: $0.word) }
        return grouped.keys.sorted().map { letter in
            (letter, grouped[letter]!.sorted { $0.word.localizedCaseInsensitiveCompare($1.word) == .orderedAscending })
        }
    }

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
                    ZStack(alignment: .trailing) {
                        List {
                            ForEach(sections, id: \.letter) { section in
                                Section {
                                    ForEach(section.words) { word in
                                        NavigationLink(destination: WordDetailView(word: word, listViewModel: viewModel)) {
                                            wordRow(word)
                                        }
                                        .buttonStyle(.plain)
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
                        .padding(.trailing, 18)

                        indexBar(proxy: proxy)
                    }
                }
            }
        }
    }

    /// 右侧字母索引条：拖动时按手指纵向位置换算成字母，滚动列表到对应分组。
    /// 对 VoiceOver 隐藏——VoiceOver 用户本就是靠逐行滑动浏览列表定位，这种连续
    /// 拖动手势做不出有意义的无障碍交互，隐藏索引条不影响他们正常浏览生词库。
    private func indexBar(proxy: ScrollViewProxy) -> some View {
        let letters = sections.map(\.letter)
        return GeometryReader { geo in
            VStack(spacing: 0) {
                ForEach(letters, id: \.self) { letter in
                    Text(letter)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(Theme.accent)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { value in
                        guard !letters.isEmpty else { return }
                        let rowHeight = geo.size.height / CGFloat(letters.count)
                        let index = min(letters.count - 1, max(0, Int(value.location.y / rowHeight)))
                        proxy.scrollTo(letters[index], anchor: .top)
                    }
            )
        }
        .frame(width: 18, maxHeight: .infinity)
        .padding(.vertical, 8)
        .accessibilityHidden(true)
    }

    private func indexLetter(for word: String) -> String {
        guard let first = word.uppercased().first, first.isLetter else { return "#" }
        return String(first)
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
