import SwiftUI

/// 词条名在界面上的小标签：点开看大白话（有缠论教程的词条打开教程，否则打开名词小词典）。
/// 两边都查不到时什么也不画——词条还没写全的时候不留死链接。
struct TermChip: View {
    let term: String

    private var title: String? {
        GlossaryStore.entry(for: term)?.term ?? GlossaryIndex.article(for: term)?.title
    }

    var body: some View {
        if let title {
            GlossaryLink(term: term) {
                HStack(spacing: 4) {
                    Image(systemName: "book").font(.system(size: 10))
                    Text(title).font(.caption)
                }
                .foregroundStyle(Theme.accent)
                .padding(.horizontal, 9).padding(.vertical, 4)
                .background(Theme.accent.opacity(0.12), in: Capsule())
            }
        }
    }
}

/// 名词旁的小问号：点开看这个词是什么意思。
struct TermHint: View {
    let term: String

    var body: some View {
        GlossaryLink(term: term) {
            Image(systemName: "questionmark.circle")
                .font(.system(size: 11))
                .foregroundStyle(Theme.textSecondary.opacity(0.9))
                .frame(minWidth: 22, minHeight: 22)
                .contentShape(Rectangle())
        }
        .accessibilityLabel(L("这个词是什么意思"))
    }
}

/// 一个名词的解释内容（弹层与词典页下钻共用）。
struct GlossaryEntryView: View {
    let entry: GlossaryEntry

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text(entry.plain)
                    .font(.system(size: 16)).foregroundStyle(Theme.textPrimary)
                    .lineSpacing(5).fixedSize(horizontal: false, vertical: true)
                if let example = entry.example {
                    block(icon: "lightbulb", color: Theme.segment, title: L("举个例子"), text: example)
                }
                if let notMeans = entry.notMeans {
                    block(icon: "xmark.circle", color: Theme.textSecondary, title: L("它不代表"), text: notMeans)
                }
                Text(L("以上为通俗解释，仅供学习参考，不构成投资建议。"))
                    .font(.caption2).foregroundStyle(Theme.textSecondary)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(Theme.background)
        .navigationTitle(entry.term)
        .navigationBarTitleDisplayMode(.inline)
    }

    private func block(icon: String, color: Color, title: String, text: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: icon).foregroundStyle(color).padding(.top, 2)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.footnote.weight(.semibold)).foregroundStyle(Theme.textPrimary)
                Text(text).font(.subheadline).foregroundStyle(Theme.textSecondary)
                    .lineSpacing(4).fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 10))
    }
}

/// 名词小词典：按类别分组、可搜索；学习页入口。
struct GlossaryListView: View {
    @State private var query = ""

    var body: some View {
        let hits = GlossaryStore.search(query)
        List {
            ForEach(GlossaryCategory.allCases, id: \.self) { category in
                let items = hits.filter { $0.category == category.rawValue }
                if !items.isEmpty {
                    Section(category.title) {
                        ForEach(items) { entry in
                            NavigationLink { GlossaryEntryView(entry: entry) } label: {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(entry.term).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.textPrimary)
                                    Text(entry.plain).font(.caption).foregroundStyle(Theme.textSecondary).lineLimit(2)
                                }
                            }
                        }
                    }
                }
            }
        }
        .scrollContentBackground(.hidden)
        .background(Theme.background)
        .searchable(text: $query, prompt: L("搜索名词"))
        .navigationTitle(L("名词小词典"))
        .navigationBarTitleDisplayMode(.inline)
    }
}
