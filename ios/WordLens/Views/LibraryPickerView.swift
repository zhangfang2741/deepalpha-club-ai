// Views/LibraryPickerView.swift
import SwiftUI

/// 内置词库选择页（从设置页进入）。
///
/// 展示后端内置的分组词库（小学/初中/高中/四六级/考研/专四专八/出国/商务），
/// 用户点某一本即可把整本并入自己的生词库。导入服务端自动跨全库去重，可重复
/// 导入把之前漏掉的补齐，因此对同一本反复点也安全。
struct LibraryPickerView: View {
    @EnvironmentObject private var nav: AppNavigationState
    @StateObject private var viewModel = LibraryPickerViewModel()

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            content
        }
        .navigationTitle(L("选择词库"))
        .navigationBarTitleDisplayMode(.inline)
        .task { await viewModel.loadIfNeeded() }
        // 导入进行中盖一层，避免用户在写库期间反复点触发并发导入。
        .overlay {
            if let importing = viewModel.importingTitle {
                importingOverlay(title: importing)
            }
        }
        .alert(item: $viewModel.resultAlert) { alert in
            Alert(title: Text(alert.title), message: Text(alert.message), dismissButton: .default(Text(L("好的"))))
        }
    }

    @ViewBuilder
    private var content: some View {
        if viewModel.isLoading {
            ProgressView().tint(Theme.accent)
        } else if let error = viewModel.errorMessage {
            VStack(spacing: 12) {
                Label(error, systemImage: "exclamationmark.triangle")
                    .foregroundStyle(Theme.textSecondary)
                Button(L("重试")) { Task { await viewModel.reload() } }
                    .buttonStyle(.borderedProminent)
                    .tint(Theme.accent)
            }
            .padding()
        } else {
            libraryList
        }
    }

    private var libraryList: some View {
        Form {
            ForEach(viewModel.groups) { group in
                Section {
                    ForEach(group.books) { book in
                        Button {
                            viewModel.confirmImport(book: book)
                        } label: {
                            HStack(spacing: 12) {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(book.title)
                                        .foregroundStyle(Theme.textPrimary)
                                    Text(L("%lld 词", book.wordCount))
                                        .font(.caption)
                                        .foregroundStyle(Theme.textSecondary)
                                }
                                Spacer()
                                Image(systemName: "plus.circle")
                                    .foregroundStyle(Theme.accent)
                            }
                        }
                        .disabled(viewModel.importingTitle != nil)
                    }
                } header: {
                    Text(group.title)
                }
                .listRowBackground(Theme.surface)
            }
        }
        .scrollContentBackground(.hidden)
        .confirmationDialog(
            viewModel.pendingBook?.title ?? "",
            isPresented: $viewModel.isConfirmPresented,
            titleVisibility: .visible
        ) {
            if let book = viewModel.pendingBook {
                Button(L("加入生词库")) {
                    Task { await viewModel.performImport(book: book, nav: nav) }
                }
                Button(L("取消"), role: .cancel) {}
            }
        } message: {
            if let book = viewModel.pendingBook {
                Text(L("将「%@」的 %lld 个单词加入生词库，已有的词会自动跳过。", book.title, book.wordCount))
            }
        }
    }

    private func importingOverlay(title: String) -> some View {
        ZStack {
            Color.black.opacity(0.35).ignoresSafeArea()
            VStack(spacing: 14) {
                ProgressView().tint(.white)
                Text(L("正在导入「%@」…", title))
                    .font(.subheadline)
                    .foregroundStyle(.white)
            }
            .padding(24)
            .background(RoundedRectangle(cornerRadius: 16).fill(Color.black.opacity(0.6)))
        }
    }
}

/// 内置词库选择页的状态。
@MainActor
final class LibraryPickerViewModel: ObservableObject {
    @Published var groups: [VocabularyLibraryGroup] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    @Published var pendingBook: VocabularyLibraryBook?
    @Published var isConfirmPresented = false
    /// 非 nil 表示正在导入这本（标题），用于盖遮罩、禁用列表。
    @Published var importingTitle: String?
    @Published var resultAlert: LibraryImportAlert?

    /// 首次进入才拉取；已加载过（例如从确认框返回）不重复请求。
    func loadIfNeeded() async {
        guard groups.isEmpty, !isLoading else { return }
        await reload()
    }

    func reload() async {
        isLoading = true
        errorMessage = nil
        do {
            groups = try await WordService.listLibraries()
        } catch {
            errorMessage = L("加载词库失败，请稍后重试")
        }
        isLoading = false
    }

    func confirmImport(book: VocabularyLibraryBook) {
        pendingBook = book
        isConfirmPresented = true
    }

    func performImport(book: VocabularyLibraryBook, nav: AppNavigationState) async {
        importingTitle = book.title
        defer { importingTitle = nil }
        do {
            let result = try await WordService.importLibrary(bookId: book.id)
            // 导入总会建/刷新对应歌单，且可能并入新词，统一通知刷新生词库/首页
            // 各分组计数与歌单列表。
            nav.notifyVocabularyDataChanged()
            resultAlert = LibraryImportAlert(
                title: L("导入完成"),
                message: Self.resultMessage(result: result)
            )
        } catch {
            resultAlert = LibraryImportAlert(
                title: L("导入失败"),
                message: L("请检查网络后重试")
            )
        }
    }

    private static func resultMessage(result: LibraryImportResult) -> String {
        let head: String
        if result.imported == 0 {
            head = L("这些单词都已在生词库中，进度保持不变。")
        } else if result.skipped == 0 {
            head = L("已加入 %lld 个新单词。", result.imported)
        } else {
            head = L("已加入 %lld 个新单词，%lld 个已存在（进度保留）。", result.imported, result.skipped)
        }
        // 每本词库都会生成同名歌单，指引用户去首页单独复习这本。
        let tail = L("已生成歌单「%@」（%lld 词），可在首页切换到它单独复习。",
                     result.playlistName, result.playlistWordCount)
        return head + "\n" + tail
    }
}

/// 导入结果弹窗内容。用 Identifiable 配合 .alert(item:)。
struct LibraryImportAlert: Identifiable {
    let id = UUID()
    let title: String
    let message: String
}
