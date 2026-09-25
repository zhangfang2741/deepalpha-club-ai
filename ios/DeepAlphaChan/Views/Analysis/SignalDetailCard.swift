import SwiftUI

/// 边框虚实对应确认状态，色块深浅复用雷达的强度映射。
struct SignalDetailCard: View {
    let signal: Signal
    var isStatic = false

    private var directionColor: Color { signal.isBuy ? Theme.up : Theme.down }
    private var strengthColor: Color {
        SignalFormatting.radarColor(side: signal.isBuy ? "buy" : "sell",
                                    depth: SignalFormatting.strengthDepth(signal.strength.rawValue))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                GlossaryLink(term: "买卖点") {
                    Label(signal.label, systemImage: signal.isBuy ? "arrow.up.circle.fill" : "arrow.down.circle.fill")
                        .font(.headline)
                        .foregroundStyle(directionColor)
                        .frame(minHeight: 44)
                }
                Spacer(minLength: 8)
                Text(signal.time).font(.caption).foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            WrapLayout(spacing: 10, lineSpacing: 8) {
                Label(signal.confirmed ? L("已确认") : L("未确认"),
                      systemImage: signal.confirmed ? "checkmark.circle" : "circle.dashed")
                HStack(spacing: 5) {
                    Circle().fill(strengthColor).frame(width: 12, height: 12)
                    Text(L("强度：%@", SignalFormatting.strengthLabel(signal.strength)))
                }
                Text(L("价位 %@", String(format: "%.2f", signal.price))).monospacedDigit()
            }
            .font(.caption)
            .foregroundStyle(Theme.textSecondary)
            .fixedSize(horizontal: false, vertical: true)

            Text(HeadlineHighlighter.highlight(signal.description))
                .font(AnalysisType.body)
                .foregroundStyle(Theme.textPrimary)
                .lineSpacing(AnalysisType.bodyLineSpacing)
                .fixedSize(horizontal: false, vertical: true)
            if !signal.confirmed {
                Text(L("对应结构仍在延伸，后续 K 线可能使信号改变或消失。"))
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if isStatic {
                explanation
            } else {
                DisclosureGroup {
                    explanation.padding(.top, 8)
                } label: {
                    Text(L("为什么是这个信号"))
                        .font(.subheadline.weight(.medium))
                        .frame(minHeight: 44)
                }
                .tint(Theme.textSecondary)
            }
        }
        .padding(16)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
        .overlay {
            RoundedRectangle(cornerRadius: 14)
                .strokeBorder(directionColor.opacity(0.5),
                              style: StrokeStyle(lineWidth: 1, dash: signal.confirmed ? [] : [5, 4]))
        }
    }

    private var explanation: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(SignalFormatting.typeExplanation(signal.type))
                .font(AnalysisType.body)
                .foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if signal.type == .buy1 || signal.type == .sell1 {
                WrapLayout(spacing: 12, lineSpacing: 8) {
                    ratio(L("价差比"), value: signal.priceRatio)
                    ratio(L("量能比"), value: signal.volumeRatio)
                    ratio(L("时长比"), value: signal.lengthRatio)
                }
                Text(L("比值为当前笔与比较基准之比，小于 1 表示该项减弱；缺失数据以 — 表示。背驰不等于反转。"))
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                AnalysisTermLink(term: "背驰", color: Theme.divergence)
            } else {
                Text(L("二、三类强度综合参考中枢级别与回抽余地，不由类型编号决定。"))
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                AnalysisTermLink(term: "买卖点", color: directionColor)
            }
        }
    }

    private func ratio(_ title: String, value: Double?) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption).foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            Text(value.map { String(format: "%.2f", $0) } ?? "—")
                .font(.subheadline.monospacedDigit().bold())
                .foregroundStyle(Theme.divergence)
        }
    }
}
