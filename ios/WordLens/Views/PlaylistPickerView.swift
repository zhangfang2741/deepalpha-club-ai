// Views/PlaylistPickerView.swift
import SwiftUI

/// 选一个歌单：生词库多选完点「加入歌单」时弹出。
///
/// 只负责「选哪个歌单」这一件事，选完把 id 交回调用方去调接口。歌单一个都没有
/// 时给一个直接新建的入口，免得用户被卡在一个空列表前面。
struct PlaylistPickerView: View {
    @ObservedObject var viewModel: PlaylistViewModel
    /// 回传整个 Playlist 而不只是 id：调用方要拿分组名做「已加入「xxx」」的提示。
    let onPick: (Playlist) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var isCreating = false

    var body: some View {
        NavigationStack {
            Group {
                if viewModel.isLoading && viewModel.playlists.isEmpty {
                    ProgressView().tint(Theme.accent)
                } else if viewModel.playlists.isEmpty {
                    ContentUnavailableView {
                        Label("还没有自定义分组", systemImage: "music.note.list")
                    } description: {
                        Text("先建一个分组，再把选中的单词加进去")
                    } actions: {
                        Button("新建分组") { isCreating = true }
                            .buttonStyle(.borderedProminent)
                            .tint(Theme.accent)
                    }
                } else {
                    List(viewModel.playlists) { playlist in
                        Button {
                            onPick(playlist)
                            dismiss()
                        } label: {
                            HStack {
                                Text(playlist.name)
                                    .font(.subheadline.weight(.medium))
                                    .foregroundStyle(Theme.textPrimary)
                                Spacer()
                                Text("\(playlist.wordCount) 个")
                                    .font(.caption)
                                    .foregroundStyle(Theme.textSecondary)
                            }
                            .contentShape(.rect)
                        }
                        .buttonStyle(.plain)
                        .listRowBackground(Theme.surface)
                    }
                    .listStyle(.insetGrouped)
                    .scrollContentBackground(.hidden)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Theme.background.ignoresSafeArea())
            .navigationTitle("加入分组")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("取消") { dismiss() }.tint(Theme.textSecondary)
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
            .sheet(isPresented: $isCreating) {
                PlaylistEditorView(playlist: nil, viewModel: viewModel)
            }
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
    }
}
