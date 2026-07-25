// Views/HomeView.swift
import SwiftUI

struct HomeView: View {
    @StateObject private var listVM = WordListViewModel()
    @State private var reviewDueCount = 0

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                TextField("搜索单词", text: $listVM.searchQuery)
                    .padding(10)
                    .background(Theme.surface)
                    .foregroundStyle(Theme.textPrimary)
                    .clipShape(.rect(cornerRadius: 8))
                    .onSubmit { Task { await listVM.load() } }

                VStack(alignment: .leading, spacing: 12) {
                    Text("今日待复习：\(reviewDueCount) 个")
                        .font(.headline)
                        .foregroundStyle(Theme.textPrimary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding()
                .background(Theme.surface)
                .clipShape(.rect(cornerRadius: 12))

                statsRow

                // 生词库自身带字母索引条，需要用 List 独立滚动，所以不能再跟上面的
                // 卡片一起塞进一个大 ScrollView——那样索引条拖动定位的是整页而不是词表。
                WordListView(viewModel: listVM, onRefresh: refreshAll)
            }
            .padding(.horizontal)
            .padding(.top)
            .background(Theme.background.ignoresSafeArea())
            .navigationTitle("生词库")
            .task { await refreshAll() }
        }
    }

    private func refreshAll() async {
        await listVM.load()
        reviewDueCount = (try? await WordService.reviewQueue().count) ?? 0
    }

    /// 统计数字本身就是筛选入口——点一个状态直接筛列表，不再跟 WordListView 里
    /// 单独一套筛选 chip 重复；数字永远按全量 allWords 算，不会因为当前选中了
    /// 某个筛选状态就把其它状态的数字显示成 0。
    private var statsRow: some View {
        let words = listVM.allWords
        let unknownCount = words.filter { $0.status == "new" }.count
        let fuzzyCount = words.filter { $0.status == "fuzzy" }.count
        let knownCount = words.filter { $0.status == "known" }.count
        return HStack(spacing: 12) {
            statTile("全部", words.count, Theme.textPrimary, isSelected: listVM.filterStatus == nil) {
                listVM.filterStatus = nil
            }
            statTile("不认识", unknownCount, Theme.unknown, isSelected: listVM.filterStatus == "new") {
                listVM.filterStatus = listVM.filterStatus == "new" ? nil : "new"
            }
            statTile("模糊", fuzzyCount, Theme.fuzzy, isSelected: listVM.filterStatus == "fuzzy") {
                listVM.filterStatus = listVM.filterStatus == "fuzzy" ? nil : "fuzzy"
            }
            statTile("认识", knownCount, Theme.known, isSelected: listVM.filterStatus == "known") {
                listVM.filterStatus = listVM.filterStatus == "known" ? nil : "known"
            }
        }
    }

    private func statTile(_ label: String, _ count: Int, _ color: Color, isSelected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 4) {
                Text("\(count)")
                    .font(.title2.bold())
                    .foregroundStyle(color)
                Text(label)
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .background(isSelected ? Theme.surfaceAlt : Theme.surface)
            .clipShape(.rect(cornerRadius: 10))
            .overlay {
                if isSelected {
                    RoundedRectangle(cornerRadius: 10).strokeBorder(color, lineWidth: 1.5)
                }
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(label)，\(count) 个")
        .accessibilityAddTraits(isSelected ? [.isButton, .isSelected] : .isButton)
    }
}
