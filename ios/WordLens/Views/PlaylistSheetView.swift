// Views/PlaylistSheetView.swift
import SwiftUI

/// 播放列表面板：从首页左上角唤出的底部半屏 sheet，像音乐 App 的「播放队列」。
///
/// 三组来源：
/// - 智能推荐：今日待复习（SM-2 算出来的那条队列）
/// - 生词库分组：不认识 / 模糊 / 认识
/// - 我的歌单：用户手挑单词攒的组
///
/// 整行点击 = 切到这一组；行尾的 ▶ = 切过去并立刻开始连播。
struct PlaylistSheetView: View {
    @ObservedObject var viewModel: PlaylistViewModel
    /// 当前在播的组，用来打勾。
    let current: PlaylistSelection
    /// 选中回调：(选中的组, 显示名, 是否立即播放)
    let onSelect: (PlaylistSelection, String, Bool) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var editingPlaylist: Playlist?
    @State private var isCreating = false
    @State private var playlistPendingDeletion: Playlist?

    private let statusGroups: [(selection: PlaylistSelection, label: String, color: Color)] = [
        (.status("new"), "😵 不认识", Theme.unknown),
        (.status("fuzzy"), "😐 模糊", Theme.fuzzy),
        (.status("known"), "😊 认识", Theme.known),
    ]

    var body: some View {
        NavigationStack {
            List {
                Section("智能推荐") {
                    row(.dueReview, label: "待复习", color: Theme.accent)
                }

                Section("生词库分组") {
                    ForEach(statusGroups, id: \.selection) { group in
                        row(group.selection, label: group.label, color: group.color)
                    }
                }

                Section("自定义") {
                    ForEach(viewModel.playlists) { playlist in
                        row(.custom(playlist.id), label: playlist.name, color: Theme.textPrimary)
                            .swipeActions(edge: .trailing) {
                                Button(role: .destructive) {
                                    playlistPendingDeletion = playlist
                                } label: {
                                    Label("删除", systemImage: "trash")
                                }
                                Button {
                                    editingPlaylist = playlist
                                } label: {
                                    Label("编辑", systemImage: "pencil")
                                }
                                .tint(Theme.accent)
                            }
                    }

                    Button {
                        isCreating = true
                    } label: {
                        Label("新建歌单", systemImage: "plus.circle.fill")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(Theme.accent)
                    }
                }

                if let errorMessage = viewModel.errorMessage {
                    Section {
                        Text(errorMessage)
                            .font(.footnote)
                            .foregroundStyle(Theme.unknown)
                    }
                }
            }
            .listStyle(.insetGrouped)
            .scrollContentBackground(.hidden)
            .background(Theme.background)
            .navigationTitle("播放列表")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("完成") { dismiss() }
                        .tint(Theme.accent)
                }
            }
            .overlay {
                if viewModel.isLoading && viewModel.playlists.isEmpty {
                    ProgressView().tint(Theme.accent)
                }
            }
            .task { await viewModel.load() }
            .refreshable { await viewModel.load() }
            // 新建 / 编辑都推到同一个编辑页，区别只是有没有带初始歌单。
            .sheet(isPresented: $isCreating) {
                PlaylistEditorView(playlist: nil, viewModel: viewModel)
            }
            .sheet(item: $editingPlaylist) { playlist in
                PlaylistEditorView(playlist: playlist, viewModel: viewModel)
            }
            .confirmationDialog(
                "删除歌单「\(playlistPendingDeletion?.name ?? "")」？",
                isPresented: Binding(
                    get: { playlistPendingDeletion != nil },
                    set: { if !$0 { playlistPendingDeletion = nil } }
                ),
                titleVisibility: .visible
            ) {
                Button("删除歌单", role: .destructive) {
                    guard let playlist = playlistPendingDeletion else { return }
                    playlistPendingDeletion = nil
                    Task {
                        await viewModel.deletePlaylist(id: playlist.id)
                        // 删掉的正好是在播的那一组，回落到待复习，免得停在一个
                        // 已经不存在的列表上。
                        if current == .custom(playlist.id) {
                            onSelect(.dueReview, PlaylistSelection.dueReview.displayName(), false)
                        }
                    }
                }
                Button("取消", role: .cancel) { playlistPendingDeletion = nil }
            } message: {
                Text("只删歌单，里面的单词仍然留在生词库")
            }
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
    }

    private func row(_ selection: PlaylistSelection, label: String, color: Color) -> some View {
        let isCurrent = selection == current
        let count = viewModel.count(for: selection)
        return HStack(spacing: 12) {
            // 行尾的播放键单独可点：切过去并立刻开始连播。空组不给播。
            Button {
                onSelect(selection, label, true)
                dismiss()
            } label: {
                Image(systemName: "play.circle.fill")
                    .font(.title3)
                    .foregroundStyle(count > 0 ? Theme.accent : Theme.textSecondary.opacity(0.4))
            }
            .buttonStyle(.plain)
            .disabled(count == 0)
            .accessibilityLabel("播放 \(label)")

            Button {
                onSelect(selection, label, false)
                dismiss()
            } label: {
                HStack(spacing: 8) {
                    Text(label)
                        .font(.subheadline.weight(isCurrent ? .semibold : .regular))
                        .foregroundStyle(color)
                    Spacer()
                    Text("\(count) 个")
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                    if isCurrent {
                        Image(systemName: "checkmark")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(Theme.accent)
                    }
                }
                .contentShape(.rect)
            }
            .buttonStyle(.plain)
        }
        .listRowBackground(isCurrent ? Theme.surfaceAlt : Theme.surface)
        .accessibilityElement(children: .contain)
        .accessibilityAddTraits(isCurrent ? [.isSelected] : [])
    }
}
