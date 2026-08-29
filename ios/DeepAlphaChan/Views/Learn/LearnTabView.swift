import SwiftUI

/// 学习 Tab：缠论概念词条列表。
struct LearnTabView: View {
    private let articles = LessonStore.all

    var body: some View {
        NavigationStack {
            Group {
                if articles.isEmpty {
                    emptyState
                } else {
                    list
                }
            }
            .background(Theme.background)
            .navigationTitle(L("缠论入门"))
        }
    }

    private var list: some View {
        ScrollView {
            VStack(spacing: 10) {
                intro

                // 词条顺序在 JSON 里是有意编排的（从 K 线处理递进到级别），
                // 所以给序号，让人知道该按顺序读。
                ForEach(Array(articles.enumerated()), id: \.element.id) { index, article in
                    NavigationLink {
                        LessonDetailView(article: article)
                    } label: {
                        row(index: index + 1, article: article)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, Theme.contentHInset)
            .padding(.vertical, Theme.contentVInset)
        }
    }

    private var intro: some View {
        Text(L("按顺序读下来，就能看懂分析页上画的每一条线。"))
            .font(.footnote)
            .foregroundColor(Theme.textSecondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            // 裸文本，补回卡片那一层内边距，才和下方卡片里的文字对齐
            .padding(.horizontal, 8)
            .padding(.bottom, 4)
    }

    private func row(index: Int, article: LessonArticle) -> some View {
        HStack(spacing: 12) {
            Text("\(index)")
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundColor(Theme.accent)
                .frame(width: 26, height: 26)
                .background(Theme.accent.opacity(0.14))
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 4) {
                Text(article.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundColor(Theme.textPrimary)
                Text(article.summary)
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
            }

            Spacer(minLength: 8)

            Image(systemName: "chevron.right")
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
        }
        .padding(14)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
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
