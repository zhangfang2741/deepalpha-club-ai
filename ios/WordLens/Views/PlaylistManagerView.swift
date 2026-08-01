// Views/PlaylistManagerView.swift
import SwiftUI

/// 分组管理：新建、改名、改词表、删除。从生词库进入。
///
/// 这些操作原先散在「切换分组」页的右上角菜单和标签长按里。放在那儿有两个问题：
/// 换组是个高频的一秒钟动作，管理是低频的编辑动作，混在一页里互相干扰；而且
/// 「往分组里放哪些词」本来就是在生词库里挑词，跟这里同源。
struct PlaylistManagerView: View {
    @ObservedObject var viewModel: PlaylistViewModel

    @Environment(\.dismiss) private var dismiss
    @State private var editingPlaylist: Playlist?
    @State private var isCreating = false
    @State private var pendingDeletion: Playlist?

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()

                if viewModel.isLoading && viewModel.playlists.isEmpty {
                    ProgressView().tint(Theme.accent)
                } else if viewModel.playlists.isEmpty {
                    ContentUnavailableView {
                        Label("还没有自定义分组", systemImage: "folder.badge.plus")
                    } description: {
                        Text("把常背的词攒成一组，学习页就能单独播这一组")
                    } actions: {
                        Button("新建分组") { isCreating = true }
                            .buttonStyle(.borderedProminent)
                            .tint(Theme.accent)
                    }
                } else {
                    List {
                        ForEach(viewModel.playlists) { playlist in
                            let isDeleting = viewModel.deletingPlaylistID == playlist.id
                            Button {
                                editingPlaylist = playlist
                            } label: {
                                HStack {
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text(playlist.name)
                                            .font(.body.weight(.medium))
                                            .foregroundStyle(Theme.textPrimary)
                                        Text(isDeleting ? "删除中…" : "\(playlist.wordCount) 个单词")
                                            .font(.caption)
                                            .foregroundStyle(Theme.textSecondary)
                                    }
                                    Spacer()
                                    if isDeleting {
                                        ProgressView()
                                            .tint(Theme.unknown)
                                    } else {
                                        Image(systemName: "chevron.right")
                                            .font(.caption.weight(.bold))
                                            .foregroundStyle(Theme.textSecondary)
                                    }
                                }
                                .contentShape(.rect)
                            }
                            .buttonStyle(.plain)
                            // 删除中：整行降透明，禁用按钮和左滑——避免用户在请求
                            // 飞行期间又点这一行或左滑出别的动作造成状态混乱。
                            .disabled(isDeleting)
                            .opacity(isDeleting ? 0.5 : 1.0)
                            .listRowBackground(Theme.surface)
                            .swipeActions(edge: .trailing) {
                                Button(role: .destructive) {
                                    pendingDeletion = playlist
                                } label: {
                                    Label("删除", systemImage: "trash")
                                }
                                .tint(Theme.unknown)
                                .disabled(isDeleting)
                            }
                        }

                        if let errorMessage = viewModel.errorMessage {
                            Text(errorMessage)
                                .font(.footnote)
                                .foregroundStyle(Theme.unknown)
                                .listRowBackground(Theme.surface)
                        }
                    }
                    .listStyle(.insetGrouped)
                    .scrollContentBackground(.hidden)
                }
            }
            .navigationTitle("分组管理")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("完成") { dismiss() }.tint(Theme.textSecondary)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { isCreating = true } label: {
                        Image(systemName: "plus")
                    }
                    .tint(Theme.accent)
                    .accessibilityLabel("新建分组")
                }
            }
            .task { await viewModel.load() }
            .refreshable { await viewModel.load() }
            .sheet(isPresented: $isCreating) {
                PlaylistEditorView(playlist: nil, viewModel: viewModel)
            }
            .sheet(item: $editingPlaylist) { playlist in
                PlaylistEditorView(playlist: playlist, viewModel: viewModel)
            }
            .confirmationDialog(
                "删除「\(pendingDeletion?.name ?? "")」？",
                isPresented: Binding(
                    get: { pendingDeletion != nil },
                    set: { if !$0 { pendingDeletion = nil } }
                ),
                titleVisibility: .visible
            ) {
                Button("删除分组", role: .destructive) {
                    guard let playlist = pendingDeletion else { return }
                    pendingDeletion = nil
                    // deletePlaylist 内部会把 deletingPlaylistID 置上、再走网络
                    // 请求——行立刻灰掉并显示「删除中…」加载状态，完成后自动恢复。
                    Task { await viewModel.deletePlaylist(id: playlist.id) }
                }
                Button("取消", role: .cancel) { pendingDeletion = nil }
            } message: {
                Text("只删分组，里面的单词仍然留在生词库")
            }
        }
    }
}
