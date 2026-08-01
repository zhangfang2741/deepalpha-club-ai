// Views/WordListView.swift
import SwiftUI

struct WordListView: View {
    @ObservedObject var viewModel: WordListViewModel
    @EnvironmentObject var nav: AppNavigationState
    var onRefresh: (() async -> Void)?

    /// 用 Button + navigationDestination(item:) 代替 NavigationLink(destination:)：
    /// NavigationLink 在 List 里会自带一个右侧箭头指示器，视觉上跟自己的
    /// statusDot 挤在一起显得乱，改成手动导航就没有这个箭头。
    @State private var selectedWord: VocabularyWord?
    @State private var showDeleteConfirm = false
    /// 多选后「加入歌单」用：面板里挑一个已有歌单，把选中的词并进去。
    @StateObject private var playlistVM = PlaylistViewModel()
    @State private var showPlaylistPicker = false

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
            selectionBar

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
                                    Button {
                                        if viewModel.isSelecting {
                                            viewModel.toggleSelection(word)
                                        } else {
                                            selectedWord = word
                                        }
                                    } label: {
                                        wordRow(word)
                                    }
                                    .buttonStyle(.pressable)
                                    .listRowBackground(Color.clear)
                                    .listRowSeparator(.hidden)
                                    .listRowInsets(EdgeInsets(top: 4, leading: 0, bottom: 4, trailing: 0))
                                    // 删除时让行带 0.35s 的滑出+淡出过渡，配合
                                    // ViewModel 里 withAnimation 一起给用户"按了有反应"
                                    // 的反馈，而不是数据被硬切走。
                                    .transition(.asymmetric(
                                        insertion: .opacity,
                                        removal: .move(edge: .leading).combined(with: .opacity)
                                    ))
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
                    // 监听 allWords 的删除触发 List 自带的删除动画；
                    // 0.35s 的 duration 和 viewRow 上 transition 的 timing 对齐。
                    .animation(.easeInOut(duration: 0.35), value: viewModel.allWords.map(\.id))
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

                if viewModel.isSelecting && !viewModel.selectedIDs.isEmpty {
                    // 复用已有的多选基建（isSelecting / selectedIDs），
                    // 只是多给一个去处：除了删除，也能把选中的词并进歌单。
                    Button {
                        showPlaylistPicker = true
                    } label: {
                        Label("加入分组 (\(viewModel.selectedIDs.count))", systemImage: "text.badge.plus")
                            .font(.subheadline.weight(.semibold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 12)
                            .background(Theme.accent.opacity(0.15))
                            .foregroundStyle(Theme.accent)
                            .clipShape(.rect(cornerRadius: 10))
                    }
                    .buttonStyle(.pressable)
                    .disabled(viewModel.isDeletingSelected)

                    Button(role: .destructive) {
                        showDeleteConfirm = true
                    } label: {
                        // 删除中显示进度 X/Y; 否则显示静态"删除所选 (N)".
                        // 用户能直观看到 100 词批量删除推进到第几个——
                        // 100 词并发 3 秒内结束, 进度数字会从 0/100 滚到 100/100,
                        // 比 beginBlockingOperation 的固定文案更清晰.
                        Group {
                            if let progress = viewModel.deletionProgress {
                                Text("正在删除 \(progress.completed) / \(progress.total)")
                            } else {
                                Text("删除所选 (\(viewModel.selectedIDs.count))")
                            }
                        }
                        .font(.subheadline.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(Theme.unknown.opacity(viewModel.isDeletingSelected ? 0.25 : 0.15))
                        .foregroundStyle(Theme.unknown)
                        .clipShape(.rect(cornerRadius: 10))
                    }
                    .buttonStyle(.pressable)
                    .disabled(viewModel.isDeletingSelected)
                    .confirmationDialog(
                        "确定删除选中的 \(viewModel.selectedIDs.count) 个单词吗？",
                        isPresented: $showDeleteConfirm,
                        titleVisibility: .visible
                    ) {
                        Button("删除", role: .destructive) {
                            Task {
                                nav.beginBlockingOperation("正在删除生词...")
                                defer { nav.endBlockingOperation() }
                                if await viewModel.deleteSelected() {
                                    nav.notifyVocabularyDataChanged()
                                }
                            }
                        }
                        Button("取消", role: .cancel) {}
                    }
                }
            }
        }
        .navigationDestination(item: $selectedWord) { word in
            WordDetailView(word: word, listViewModel: viewModel)
        }
        .sheet(isPresented: $showPlaylistPicker) {
            PlaylistPickerView(viewModel: playlistVM) { playlistID in
                Task {
                    let wordIDs = Array(viewModel.selectedIDs)
                    if await playlistVM.addWords(to: playlistID, wordIDs: wordIDs) {
                        viewModel.toggleSelecting()  // 加完退出多选，跟删除后的行为一致
                    }
                }
            }
        }
    }

    private var selectionBar: some View {
        HStack {
            if viewModel.isSelecting {
                Button {
                    viewModel.toggleSelectAll()
                } label: {
                    Text(selectAllTitle)
                        .font(.subheadline.weight(viewModel.isAllSelected ? .semibold : .regular))
                }
                .disabled(viewModel.words.isEmpty)
            }

            Spacer()

            Button(viewModel.isSelecting ? "完成" : "选择") {
                viewModel.toggleSelecting()
            }
            .font(.subheadline.weight(.semibold))
            .disabled(viewModel.words.isEmpty)
        }
        .frame(height: 32)
    }

    private var selectAllTitle: String {
        if viewModel.isAllSelected {
            return "全不选"
        }
        return "全选"
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
        let isSelected = viewModel.selectedIDs.contains(word.id)
        return HStack {
            if viewModel.isSelecting {
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(isSelected ? Theme.accent : Theme.textSecondary)
                    .font(.title3)
            }
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
