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

    private var list: some View {
        ScrollView {
            VStack(spacing: 10) {
                if !guides.isEmpty { guideSection }
                methodsRow
                glossaryRow
                sectionTitle(L("缠论入门"))
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

    private func sectionTitle(_ text: String) -> some View {
        Text(text)
            .font(.headline).foregroundColor(Theme.textPrimary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 8).padding(.top, 10)
    }

    /// 新手入门：不懂金融也能读，讲「怎么看这个 App、各项数字是什么意思、常见误区」。
    private var guideSection: some View {
        VStack(spacing: 10) {
            sectionTitle(L("新手入门"))
            Text(L("没学过金融也能读：先弄明白这个 App 的思路，再一步步看懂每个数字。"))
                .font(.footnote).foregroundColor(Theme.textSecondary)
                .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 8)
            Button { showTour = true } label: {
                HStack(spacing: 10) {
                    Image(systemName: "play.circle.fill").font(.title3).foregroundColor(Theme.accent)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(L("30 秒看懂这个 App")).font(.subheadline.weight(.semibold)).foregroundColor(Theme.textPrimary)
                        Text(L("重新看一遍新手导览")).font(.caption).foregroundColor(Theme.textSecondary)
                    }
                    Spacer()
                    Image(systemName: "chevron.right").font(.caption).foregroundColor(Theme.textSecondary)
                }
                .padding(14).background(Theme.surface).clipShape(RoundedRectangle(cornerRadius: 12))
            }
            .buttonStyle(.plain)
            ForEach(Array(guides.enumerated()), id: \.element.id) { index, article in
                NavigationLink {
                    LessonDetailView(article: article, footnote: L("以上为知识讲解，仅供学习参考，不构成投资建议。"))
                } label: {
                    row(index: index + 1, article: article)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var methodsRow: some View {
        NavigationLink { MethodsView() } label: {
            HStack(spacing: 10) {
                Image(systemName: "function").font(.title3).foregroundColor(Theme.accent)
                VStack(alignment: .leading, spacing: 2) {
                    Text(L("方法说明")).font(.subheadline.weight(.semibold)).foregroundColor(Theme.textPrimary)
                    Text(L("市场状态、行业强弱、基本面、买卖点……都是怎么算的")).font(.caption).foregroundColor(Theme.textSecondary)
                }
                Spacer()
                Image(systemName: "chevron.right").font(.caption).foregroundColor(Theme.textSecondary)
            }
            .padding(14).background(Theme.surface).clipShape(RoundedRectangle(cornerRadius: 12))
        }
        .buttonStyle(.plain)
        .padding(.top, 6)
    }

    private var glossaryRow: some View {
        NavigationLink { GlossaryListView() } label: {
            HStack(spacing: 10) {
                Image(systemName: "character.book.closed").font(.title3).foregroundColor(Theme.accent)
                VStack(alignment: .leading, spacing: 2) {
                    Text(L("名词小词典")).font(.subheadline.weight(.semibold)).foregroundColor(Theme.textPrimary)
                    Text(L("逐利、避险、基点、倒挂、百分位……一查就懂")).font(.caption).foregroundColor(Theme.textSecondary)
                }
                Spacer()
                Image(systemName: "chevron.right").font(.caption).foregroundColor(Theme.textSecondary)
            }
            .padding(14).background(Theme.surface).clipShape(RoundedRectangle(cornerRadius: 12))
        }
        .buttonStyle(.plain)
        .padding(.top, 6)
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
