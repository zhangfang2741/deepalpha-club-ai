import SwiftUI

/// 使用稳定的中文术语索引打开当前语言的学习词条。
struct AnalysisTermLink: View {
    let term: String
    let color: Color

    var body: some View {
        GlossaryLink(term: term) {
            Label(L(term), systemImage: "questionmark.circle")
                .font(.subheadline.weight(.medium))
                .foregroundStyle(color)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
        }
        .accessibilityHint(L("查看学习词条"))
    }
}
