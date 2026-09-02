import SwiftUI

/// 可点击的术语。点击弹出对应的教程词条。
///
/// 术语在 GlossaryIndex 里查不到时**退化为普通文本**——词条还没写完的时候，
/// 界面上不该出现点了没反应的死链。
struct GlossaryLink<Label: View>: View {
    let term: String
    @ViewBuilder var label: () -> Label

    @State private var article: LessonArticle?

    var body: some View {
        if let entry = GlossaryIndex.article(for: term) {
            Button {
                article = entry
            } label: {
                label()
            }
            .buttonStyle(.plain)
            .sheet(item: $article) { a in
                NavigationStack {
                    LessonDetailView(article: a, showsCloseButton: true)
                }
                .presentationDetents([.medium, .large])
                .preferredColorScheme(.dark)
                // 抑制的是弹出的术语详情 sheet，不是词条本身 —— 词条列表在
                // 结果页里是合法的分享内容。sheet 弹出后它成为协调器栈顶，
                // 截图事件到它这里被吞掉：底下的结果页/全屏图表页收不到
                // onDisappear、监听还活着，一旦响应就会和本 sheet 抢
                // presenter，输掉后预览状态卡在非 nil，本页分享从此失效。
                .suppressScreenshotShare()
            }
        } else {
            label()
        }
    }
}
