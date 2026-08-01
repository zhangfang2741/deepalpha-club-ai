// Views/NowPlayingView.swift
import SwiftUI

/// 切换分组：把所有分组摊开，点一个就换过去。
///
/// 这一页只干「换组」一件事。曾经它还兼着预览词表 + 二次确认 + 新建/编辑/删除
/// 分组，现在都拆走了：当前队列的词表挪到了播放条右侧的队列按钮，新建/管理
/// 分组挪到了生词库。职责收敛之后，点一下即切、立刻收起，没有中间步骤。
struct NowPlayingView: View {
    @ObservedObject var playlistVM: PlaylistViewModel
    @ObservedObject var reviewVM: ReviewViewModel

    /// 切换分组：(选中的组, 显示名)
    let onSelect: (PlaylistSelection, String) -> Void

    @Environment(\.dismiss) private var dismiss

    private var current: PlaylistSelection { reviewVM.selection }

    /// 内置分组：待复习 + 三个状态。`dot` 是名字前那个小圆点的颜色，nil 表示不画。
    private var builtinGroups: [(selection: PlaylistSelection, label: String, dot: Color?)] {
        [
            (.dueReview, "待复习", nil),
            (.status("new"), "不认识", Theme.unknown),
            (.status("fuzzy"), "模糊", Theme.fuzzy),
            (.status("known"), "认识", Theme.known),
        ]
    }

    private var customGroups: [(selection: PlaylistSelection, label: String, dot: Color?)] {
        playlistVM.playlists.map { (.custom($0.id), $0.name, nil) }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()

                List {
                    Section("生词库分组") {
                        ForEach(builtinGroups, id: \.selection) { group in
                            groupRow(group.selection, label: group.label, dot: group.dot)
                        }
                    }
                    .listRowBackground(Theme.surface)

                    if customGroups.isEmpty {
                        Section("自定义") {
                            Text("还没有自定义分组，去「生词库 › 分组管理」新建")
                                .font(.footnote)
                                .foregroundStyle(Theme.textSecondary)
                        }
                        .listRowBackground(Theme.surface)
                    } else {
                        Section("自定义") {
                            ForEach(customGroups, id: \.selection) { group in
                                groupRow(group.selection, label: group.label, dot: group.dot)
                            }
                        }
                        .listRowBackground(Theme.surface)
                    }
                }
                .listStyle(.insetGrouped)
                .scrollContentBackground(.hidden)
            }
            .navigationTitle("切换分组")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "chevron.down").font(.headline)
                    }
                    .tint(Theme.textSecondary)
                    .accessibilityLabel("收起")
                }
            }
            .task { await playlistVM.load() }
            .refreshable { await playlistVM.load() }
            .overlay {
                if playlistVM.isLoading && playlistVM.playlists.isEmpty {
                    ProgressView().tint(Theme.accent)
                }
            }
        }
    }

    private func groupRow(_ selection: PlaylistSelection, label: String, dot: Color?) -> some View {
        let isCurrent = selection == current
        let count = playlistVM.count(for: selection)
        return Button {
            guard !isCurrent else {
                dismiss()
                return
            }
            onSelect(selection, label)
            dismiss()
        } label: {
            HStack(spacing: 10) {
                if let dot {
                    Circle().fill(dot).frame(width: 8, height: 8)
                }
                Text(label)
                    .font(.body.weight(isCurrent ? .semibold : .regular))
                    .foregroundStyle(isCurrent ? Theme.accent : Theme.textPrimary)
                Spacer()
                Text("\(count) 个")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(Theme.textSecondary)
                if isCurrent {
                    Image(systemName: "checkmark")
                        .font(.footnote.weight(.bold))
                        .foregroundStyle(Theme.accent)
                }
            }
            .contentShape(.rect)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(label)，\(count) 个\(isCurrent ? "，当前分组" : "")")
        .accessibilityAddTraits(isCurrent ? [.isButton, .isSelected] : .isButton)
    }
}
