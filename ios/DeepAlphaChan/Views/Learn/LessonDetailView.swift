import SwiftUI

/// 词条详情。既作为学习页的下钻目标，也作为术语点击后弹出的 sheet。
struct LessonDetailView: View {
    let article: LessonArticle
    /// 以 sheet 形式弹出时显示关闭按钮；从列表 push 进来时不需要。
    var showsCloseButton = false
    /// 页脚说明；缠论词条用默认的「通行解读」，新手入门等其它内容传自己的。
    var footnote: String? = nil

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        content
            .background(Theme.background)
            .navigationTitle(article.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if showsCloseButton {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button(L("完成")) { dismiss() }
                    }
                }
            }
    }

    private var content: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text(article.summary)
                    .font(.subheadline)
                    .foregroundColor(Theme.textSecondary)
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.surface)
                    .clipShape(RoundedRectangle(cornerRadius: 12))

                // 示意图放在摘要之后、正文之前：先看图建立直观印象，再读定义。
                if let spec = LessonDiagrams.spec(for: article.id) {
                    VStack(alignment: .leading, spacing: 6) {
                        LessonDiagram(spec: spec)
                        Text(L("示意图，与分析页使用同一套配色"))
                            .font(.caption2)
                            .foregroundColor(Theme.textSecondary)
                    }
                }

                // 按空行切段落分别渲染，而不是把整篇丢给一个 Text：
                // AttributedString 的 Markdown 解析默认会把换行折叠掉，
                // 整篇渲染出来会是没有段落的一大坨。
                ForEach(Array(paragraphs.enumerated()), id: \.offset) { _, paragraph in
                    if let shot = LessonScreenshot.parse(paragraph) {
                        shot
                    } else {
                        Text(markdown(paragraph))
                            .font(.system(size: 15))
                            .foregroundColor(Theme.textPrimary)
                            .lineSpacing(6)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .textSelection(.enabled)
                    }
                }

                Text(footnote ?? L("以上为缠论的通行解读，仅供学习参考，不构成投资建议。"))
                    .font(.caption2)
                    .foregroundColor(Theme.textSecondary)
                    .padding(.top, 8)
            }
            // 这一页正文是裸 Text（没有卡片背景兜底），水平边距不跟着列表页收窄，
            // 否则文字会直接贴到屏幕边上。
            .padding(18)
        }
    }

    private var paragraphs: [String] {
        article.body
            .components(separatedBy: "\n\n")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    /// 解析行内 Markdown。解析失败就退回纯文本，不能因为一个星号没配对就丢内容。
    private func markdown(_ text: String) -> AttributedString {
        // .inlineOnlyPreservingWhitespace 保留段落内的单换行（项目符号列表靠它分行）
        (try? AttributedString(
            markdown: text,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        )) ?? AttributedString(text)
    }
}

/// 正文里的 App 截图：单独成段的 `![说明](资源名)`。
///
/// 截图存在 Assets.xcassets/Guide 里，按界面语言取：英文界面优先用 `资源名-en`，
/// 没有就退回中文版。资源缺失时整段不显示（不出现空白框），内容测试会守护引用都存在。
/// 截图只裁内容区域（不含状态栏、页面标题），正文里与文字同宽显示，点开全屏看原图。
struct LessonScreenshot: View {
    let caption: String
    let image: UIImage

    @State private var zoomed = false

    /// 不是截图语法、或资源找不到时返回 nil，调用方按普通段落渲染。
    static func parse(_ paragraph: String) -> LessonScreenshot? {
        guard paragraph.hasPrefix("!["), paragraph.hasSuffix(")"),
              let mid = paragraph.range(of: "](") else { return nil }
        let caption = String(paragraph[paragraph.index(paragraph.startIndex, offsetBy: 2)..<mid.lowerBound])
        let name = String(paragraph[mid.upperBound..<paragraph.index(before: paragraph.endIndex)])
        let localized = Localized.language() == .english ? UIImage(named: name + "-en") : nil
        guard let image = localized ?? UIImage(named: name) else { return nil }
        return LessonScreenshot(caption: caption, image: image)
    }

    var body: some View {
        // 截图本身就是 App 界面，直接贴在正文里会和真实界面混在一起：
        // 外面套一层浅一级底色的框、留内边距，图片单独圆角描边，说明放在框内底部。
        Button { zoomed = true } label: {
            VStack(alignment: .leading, spacing: 10) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
                    .frame(maxWidth: .infinity)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                    .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.border, lineWidth: 1))
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Image(systemName: "iphone")
                        .font(.caption2)
                    Text(caption)
                        .font(.caption)
                        .multilineTextAlignment(.leading)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    Image(systemName: "arrow.up.left.and.arrow.down.right")
                        .font(.caption2)
                }
                .foregroundColor(Theme.textSecondary)
                .padding(.horizontal, 2)
            }
            .padding(12)
            .background(Theme.surfaceAlt)
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(Theme.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(caption)
        .accessibilityHint(L("点开看大图"))
        .padding(.vertical, 6)
        .fullScreenCover(isPresented: $zoomed) {
            ZStack(alignment: .topTrailing) {
                Color.black.ignoresSafeArea()
                // 矮图垂直居中，高图可以上下滚动
                GeometryReader { geo in
                    ScrollView {
                        Image(uiImage: image)
                            .resizable()
                            .scaledToFit()
                            .padding(.horizontal, 12)
                            .padding(.vertical, 56)
                            .frame(minHeight: geo.size.height)
                    }
                }
                Button { zoomed = false } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.title)
                        .foregroundStyle(.white.opacity(0.85))
                        .padding(16)
                }
                .accessibilityLabel(L("关闭"))
            }
            .onTapGesture { zoomed = false }
        }
    }
}
