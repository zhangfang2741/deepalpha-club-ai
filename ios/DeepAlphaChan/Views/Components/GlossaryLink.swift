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
            }
        } else {
            label()
        }
    }
}
