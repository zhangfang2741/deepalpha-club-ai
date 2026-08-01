// Views/PlaylistEditorView.swift
import SwiftUI

/// 新建 / 编辑歌单：起个名字 + 从生词库里勾选想背的词。
///
/// `playlist == nil` 是新建，否则是编辑（进来时先把已有词表拉下来预勾上）。
/// 勾选顺序就是保存顺序，也就是之后的播放顺序——后端按 position 存。
struct PlaylistEditorView: View {
    let playlist: Playlist?
    @ObservedObject var viewModel: PlaylistViewModel

    @Environment(\.dismiss) private var dismiss
    @StateObject private var wordList = WordListViewModel()

    @State private var name: String = ""
    @State private var searchText: String = ""
    /// 用数组而不是 Set：勾选的先后顺序就是播放顺序，Set 存不住顺序。
    @State private var selectedIDs: [String] = []
    @State private var isSaving = false
    @State private var isLoadingExisting = false

    private var isNew: Bool { playlist == nil }

    /// 搜索只在本地过滤已加载的全量生词，不打后端——编辑歌单时来回搜很频繁。
    private var filteredWords: [VocabularyWord] {
        let all = wordList.allWords
        guard !searchText.isEmpty else { return all }
        return all.filter {
            $0.word.localizedCaseInsensitiveContains(searchText)
                || $0.definitionZh.localizedCaseInsensitiveContains(searchText)
        }
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                TextField("歌单名称", text: $name)
                    .padding(10)
                    .background(Theme.surface)
                    .foregroundStyle(Theme.textPrimary)
                    .clipShape(.rect(cornerRadius: 8))

                HStack {
                    Text("已选 \(selectedIDs.count) 个")
                        .font(.caption)
                        .foregroundStyle(Theme.textSecondary)
                    Spacer()
                    if !selectedIDs.isEmpty {
                        Button("清空选择") { selectedIDs.removeAll() }
                            .font(.caption)
                            .tint(Theme.accent)
                    }
                }

                TextField("搜索单词", text: $searchText)
                    .padding(10)
                    .background(Theme.surface)
                    .foregroundStyle(Theme.textPrimary)
                    .clipShape(.rect(cornerRadius: 8))

                if wordList.isLoading || isLoadingExisting {
                    ProgressView().tint(Theme.accent).frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if wordList.allWords.isEmpty {
                    ContentUnavailableView(
                        "生词库还是空的",
                        systemImage: "book.closed",
                        description: Text("先去拍照识别一些单词，再来建歌单")
                    )
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    List(filteredWords) { word in
                        Button {
                            toggle(word)
                        } label: {
                            wordRow(word)
                        }
                        .buttonStyle(.plain)
                        .listRowBackground(Color.clear)
                        .listRowSeparator(.hidden)
                        .listRowInsets(EdgeInsets(top: 4, leading: 0, bottom: 4, trailing: 0))
                    }
                    .listStyle(.plain)
                    .scrollContentBackground(.hidden)
                }
            }
            .padding(.horizontal)
            .padding(.top)
            .background(Theme.background.ignoresSafeArea())
            .navigationTitle(isNew ? "新建歌单" : "编辑歌单")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("取消") { dismiss() }.tint(Theme.textSecondary)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button(isSaving ? "保存中…" : "保存") { Task { await save() } }
                        .tint(Theme.accent)
                        .disabled(isSaving || name.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
            .task { await loadInitialState() }
        }
    }

    private func loadInitialState() async {
        await wordList.load()
        guard let playlist else { return }
        name = playlist.name
        isLoadingExisting = true
        defer { isLoadingExisting = false }
        // 编辑已有歌单时按 position 顺序回填，保存后顺序不会被打乱。
        if let words = try? await WordService.playlistWords(id: playlist.id) {
            selectedIDs = words.map(\.id)
        }
    }

    private func toggle(_ word: VocabularyWord) {
        if let index = selectedIDs.firstIndex(of: word.id) {
            selectedIDs.remove(at: index)
        } else {
            selectedIDs.append(word.id)
        }
    }

    private func save() async {
        let trimmedName = name.trimmingCharacters(in: .whitespaces)
        guard !trimmedName.isEmpty else { return }
        isSaving = true
        defer { isSaving = false }
        let ok: Bool
        if let playlist {
            ok = await viewModel.updatePlaylist(id: playlist.id, name: trimmedName, wordIDs: selectedIDs)
        } else {
            ok = await viewModel.createPlaylist(name: trimmedName, wordIDs: selectedIDs) != nil
        }
        if ok { dismiss() }
    }

    /// 行样式跟生词库列表保持一致（词 + 音标释义 + 状态点），只是把右侧的状态点
    /// 换成勾选框，用户在两个页面看到的是同一种"一行一个词"。
    private func wordRow(_ word: VocabularyWord) -> some View {
        let isSelected = selectedIDs.contains(word.id)
        return HStack {
            Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                .foregroundStyle(isSelected ? Theme.accent : Theme.textSecondary)
                .font(.title3)
            VStack(alignment: .leading, spacing: 4) {
                Text(word.word).fontWeight(.semibold).foregroundStyle(Theme.textPrimary)
                Text("/\(word.phoneticIpa)/ \(word.definitionZh)")
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(1)
            }
            Spacer()
        }
        .padding()
        .background(isSelected ? Theme.surfaceAlt : Theme.surface)
        .clipShape(.rect(cornerRadius: 10))
    }
}
