// Views/WordListView.swift
import SwiftUI

struct WordListView: View {
    @ObservedObject var viewModel: WordListViewModel
    var onRefresh: (() async -> Void)?

    /// 按单词首字母分组，供右侧字母索引条定位（类似系统通讯录）。非字母开头统一归到 "#"。
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
                        // 右侧字母索引条对 VoiceOver 隐藏（连续拖动手势做不出有意义的
                        // 无障碍交互），改用 Rotor 让 VoiceOver 用户也能快速跳转到某个
                        // 字母分组，功能上补齐而不是单纯砍掉。
                        .accessibilityRotor("按字母跳转") {
                            ForEach(sections, id: \.letter) { section in
                                AccessibilityRotorEntry(section.letter, id: section.letter)
                            }
                        }
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
    /// 对 VoiceOver 隐藏——这种连续拖动手势做不出有意义的无障碍交互；跳转能力
    /// 改由上面 List 挂的 accessibilityRotor("按字母跳转") 提供。
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
        .frame(width: 18)
        .frame(maxHeight: .infinity)
        .padding(.vertical, 8)
        .accessibilityHidden(true)
    }

    private func indexLetter(for word: String) -> String {
        guard let first = word.uppercased().first, first.isLetter else { return "#" }
        return String(first)
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
