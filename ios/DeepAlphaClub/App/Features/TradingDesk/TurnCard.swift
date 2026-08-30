import SwiftUI
import DeepAlphaCore

/// 一张发言卡。辩论卡按 polarity 分色（前端无需认识门派）；人工意见蓝色。
struct TurnCard: View {
    let turn: Turn
    var streaming = false

    private var tint: Color {
        if turn.human { return .blue }
        return turn.debate?.polarity.tint ?? Color(.systemGray)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            header
            if !turn.tools.isEmpty {
                ToolChips(items: turn.tools)
            }
            if !turn.text.isEmpty {
                MarkdownText(markdown: turn.text)
            }
            if streaming {
                StreamingCursor()
            }
            if let thinking = turn.thinking, !thinking.isEmpty {
                thinkingSection(thinking)
            }
            if let signal = turn.signal {
                SignalChip(dir: signal.dir, conf: signal.conf, extracted: signal.extracted)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(tint.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(tint.opacity(0.25), lineWidth: 1))
        // 看空方缩进（对齐 web bear 的 ml-8 错位感）
        .padding(.leading, turn.debate?.polarity == .bear ? 20 : 0)
    }

    private var header: some View {
        HStack(spacing: 8) {
            Text(turn.avatar)
                .font(.caption2.monospaced().weight(.bold))
                .foregroundStyle(tint)
                .frame(width: 26, height: 26)
                .background(tint.opacity(0.15), in: RoundedRectangle(cornerRadius: 6))
            Text(turn.name)
                .font(.footnote.weight(.semibold))
                .lineLimit(1)
            if let debate = turn.debate {
                Text("第 \(debate.round) 轮 · \(debate.sideLabel)")
                    .font(.caption2.monospaced())
                    .foregroundStyle(tint)
            }
            Spacer(minLength: 4)
            if !turn.role.isEmpty {
                Text(turn.role)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.tertiary)
                    .lineLimit(1)
            }
        }
    }

    private func thinkingSection(_ thinking: String) -> some View {
        DisclosureGroup {
            MarkdownText(markdown: thinking)
                .padding(.top, 6)
        } label: {
            Label("推理过程", systemImage: "brain")
                .font(.caption2.monospaced().weight(.semibold))
        }
        .tint(.purple)
        .padding(10)
        .background(Color.purple.opacity(0.07), in: RoundedRectangle(cornerRadius: 8))
    }
}

/// 流式打字光标（蓝色闪烁竖条）。
struct StreamingCursor: View {
    @State private var on = true
    var body: some View {
        RoundedRectangle(cornerRadius: 1)
            .fill(.blue)
            .frame(width: 3, height: 14)
            .opacity(on ? 1 : 0.2)
            .onAppear {
                withAnimation(.easeInOut(duration: 0.6).repeatForever()) { on = false }
            }
    }
}

/// 工具调用标签（每行一个，工具名可能较长，不做横向挤压）。
struct ToolChips: View {
    let items: [String]
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(items, id: \.self) { item in
                Text("⚙ \(item)")
                    .font(.caption2.monospaced())
                    .foregroundStyle(.blue)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.blue.opacity(0.08),
                                in: RoundedRectangle(cornerRadius: 5))
            }
        }
    }
}

/// 轻量 markdown 渲染：Core 的块解析 + AttributedString inline。
struct MarkdownText: View {
    let markdown: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(MarkdownBlockParser.parse(markdown).enumerated()),
                    id: \.offset) { _, block in
                blockView(block)
            }
        }
        .font(.footnote)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private func blockView(_ block: MarkdownBlock) -> some View {
        switch block {
        case .heading(let level, let text):
            Text(inline(text))
                .font(level <= 2 ? .subheadline.weight(.bold) : .footnote.weight(.semibold))
                .padding(.top, 2)
                .frame(maxWidth: .infinity, alignment: .leading)
        case .bullet(let items):
            VStack(alignment: .leading, spacing: 3) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text("•").foregroundStyle(.tertiary)
                        Text(inline(item)).foregroundStyle(.secondary)
                        Spacer(minLength: 0)
                    }
                }
            }
        case .ordered(let items):
            VStack(alignment: .leading, spacing: 3) {
                ForEach(Array(items.enumerated()), id: \.offset) { i, item in
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text("\(i + 1).").monospacedDigit().foregroundStyle(.tertiary)
                        Text(inline(item)).foregroundStyle(.secondary)
                        Spacer(minLength: 0)
                    }
                }
            }
        case .code(let code):
            ScrollView(.horizontal, showsIndicators: false) {
                Text(code)
                    .font(.caption.monospaced())
                    .foregroundStyle(.primary)
                    .padding(8)
            }
            .background(Color(.tertiarySystemBackground),
                        in: RoundedRectangle(cornerRadius: 8))
        case .paragraph(let text):
            Text(inline(text))
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// inline markdown（**粗体**、*斜体*、`code`、[链接](url)）交给系统解析。
    private func inline(_ s: String) -> AttributedString {
        (try? AttributedString(
            markdown: s,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)))
            ?? AttributedString(s)
    }
}
