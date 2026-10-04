import SwiftUI

/// 历史买卖点的一行：默认收起，只有一行信息；点开才展开"为什么是这个信号"。
/// 色块深浅复用雷达的强度映射；确认状态已经用行内的勾选/虚线圆图标表达过，
/// 不再另用边框虚实重复一遍。
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
    }

    private var row: some View {
        HStack(spacing: 8) {
            Image(systemName: signal.isBuy ? "arrow.up.circle.fill" : "arrow.down.circle.fill")
                .foregroundStyle(directionColor)
                .font(AnalysisType.title)
            Text(signal.label)
                .font(AnalysisType.title)
                .foregroundStyle(Theme.textPrimary)
            Circle().fill(strengthColor).frame(width: 7, height: 7)
            if signal.isCandidate {
                Text(L("待确认"))
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(Theme.textSecondary)
                    .padding(.horizontal, 5).padding(.vertical, 1)
                    .overlay(Capsule().stroke(directionColor, style: StrokeStyle(lineWidth: 1, dash: [3, 2])))
            } else {
                Image(systemName: signal.confirmed ? "checkmark.circle" : "circle.dashed")
                    .font(.caption2)
                    .foregroundStyle(Theme.textSecondary)
            }
            Spacer(minLength: 6)
            Text(String(format: "%.2f", signal.price))
                .font(.caption.monospacedDigit())
                .foregroundStyle(Theme.textSecondary)
            // 出现日（笔走完确认的那天）与图上标记（所在笔的极值 K 线）可能差好几周：
            // 两个日期不同时折叠行就都写出来，对得上图，不必展开才知道
            VStack(alignment: .trailing, spacing: 1) {
                Text(signal.displayTime)
                    .font(.caption2)
                    .foregroundStyle(Theme.textSecondary)
                if signal.displayTime != signal.time {
                    Text(L("图上 %@", signal.time))
                        .font(.system(size: 9))
                        .foregroundStyle(Theme.textSecondary.opacity(0.7))
                }
            }
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
                .font(AnalysisType.body)
                .foregroundStyle(Theme.textPrimary)
                .lineSpacing(AnalysisType.bodyLineSpacing)
                .fixedSize(horizontal: false, vertical: true)
            Text(SignalFormatting.typeExplanation(signal.type))
                .font(AnalysisType.body)
                .foregroundStyle(Theme.textSecondary)
                .lineSpacing(AnalysisType.bodyLineSpacing)
                .fixedSize(horizontal: false, vertical: true)
            if signal.displayTime != signal.time {
                // 雷达与这里的日期都是出现日；图上标记画在所属笔的极值 K 线，所以会在出现日左侧
                Text(L("%@ 出现；所在笔的极值在 %@，图上标记画在那根 K 线。", signal.displayTime, signal.time))
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if signal.isCandidate {
                Text(L("所在的最后一笔还在走，端点可能延伸甚至回到中枢，按缠论尚不成立；这一笔走完才算买卖点。"))
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            } else if !signal.confirmed {
                Text(L("对应结构仍在延伸，后续 K 线可能使信号改变或消失。"))
                    .font(.caption)
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
