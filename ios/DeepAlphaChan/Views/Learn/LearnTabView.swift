import SwiftUI

/// 学习 Tab：缠论概念词条列表。
struct LearnTabView: View {
    private let articles = LessonStore.all
    private let guides = GuideStore.all
    @State private var showTour = false

    /// 以登录页 sheet 形式弹出时传 false：登录流程是隐私场景，不参与截图分享。
    /// 主 Tab 里的学习页不传，默认启用。
    var enablesScreenshotShare = true

    var body: some View {
        if enablesScreenshotShare {
            content
                // 挂在 NavigationStack 外面：挂里面的话预览弹窗会被导航层裁切
                .shareOnScreenshot(text: "DeepAlpha \(L("缠论")) · \(L("缠论入门"))")
        } else {
            content
        }
    }

    private var content: some View {
        NavigationStack {
            Group {
                if articles.isEmpty {
                    emptyState
                } else {
                    list
                }
            }
            .background(Theme.background)
            .navigationTitle(L("学习"))
            .sheet(isPresented: $showTour) { OnboardingTourView() }
        }
    }

    /// 一级页只放四个入口（导览 + 三个分类），具体文章都在二级列表里——22 条平铺太乱。
    private var list: some View {
        ScrollView {
            VStack(spacing: 10) {
                Text(L("没学过金融也能读：先弄明白这个 App 的思路，再一步步看懂每个数字。"))
                    .font(.footnote).foregroundColor(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 8)

                Button { showTour = true } label: {
                    entryCard(icon: "play.circle.fill", title: L("30 秒看懂这个 App"),
                              subtitle: L("重新看一遍新手导览"))
                }
                .buttonStyle(.plain)

                if !guides.isEmpty {
                    NavigationLink { GuideListView(guides: guides) } label: {
                        entryCard(icon: "sparkles", title: L("新手入门"),
                                  subtitle: L("先看这个：App 怎么用、四步怎么看"),
                                  count: L("%lld 篇", guides.count))
                    }
                    .buttonStyle(.plain)
                }

                NavigationLink { LessonListView(articles: articles) } label: {
                    entryCard(icon: "chart.xyaxis.line", title: L("缠论入门"),
                              subtitle: L("按顺序读，看懂分析页上画的每一条线"),
                              count: L("%lld 篇", articles.count))
                }
                .buttonStyle(.plain)

                NavigationLink { GlossaryListView() } label: {
                    entryCard(icon: "character.book.closed", title: L("名词小词典"),
                              subtitle: L("逐利、避险、基点、倒挂、百分位……一查就懂"),
                              count: L("%lld 个词", GlossaryStore.all.count))
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, Theme.contentHInset)
            .padding(.vertical, Theme.contentVInset)
        }
    }

    private func entryCard(icon: String, title: String, subtitle: String, count: String? = nil) -> some View {
        HStack(spacing: 12) {
            Image(systemName: icon).font(.title3).foregroundColor(Theme.accent).frame(width: 28)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.subheadline.weight(.semibold)).foregroundColor(Theme.textPrimary)
                Text(subtitle).font(.caption).foregroundColor(Theme.textSecondary)
                    .multilineTextAlignment(.leading)
            }
            Spacer(minLength: 8)
            if let count { Text(count).font(.caption).foregroundColor(Theme.textSecondary) }
            Image(systemName: "chevron.right").font(.caption).foregroundColor(Theme.textSecondary)
        }
        .padding(14).background(Theme.surface).clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "book.closed")
                .font(.largeTitle)
                .foregroundColor(Theme.textSecondary)
            Text(L("教程内容加载失败"))
                .font(.subheadline)
                .foregroundColor(Theme.textPrimary)
            Text(L("请重装 App 或联系我们"))
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// 文章行：序号 + 标题 + 摘要。
struct LearnRow: View {
    let index: Int
    let article: LessonArticle

    var body: some View {
        HStack(spacing: 12) {
            Text("\(index)")
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundColor(Theme.accent)
                .frame(width: 26, height: 26)
                .background(Theme.accent.opacity(0.14))
                .clipShape(Circle())
            VStack(alignment: .leading, spacing: 4) {
                Text(article.title).font(.subheadline.weight(.semibold)).foregroundColor(Theme.textPrimary)
                Text(article.summary).font(.caption).foregroundColor(Theme.textSecondary)
                    .lineLimit(2).multilineTextAlignment(.leading)
            }
            Spacer(minLength: 8)
            Image(systemName: "chevron.right").font(.caption).foregroundColor(Theme.textSecondary)
        }
        .padding(14)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

/// 新手入门列表：按「认识 App / 四步看懂市场 / 避坑」三组分段，序号连续（读的顺序）。
struct GuideListView: View {
    let guides: [LessonArticle]

    private static let groups: [(title: String, ids: [String])] = [
        ("认识这个 App", ["guide-start", "guide-app-tour", "guide-app-radar", "guide-app-detail"]),
        ("四步看懂市场", ["guide-market", "guide-sector", "guide-fundamentals", "guide-structure",
                        "guide-relation", "guide-combine"]),
        ("避坑", ["guide-mistakes"]),
    ]

    var body: some View {
        ScrollView {
            VStack(spacing: 10) {
                ForEach(sections, id: \.title) { section in
                    Text(L(section.title))
                        .font(.headline).foregroundColor(Theme.textPrimary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 8).padding(.top, 10)
                    ForEach(section.items, id: \.article.id) { item in
                        NavigationLink {
                            LessonDetailView(article: item.article, footnote: L("以上为知识讲解，仅供学习参考，不构成投资建议。"))
                        } label: {
                            LearnRow(index: item.index, article: item.article)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding(.horizontal, Theme.contentHInset)
            .padding(.vertical, Theme.contentVInset)
        }
        .background(Theme.background)
        .navigationTitle(L("新手入门"))
        .navigationBarTitleDisplayMode(.inline)
    }

    private typealias Item = (index: Int, article: LessonArticle)

    /// 序号按全部文章的原顺序给；不在任何分组里的新文章归入最后一组，不会丢。
    private var sections: [(title: String, items: [Item])] {
        let indexed: [Item] = guides.enumerated().map { ($0.offset + 1, $0.element) }
        var known = Set<String>()
        var out: [(title: String, items: [Item])] = Self.groups.compactMap { g in
            let items = indexed.filter { g.ids.contains($0.article.id) }
            known.formUnion(g.ids)
            return items.isEmpty ? nil : (g.title, items)
        }
        let rest = indexed.filter { !known.contains($0.article.id) }
        if !rest.isEmpty {
            if let last = out.indices.last { out[last].items += rest } else { out.append(("新手入门", rest)) }
        }
        return out
    }
}

/// 缠论入门列表：顺序是有意编排的（从 K 线处理递进到级别），给序号。
struct LessonListView: View {
    let articles: [LessonArticle]

    var body: some View {
        ScrollView {
            VStack(spacing: 10) {
                Text(L("按顺序读下来，就能看懂分析页上画的每一条线。"))
                    .font(.footnote).foregroundColor(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 8)
                ForEach(Array(articles.enumerated()), id: \.element.id) { index, article in
                    NavigationLink { LessonDetailView(article: article) } label: {
                        LearnRow(index: index + 1, article: article)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, Theme.contentHInset)
            .padding(.vertical, Theme.contentVInset)
        }
        .background(Theme.background)
        .navigationTitle(L("缠论入门"))
        .navigationBarTitleDisplayMode(.inline)
    }
}
