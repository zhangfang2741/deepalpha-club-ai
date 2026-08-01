// Views/NowPlayingView.swift
import SwiftUI

/// 全屏「切换分组」页：上面是所有分组的标签，下面列出选中那一组有哪些词。
///
/// 这里的词表是**纯展示**——点词不会跳转、也不会开始播放。这一页只干「挑分组」
/// 一件事，挑完按底部按钮才生效。要跳到某个具体的词，走首页顶部的播放队列下拉
/// 框（那里才是「当前正在播的队列」）。两件事分开，点错的代价就小。
struct NowPlayingView: View {
    @ObservedObject var playlistVM: PlaylistViewModel
    @ObservedObject var reviewVM: ReviewViewModel

    /// 切换分组：(选中的组, 显示名, 是否立即播放)
    let onSelect: (PlaylistSelection, String, Bool) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var editingPlaylist: Playlist?
    @State private var isCreating = false
    @State private var playlistPendingDeletion: Playlist?

    /// 正在「看」的分组，跟正在「播」的分组是两回事。
    ///
    /// 点分组标签只改这个值（翻着看看那一组有哪些词），不会动当前队列；真正切
    /// 过去要再点底部的「切换到这一组」。之前点一下标签就直接把队列换掉，很容易
    /// 手一滑就把正在背的进度冲掉。
    @State private var previewing: PlaylistSelection?

    private var current: PlaylistSelection { reviewVM.selection }
    /// 界面上正在展示的是哪一组（没在预览时就是正在播的那组）。
    private var shown: PlaylistSelection { previewing ?? current }
    /// 是否处于「看的不是正在播的那组」的状态。
    private var isPreviewingOther: Bool { previewing != nil && previewing != current }

    /// 内置分组：待复习 + 三个状态。`dot` 是标签前那个小圆点的颜色，nil 表示不画。
    private var builtinChips: [(selection: PlaylistSelection, label: String, dot: Color?)] {
        [
            (.dueReview, "待复习", nil),
            (.status("new"), "不认识", Theme.unknown),
            (.status("fuzzy"), "模糊", Theme.fuzzy),
            (.status("known"), "认识", Theme.known),
        ]
    }

    /// 用户自建的分组。
    private var customChips: [(selection: PlaylistSelection, label: String, dot: Color?)] {
        playlistVM.playlists.map { (.custom($0.id), $0.name, nil) }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()

                VStack(spacing: 0) {
                    chipRow
                    Divider().overlay(Theme.border)
                    wordList
                }
                .padding(.top, 8)
            }
            // 确认条钉在底部：切分组这个动作必须显式点一下，不会因为点了标签
            // 就悄悄发生。
            .safeAreaInset(edge: .bottom) {
                confirmBar
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
            .refreshable {
                await playlistVM.load()
                // 计数和词表要一起刷：只刷计数会出现「标签写着 5 个、下面列表还是
                // 空的」这种自相矛盾的状态（在别处往这个分组加过词时就会这样）。
                if isPreviewingOther, let previewing {
                    await playlistVM.loadPreview(previewing)
                } else {
                    await reviewVM.loadQueue()
                }
            }
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

    /// 展示用词表：看正在播的那组就用实时队列（能高亮当前词、能点词跳转），
    /// 预览别的组则用单独拉的 previewWords。
    private var shownWords: [VocabularyWord] {
        isPreviewingOther ? playlistVM.previewWords : reviewVM.queue
    }

    // MARK: - 分组 chip

    /// 用流式布局自动换行，所有分组一次铺开、位置固定——之前是横向 ScrollView，
    /// 分组一多就得左右滑才看得全。
    ///
    /// 内置分组和自定义分组分成两组、各带一行小标题：之前它们混在一片标签里，
    /// 「不认识」和用户自己起名的分组看着是同一类东西，其实完全不是。
    private var chipRow: some View {
        VStack(alignment: .leading, spacing: 12) {
            chipGroup("生词库分组", chips: builtinChips)
            if !customChips.isEmpty {
                chipGroup("自定义", chips: customChips)
            }
        }
        .padding(.horizontal, 20)
        .padding(.bottom, 14)
    }

    private func chipGroup(
        _ title: String, chips: [(selection: PlaylistSelection, label: String, dot: Color?)]
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(Theme.textSecondary)
            FlowLayout(spacing: 8, lineSpacing: 8) {
                ForEach(chips, id: \.selection) { chip in
                    chipButton(chip.selection, label: chip.label, dot: chip.dot)
                }
            }
        }
    }

