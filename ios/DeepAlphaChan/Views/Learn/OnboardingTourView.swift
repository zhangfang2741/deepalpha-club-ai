import SwiftUI

/// 新手导览：几页讲清「这个 App 怎么看」。首次进入雷达时弹一次，学习页和「我的」里可以随时重看。
/// 只讲思路和边界，不讲具体操作；文字都是大白话。
struct OnboardingTourView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var page = 0

    /// 标记是否看过（UserDefaults）。
    static let seenKey = "onboarding_tour_seen_v1"

    private struct Page { let icon: String; let title: String; let text: String }

    private var pages: [Page] {
        [
            Page(icon: "map", title: L("从大到小看市场"),
                 text: L("先看市场，再看行业，再看公司基本面，最后看价格走势的结构。四步连起来，才是一幅完整的画面。")),
            Page(icon: "chart.line.uptrend.xyaxis", title: L("顶部：市场和行业"),
                 text: L("顶部的卡片告诉你大盘现在是「逐利、观望还是避险」，行业横条告诉你哪些行业更强。每一项是怎么算的，学习页的「方法说明」里都有。")),
            Page(icon: "circle.hexagongrid", title: L("中间：雷达上的气泡"),
                 text: L("每个气泡是一只股票近期出现的一个结构信号。红色是买点类、绿色是卖点类，颜色越深结构越清晰，越靠中心越新。它描述走势位置，不是买卖指令。")),
            Page(icon: "list.bullet.rectangle", title: L("基本面名单"),
                 text: L("雷达只画基本面靠前的股票，名单里能看到它们的综合等级。基本面好不等于股价会涨，它更像一道过滤，帮你缩小范围。")),
            Page(icon: "questionmark.circle", title: L("看不懂就点问号"),
                 text: L("每一项是怎么算的，都在学习页的「方法说明」；不认识的词点旁边的问号，学习页里还有新手入门和名词小词典。理解之后，决定由你来做。")),
        ]
    }

    var body: some View {
        VStack(spacing: 0) {
            TabView(selection: $page) {
                ForEach(Array(pages.enumerated()), id: \.offset) { idx, p in
                    VStack(spacing: 18) {
                        Spacer(minLength: 20)
                        Image(systemName: p.icon)
                            .font(.system(size: 54, weight: .light))
                            .foregroundStyle(Theme.accent)
                        Text(p.title)
                            .font(.title2.bold()).foregroundStyle(Theme.textPrimary)
                            .multilineTextAlignment(.center)
                        Text(p.text)
                            .font(.body).foregroundStyle(Theme.textSecondary)
                            .multilineTextAlignment(.leading).lineSpacing(6)
                            .padding(.horizontal, 28)
                        Spacer(minLength: 20)
                    }
                    .tag(idx)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .always))
            .indexViewStyle(.page(backgroundDisplayMode: .always))

            Text(L("以上内容仅为知识讲解和事实陈列，不构成投资建议。"))
                .font(.caption2).foregroundStyle(Theme.textSecondary)
                .padding(.bottom, 8)

            Button {
                if page < pages.count - 1 { withAnimation { page += 1 } } else { finish() }
            } label: {
                Text(page < pages.count - 1 ? L("下一步") : L("开始使用"))
                    .font(.headline).frame(maxWidth: .infinity).padding(.vertical, 14)
                    .background(Theme.accent, in: RoundedRectangle(cornerRadius: 12))
                    .foregroundStyle(.white)
            }
            .padding(.horizontal, 24)
            Button(L("跳过")) { finish() }
                .font(.footnote).foregroundStyle(Theme.textSecondary)
                .padding(.vertical, 12)
        }
        .background(Theme.background)
        .presentationDragIndicator(.visible)
    }

    private func finish() {
        UserDefaults.standard.set(true, forKey: Self.seenKey)
        dismiss()
    }

    static var hasSeen: Bool { UserDefaults.standard.bool(forKey: seenKey) }
}
