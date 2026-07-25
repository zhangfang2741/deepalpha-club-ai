// Views/HomeView.swift
import SwiftUI

struct HomeView: View {
    @StateObject private var listVM = WordListViewModel()
    @State private var reviewDueCount = 0

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                ScrollView {
                    VStack(spacing: 20) {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("今日待复习：\(reviewDueCount) 个")
                                .font(.headline)
                                .foregroundColor(Theme.textPrimary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .background(Theme.surface)
                        .clipShape(RoundedRectangle(cornerRadius: 12))

                        statsRow

                        WordListView(viewModel: listVM)
                    }
                    .padding()
                }
            }
            .navigationTitle("WordLens")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    NavigationLink(destination: SettingsView()) {
                        Image(systemName: "gearshape")
                    }
                }
            }
            .task {
                await listVM.load()
                reviewDueCount = (try? await WordService.reviewQueue().count) ?? 0
            }
            .refreshable {
                await listVM.load()
                reviewDueCount = (try? await WordService.reviewQueue().count) ?? 0
            }
        }
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
                .foregroundColor(color)
            Text(label)
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}