    /// 标签只有一套配色，颜色只用来表达「选中」这一件事。
    ///
    /// 之前每个分组各用各的主题色（蓝/红/橙/绿）当文字色和描边色，计数还各自
    /// 套一个彩色胶囊，选中态又换成白底——五个标签五种颜色互相打架，看着很乱。
    /// 现在统一成深色底 + 细描边，只有选中的那个填成主题蓝；状态色降级成标签
    /// 前面一个小圆点，信息还在但不再抢戏。
    private func chipButton(_ selection: PlaylistSelection, label: String, dot: Color?) -> some View {
        // 选中态跟着「正在看的那一组」走；正在播的那一组额外带个小喇叭，
        // 这样"我在看哪组"和"实际在播哪组"一眼能分开。
        let isShown = selection == shown
        let isCurrent = selection == current
        let count = playlistVM.count(for: selection)
        return Button {
            guard !isShown else { return }
            previewing = selection
            // 切回正在播的那组不用重新拉，直接用实时队列。
            if selection != current {
                Task { await playlistVM.loadPreview(selection) }
            }
        } label: {
            HStack(spacing: 6) {
                if isCurrent {
                    Image(systemName: "speaker.wave.2.fill")
                        .font(.caption2)
                        .foregroundStyle(isShown ? .white : Theme.accent)
                } else if let dot {
                    Circle()
                        .fill(dot)
                        .frame(width: 6, height: 6)
                }
                Text(label)
                    .font(.subheadline.weight(isShown ? .semibold : .regular))
                    .foregroundStyle(isShown ? .white : Theme.textPrimary)
                Text("\(count)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(isShown ? Color.white.opacity(0.75) : Theme.textSecondary)
            }
            .padding(.horizontal, 13)
            .padding(.vertical, 8)
            .background(isShown ? Theme.accent : Theme.surface)
            .clipShape(.capsule)
            .overlay {
                Capsule().strokeBorder(isShown ? .clear : Theme.border, lineWidth: 1)
            }
        }
        .buttonStyle(.pressable)
        .accessibilityLabel("\(label)，\(count) 个\(isCurrent ? "，正在播放" : "")")
        .accessibilityAddTraits(isShown ? [.isButton, .isSelected] : .isButton)
    }

    // MARK: - 底部确认条

    /// 切分组必须显式确认：点标签只是翻着看，真正切过去要按这里。
    /// 看的就是正在播的那组时，这里退化成连播的开关。
    @ViewBuilder
    private var confirmBar: some View {
        VStack(spacing: 10) {
            if isPreviewingOther {
                Button {
                    commitPreview()
                } label: {
                    Label("播放这一组", systemImage: "play.fill")
                        .font(.subheadline.weight(.bold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Theme.accent)
                        .foregroundStyle(.white)
                        .clipShape(.rect(cornerRadius: 12))
                }
                .buttonStyle(.pressable)
                .disabled(playlistVM.previewWords.isEmpty)
            } else {
                Button {
                    reviewVM.autoplay.toggle()
                } label: {
                    Label(
                        reviewVM.autoplay.isPlaying ? "停止连播" : "开始连播",
                        systemImage: reviewVM.autoplay.isPlaying ? "stop.fill" : "play.fill"
                    )
                    .font(.subheadline.weight(.bold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(reviewVM.autoplay.isPlaying ? Theme.unknown : Theme.accent)
                    .foregroundStyle(.white)
                    .clipShape(.rect(cornerRadius: 12))
                }
                .buttonStyle(.pressable)
                .disabled(reviewVM.queue.isEmpty)
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 10)
        .padding(.bottom, 8)
        .background(.ultraThinMaterial)
    }

    /// 确认切换到预览中的分组并开始连播，然后收起本页回到卡片。
    private func commitPreview() {
        guard let selection = previewing else { return }
        onSelect(selection, selection.displayName(playlists: playlistVM.playlists), true)
        previewing = nil
        playlistVM.clearPreview()
        dismiss()
    }

    // MARK: - 单词列表

    @ViewBuilder
    private var wordList: some View {
        if isPreviewingOther ? playlistVM.isLoadingPreview : reviewVM.isLoading {
            Spacer()
            ProgressView().tint(Theme.accent)
            Spacer()
        } else if shownWords.isEmpty {
            Spacer()
            ContentUnavailableView(
                shown.emptyTitle,
                systemImage: "music.note.list",
                description: Text(shown.emptyDescription)
            )
            Spacer()
        } else {
            // ScrollViewReader 让打开这个页面时能直接滚到正在播的那个词，
            // 队列有几百个词时不用自己找。
            ScrollViewReader { proxy in
                List {
                    Section {
                        ForEach(Array(shownWords.enumerated()), id: \.element.id) { index, word in
                            wordRow(word, index: index)
                                .id(word.id)
                        }
                    } header: {
                        // 大标题那一块整个去掉了——分组标签本身就标着选中态和
                        // 计数，再来一遍只是占地方。进度这些信息压缩成这一行小字。
                        HStack(spacing: 6) {
                            Text(isPreviewingOther ? "这一组的单词" : "接下来")
                            Text("·")
                            Text("\(shownWords.count) 个")
                            if !isPreviewingOther, reviewVM.reviewedCount > 0 {
                                Text("·")
                                Text("已过 \(reviewVM.reviewedCount)")
                            }
                            if !isPreviewingOther, reviewVM.autoplay.isPlaying {
                                Text("·")
                                Label("连播中", systemImage: "speaker.wave.2.fill")
                                    .foregroundStyle(Theme.accent)
                            }
                        }
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
        // 这一页的词表是纯展示，一律不可点：这里的任务只是「挑分组」。跳到某个
        // 具体的词属于「操作当前队列」，走首页顶部的播放队列下拉框。
        let isCurrent = !isPreviewingOther && word.id == reviewVM.currentWord?.id
        return Group {
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
        .listRowBackground(Color.clear)
        .listRowSeparator(.hidden)
        .listRowInsets(EdgeInsets(top: 3, leading: 20, bottom: 3, trailing: 20))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(word.word)，\(word.definitionZh)\(isCurrent ? "，正在播放" : "")")
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
