// Views/HomeView.swift
import SwiftUI

struct HomeView: View {
    @StateObject private var listVM = WordListViewModel()
    @State private var reviewDueCount = 0

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
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
            .navigationTitle("首页")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    NavigationLink(destination: SettingsView()) {
                        Image(systemName: "gearshape")
                    }
                    .accessibilityLabel("设置")
                }
            }
            .task { await refreshAll() }
        }
    }

    private func refreshAll() async {
        await listVM.load()
        reviewDueCount = (try? await WordService.reviewQueue().count) ?? 0
    }

    private var statsRow: some View {
        let words = listVM.words
        let unknownCount = words.filter { $0.status == "new" }.count
        let fuzzyCount = words.filter { $0.status == "fuzzy" }.count
        let knownCount = words.filter { $0.status == "known" }.count
        return HStack(spacing: 16) {
            statTile("不认识", unknownCount, Theme.unknown)
            statTile("模糊", fuzzyCount, Theme.fuzzy)
            statTile("认识", knownCount, Theme.known)
        }
    }

    private func statTile(_ label: String, _ count: Int, _ color: Color) -> some View {
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
        .background(Theme.surface)
        .clipShape(.rect(cornerRadius: 10))
    }
}
