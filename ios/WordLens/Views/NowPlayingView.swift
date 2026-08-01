// Views/NowPlayingView.swift
import SwiftUI

/// 全屏「正在播放」页：顶部横向 chip 切分组，下面直接列出该组的全部单词。
///
/// 之前这里是个底部半屏 sheet，只能选组、看不到组里有什么词。参考音乐 App 的
/// 正在播放页重做：一屏之内既能换组、也能看到完整队列、还能点任意一个词直接
/// 跳过去——不用二级跳转。
struct NowPlayingView: View {
    @ObservedObject var playlistVM: PlaylistViewModel
    @ObservedObject var reviewVM: ReviewViewModel

    /// 切换分组：(选中的组, 显示名, 是否立即播放)
    let onSelect: (PlaylistSelection, String, Bool) -> Void
    /// 点击列表里的某个词，跳到它。
    let onJump: (VocabularyWord) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var editingPlaylist: Playlist?
    @State private var isCreating = false
    @State private var playlistPendingDeletion: Playlist?

    private var current: PlaylistSelection { reviewVM.selection }

    /// chip 顺序：待复习 → 三个状态 → 自定义歌单。内置的在前，用户自己的在后。
    private var chips: [(selection: PlaylistSelection, label: String, color: Color)] {
        var items: [(PlaylistSelection, String, Color)] = [
            (.dueReview, "待复习", Theme.accent),
            (.status("new"), "不认识", Theme.unknown),
            (.status("fuzzy"), "模糊", Theme.fuzzy),
            (.status("known"), "认识", Theme.known),
        ]
        items += playlistVM.playlists.map { (.custom($0.id), $0.name, Theme.textPrimary) }
        return items.map { (selection: $0.0, label: $0.1, color: $0.2) }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()

                VStack(spacing: 0) {
                    header
                    chipRow
                    Divider().overlay(Theme.border)
                    wordList
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "chevron.down")
                            .font(.headline)
                    }
                    .tint(Theme.textSecondary)
                    .accessibilityLabel("收起")
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button {
                            isCreating = true
                        } label: {
                            Label("新建自定义分组", systemImage: "plus")
                        }
                        if case .custom(let id) = current,
                           let playlist = playlistVM.playlists.first(where: { $0.id == id }) {
                            Button {
                                editingPlaylist = playlist
                            } label: {
                                Label("编辑「\(playlist.name)」", systemImage: "pencil")
                            }
                            Button(role: .destructive) {
                                playlistPendingDeletion = playlist
                            } label: {
                                Label("删除「\(playlist.name)」", systemImage: "trash")
                            }
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                    .tint(Theme.accent)
                    .accessibilityLabel("更多操作")
                }
            }
            .task { await playlistVM.load() }
            .refreshable { await playlistVM.load() }
            .sheet(isPresented: $isCreating) {
                PlaylistEditorView(playlist: nil, viewModel: playlistVM)
            }
            .sheet(item: $editingPlaylist) { playlist in
                PlaylistEditorView(playlist: playlist, viewModel: playlistVM)
            }
            .confirmationDialog(
                "删除「\(playlistPendingDeletion?.name ?? "")」？",
                isPresented: Binding(
                    get: { playlistPendingDeletion != nil },
                    set: { if !$0 { playlistPendingDeletion = nil } }
                ),
                titleVisibility: .visible
            ) {
                Button("删除分组", role: .destructive) {
                    guard let playlist = playlistPendingDeletion else { return }
                    playlistPendingDeletion = nil
                    Task {
                        await playlistVM.deletePlaylist(id: playlist.id)
                        // 删掉的正好是在播的那一组，回落到待复习，免得停在一个
                        // 已经不存在的列表上。
                        if current == .custom(playlist.id) {
                            onSelect(.dueReview, PlaylistSelection.dueReview.displayName(), false)
                        }
                    }
                }
                Button("取消", role: .cancel) { playlistPendingDeletion = nil }
            } message: {
                Text("只删分组，里面的单词仍然留在生词库")
            }
        }
    }

    // MARK: - 头部

    /// 「正在播放 / 组名 / N 个词 · 已过 M」——一眼看清在哪一组、进度到哪。
    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("正在播放")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Theme.textSecondary)
                .textCase(.uppercase)
                .tracking(1.2)

            Text(reviewVM.selectionName)
                .font(.largeTitle.bold())
                .foregroundStyle(Theme.textPrimary)
                .lineLimit(1)
                .minimumScaleFactor(0.7)

            HStack(spacing: 6) {
                Text("\(reviewVM.totalCount) 个词")
                if reviewVM.reviewedCount > 0 {
                    Text("·")
                    Text("已过 \(reviewVM.reviewedCount)")
                }
                if reviewVM.autoplay.isPlaying {
                    Text("·")
                    Label("连播中", systemImage: "speaker.wave.2.fill")
                        .foregroundStyle(Theme.accent)
                }
            }
            .font(.caption)
            .foregroundStyle(Theme.textSecondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 20)
        .padding(.bottom, 14)
    }

    // MARK: - 分组 chip

    private var chipRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(chips, id: \.selection) { chip in
                    chipButton(chip.selection, label: chip.label, color: chip.color)
                }
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 14)
        }
    }

    private func chipButton(_ selection: PlaylistSelection, label: String, color: Color) -> some View {
        let isCurrent = selection == current
        let count = playlistVM.count(for: selection)
        return Button {
            guard !isCurrent else { return }
            onSelect(selection, label, false)
        } label: {
            HStack(spacing: 6) {
                Text(label)
                    .font(.subheadline.weight(isCurrent ? .bold : .medium))
                Text("\(count)")
                    .font(.caption2.weight(.semibold))
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(isCurrent ? Color.white.opacity(0.22) : Theme.surfaceAlt)
                    .clipShape(.capsule)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 9)
            .foregroundStyle(isCurrent ? .white : color)
            .background(isCurrent ? color : Theme.surface)
            .clipShape(.capsule)
            .overlay {
                Capsule().strokeBorder(
                    isCurrent ? .clear : Theme.border, lineWidth: 1
                )
            }
        }
        .buttonStyle(.pressable)
        .accessibilityLabel("\(label)，\(count) 个")
        .accessibilityAddTraits(isCurrent ? [.isButton, .isSelected] : .isButton)
    }

    // MARK: - 单词列表

    @ViewBuilder
    private var wordList: some View {
        if reviewVM.isLoading {
            Spacer()
            ProgressView().tint(Theme.accent)
            Spacer()
        } else if reviewVM.queue.isEmpty {
            Spacer()
            ContentUnavailableView(
                current.emptyTitle,
                systemImage: "music.note.list",
                description: Text(current.emptyDescription)
            )
            Spacer()
        } else {
            // ScrollViewReader 让打开这个页面时能直接滚到正在播的那个词，
            // 队列有几百个词时不用自己找。
            ScrollViewReader { proxy in
                List {
                    Section {
                        ForEach(Array(reviewVM.queue.enumerated()), id: \.element.id) { index, word in
                            wordRow(word, index: index)
                                .id(word.id)
                        }
                    } header: {
                        Text("接下来")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(Theme.textSecondary)
                            .textCase(nil)
                    }
                }
                .listStyle(.plain)
                .scrollContentBackground(.hidden)
                .onAppear {
                    guard let currentID = reviewVM.currentWord?.id else { return }
                    proxy.scrollTo(currentID, anchor: .center)
                }
                // 连播推进时列表跟着滚，正在读的词始终在视野里。
                .onChange(of: reviewVM.currentWord?.id) { _, newID in
                    guard let newID else { return }
                    withAnimation { proxy.scrollTo(newID, anchor: .center) }
                }
            }
        }
    }

    private func wordRow(_ word: VocabularyWord, index: Int) -> some View {
        let isCurrent = word.id == reviewVM.currentWord?.id
        return Button {
            onJump(word)
        } label: {
            HStack(spacing: 12) {
                // 正在播的词用声波图标顶替序号，跟音乐 App 一致。
                Group {
                    if isCurrent {
                        Image(systemName: "speaker.wave.2.fill")
                            .foregroundStyle(Theme.accent)
                            .symbolEffect(.variableColor.iterative, isActive: reviewVM.autoplay.isPlaying)
                    } else {
                        Text("\(index + 1)")
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(Theme.textSecondary)
                    }
                }
                .frame(width: 24)

                VStack(alignment: .leading, spacing: 3) {
                    Text(word.word)
                        .font(.body.weight(isCurrent ? .bold : .semibold))
                        .foregroundStyle(isCurrent ? Theme.accent : Theme.textPrimary)
                    Text("/\(word.phoneticIpa)/ \(word.definitionZh)")
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                        .lineLimit(1)
                }

                Spacer()
                statusDot(word.status)
            }
            .padding(.vertical, 10)
            .padding(.horizontal, 14)
            .background(isCurrent ? Theme.surfaceAlt : Theme.surface)
            .clipShape(.rect(cornerRadius: 12))
            .overlay {
                if isCurrent {
                    RoundedRectangle(cornerRadius: 12)
                        .strokeBorder(Theme.accent.opacity(0.6), lineWidth: 1.5)
                }
            }
        }
        .buttonStyle(.pressable)
        .listRowBackground(Color.clear)
        .listRowSeparator(.hidden)
        .listRowInsets(EdgeInsets(top: 3, leading: 20, bottom: 3, trailing: 20))
        .accessibilityLabel("\(word.word)，\(word.definitionZh)\(isCurrent ? "，正在播放" : "")")
        .accessibilityHint("双击跳到这个单词")
    }

    private func statusDot(_ status: String) -> some View {
        let color: Color = {
            switch status {
            case "known": return Theme.known
            case "fuzzy": return Theme.fuzzy
            default: return Theme.unknown
            }
        }()
        return Circle().fill(color).frame(width: 7, height: 7)
    }
}
