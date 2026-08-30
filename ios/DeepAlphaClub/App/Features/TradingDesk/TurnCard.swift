import SwiftUI
import DeepAlphaCore

/// 一张发言卡。辩论卡按 polarity 分色（前端无需认识门派）；人工意见蓝色。
struct TurnCard: View {
    let turn: Turn
    var streaming = false

    private var tint: Color {
        if turn.human { return Theme.human }
        return turn.debate?.polarity.tint ?? Theme.textSecondary
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
                    .foregroundStyle(Theme.textTertiary)
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
        .tint(Theme.accent)
        .padding(10)
        .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 8))
    }
}

/// 流式打字光标（蓝色闪烁竖条）。
struct StreamingCursor: View {
    @State private var on = true
    var body: some View {
        RoundedRectangle(cornerRadius: 1)
            .fill(Theme.accent)
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
                    .foregroundStyle(Theme.accent)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Theme.accent.opacity(0.08),
                                in: RoundedRectangle(cornerRadius: 5))
            }
        }
    }
}
