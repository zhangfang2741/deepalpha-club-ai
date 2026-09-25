import SwiftUI

/// 历史买卖点的一行：默认收起，只有一行信息；点开才展开"为什么是这个信号"。
/// 边框虚实对应确认状态，色块深浅复用雷达的强度映射。
struct SignalDetailCard: View {
    let signal: Signal
    var isStatic = false

    @State private var expanded = false

    private var directionColor: Color { signal.isBuy ? Theme.up : Theme.down }
    private var strengthColor: Color {
        SignalFormatting.radarColor(side: signal.isBuy ? "buy" : "sell",
                                    depth: SignalFormatting.strengthDepth(signal.strength.rawValue))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                if !isStatic { withAnimation(.easeInOut(duration: 0.15)) { expanded.toggle() } }
            } label: {
                row
            }
            .buttonStyle(.plain)
            .disabled(isStatic)

            if isStatic || expanded {
                explanation
                    .padding(.top, 2)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 10))
        .overlay {
            RoundedRectangle(cornerRadius: 10)
                .strokeBorder(directionColor.opacity(0.35),
                              style: StrokeStyle(lineWidth: 1, dash: signal.confirmed ? [] : [4, 3]))
        }
    }

    private var row: some View {
        HStack(spacing: 8) {
            Image(systemName: signal.isBuy ? "arrow.up.circle.fill" : "arrow.down.circle.fill")
                .foregroundStyle(directionColor)
                .font(.footnote)
            Text(signal.label)
                .font(.footnote.weight(.semibold))
                .foregroundStyle(Theme.textPrimary)
            Circle().fill(strengthColor).frame(width: 7, height: 7)
            Image(systemName: signal.confirmed ? "checkmark.circle" : "circle.dashed")
                .font(.caption2)
                .foregroundStyle(Theme.textSecondary)
            Spacer(minLength: 6)
            Text(String(format: "%.2f", signal.price))
                .font(.caption.monospacedDigit())
                .foregroundStyle(Theme.textSecondary)
            Text(signal.time)
                .font(.caption2)
                .foregroundStyle(Theme.textSecondary)
            if !isStatic {
                Image(systemName: expanded ? "chevron.up" : "chevron.down")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(Theme.textSecondary)
            }
        }
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityLabel(L("%@ %@ %@ 价位 %@",
                              signal.label, signal.confirmed ? L("已确认") : L("未确认"),
                              SignalFormatting.strengthLabel(signal.strength),
                              String(format: "%.2f", signal.price)))
    }

    private var explanation: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(HeadlineHighlighter.highlight(signal.description))
                .font(.caption)
                .foregroundStyle(Theme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            Text(SignalFormatting.typeExplanation(signal.type))
                .font(.caption)
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if !signal.confirmed {
                Text(L("对应结构仍在延伸，后续 K 线可能使信号改变或消失。"))
                    .font(.caption2)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if signal.type == .buy1 || signal.type == .sell1 {
                WrapLayout(spacing: 12, lineSpacing: 4) {
                    ratio(L("价差比"), value: signal.priceRatio)
                    ratio(L("量能比"), value: signal.volumeRatio)
                    ratio(L("时长比"), value: signal.lengthRatio)
                }
                AnalysisTermLink(term: "背驰", color: Theme.divergence)
            } else {
                AnalysisTermLink(term: "买卖点", color: directionColor)
            }
        }
    }

    private func ratio(_ title: String, value: Double?) -> some View {
        HStack(spacing: 3) {
            Text(title).font(.caption2).foregroundStyle(Theme.textSecondary)
            Text(value.map { String(format: "%.2f", $0) } ?? "—")
                .font(.caption.monospacedDigit().bold())
                .foregroundStyle(Theme.divergence)
        }
    }
}
