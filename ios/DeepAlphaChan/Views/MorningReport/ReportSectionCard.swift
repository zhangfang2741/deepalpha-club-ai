import SwiftUI

// MARK: - 四层结构（事实/洞察/预测/验证）

/// 晨报结构段落的四个认知层次，颜色与后端/前端约定一致。
enum MRLayer {
    case fact, insight, prediction, verification

    var label: String {
        switch self {
        case .fact: return L("事实")
        case .insight: return L("洞察")
        case .prediction: return L("预测")
        case .verification: return L("验证")
        }
    }

    var color: Color {
        switch self {
        case .fact: return Color(hex: 0x7CB0FF)
        case .insight: return Color(hex: 0xB79CFF)
        case .prediction: return Color(hex: 0xF5B94F)
        case .verification: return Color(hex: 0x5BD99A)
        }
    }
}

/// 单个四层行：彩色 pill 标签 + 正文。
private struct LayerRow: View {
    let layer: MRLayer
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Text(layer.label)
                .font(.caption2.bold())
                .foregroundColor(layer.color)
                .padding(.horizontal, 7)
                .padding(.vertical, 3)
                .background(layer.color.opacity(0.13), in: RoundedRectangle(cornerRadius: 5))
                .overlay(
                    RoundedRectangle(cornerRadius: 5)
                        .stroke(layer.color.opacity(0.3), lineWidth: 0.5)
                )
            Text(text)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 1)
    }
}

/// 四层结构卡：标题条 + 每条 entry 的 fact/insight/prediction/verification 四行。
struct ReportSectionCard: View {
    let section: MRSection

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                RoundedRectangle(cornerRadius: 1.5)
                    .fill(
                        LinearGradient(
                            colors: [Theme.accent, Color(hex: 0x60A5FA)],
                            startPoint: .top, endPoint: .bottom
                        )
                    )
                    .frame(width: 4, height: 14)
                Text(section.title.resolved)
                    .font(.subheadline.bold())
                    .foregroundColor(Theme.textPrimary)
            }
            ForEach(section.entries, id: \.self) { entry in
                VStack(alignment: .leading, spacing: 6) {
                    LayerRow(layer: .fact, text: entry.fact.resolved)
                    LayerRow(layer: .insight, text: entry.insight.resolved)
                    LayerRow(layer: .prediction, text: entry.prediction.resolved)
                    LayerRow(layer: .verification, text: entry.verification.resolved)
                }
                .padding(.vertical, 2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.border, lineWidth: 1))
    }
}

// MARK: - 今日核心判断大卡

/// 核心判断卡：headline 正文 + 指标小卡（name / value 按 direction 着色 / note）。
struct HeadlineCard: View {
    let headline: String
    let metrics: [MRMetric]

    private func directionColor(_ direction: String) -> Color {
        switch direction {
        case "up": return Theme.up
        case "down": return Theme.down
        default: return Theme.textSecondary
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "star.fill")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(
                        LinearGradient(
                            colors: [Color(hex: 0xF5B94F), Color(hex: 0xF59E0B)],
                            startPoint: .top, endPoint: .bottom
                        )
                    )
                Text(L("今日核心判断"))
                    .font(.subheadline.bold())
                    .foregroundColor(Theme.textPrimary)
                RoundedRectangle(cornerRadius: 1.5)
                    .fill(
                        LinearGradient(
                            colors: [Theme.accent, Color(hex: 0x60A5FA)],
                            startPoint: .top, endPoint: .bottom
                        )
                    )
                    .frame(width: 4, height: 14)
            }
            Text(headline)
                .font(.subheadline)
                .foregroundColor(Theme.textPrimary)
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)
            if !metrics.isEmpty {
                HStack(alignment: .top, spacing: 8) {
                    ForEach(metrics, id: \.self) { metric in
                        VStack(alignment: .leading, spacing: 3) {
                            Text(metric.name.resolved)
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                            Text(metric.value)
                                .font(.headline.monospaced())
                                .foregroundColor(directionColor(metric.direction))
                            Text(metric.note.resolved)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(8)
                        .background(
                            LinearGradient(
                                colors: [Theme.accent.opacity(0.10), Theme.accent.opacity(0.02)],
                                startPoint: .top, endPoint: .bottom
                            ),
                            in: RoundedRectangle(cornerRadius: 8)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(Theme.accent.opacity(0.35), lineWidth: 0.5)
                        )
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.accent.opacity(0.35), lineWidth: 1))
    }
}

// MARK: - 催化剂日历卡

/// 催化剂日历卡：日期方块 + 事件/why + 市场标签（美/中/港）。
struct CatalystsCard: View {
    let catalysts: [MRCatalyst]

    private func marketLabel(_ market: String) -> String {
        switch market {
        case "us": return L("美")
        case "cn": return L("中")
        case "hk": return L("港")
        default: return market.uppercased()
        }
    }

    private func marketColor(_ market: String) -> Color {
        switch market {
        case "cn": return Color(hex: 0xF5B94F)
        case "hk": return Color(hex: 0xB79CFF)
        default: return Color(hex: 0x7CB0FF) // us 及未知市场统一美股蓝
        }
    }

    /// 从 "YYYY-MM-DD" 拆出（日数字， "YYYY-MM"），解析失败返回占位。
    private func dateParts(_ date: String) -> (day: String, ym: String) {
        let parts = date.split(separator: "-")
        guard parts.count >= 3 else { return ("?", date) }
        let day = parts[2].count >= 2 && parts[2].hasPrefix("0")
            ? String(parts[2].dropFirst()) : String(parts[2])
        return (day, "\(parts[0])-\(parts[1])")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                RoundedRectangle(cornerRadius: 1.5)
                    .fill(
                        LinearGradient(
                            colors: [Theme.accent, Color(hex: 0x60A5FA)],
                            startPoint: .top, endPoint: .bottom
                        )
                    )
                    .frame(width: 4, height: 14)
                Text(L("催化剂日历"))
                    .font(.subheadline.bold())
                    .foregroundColor(Theme.textPrimary)
            }
            ForEach(Array(catalysts.enumerated()), id: \.offset) { index, catalyst in
                let parts = dateParts(catalyst.date)
                HStack(alignment: .top, spacing: 10) {
                    VStack(spacing: 1) {
                        Text(parts.day)
                            .font(.headline.monospacedDigit())
                            .foregroundColor(Theme.textPrimary)
                        Text(parts.ym)
                            .font(.system(size: 8))
                            .foregroundStyle(.tertiary)
                    }
                    .frame(width: 42, height: 40)
                    .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(Theme.border, lineWidth: 1))
                    VStack(alignment: .leading, spacing: 3) {
                        Text(catalyst.event.resolved)
                            .font(.subheadline.bold())
                            .foregroundColor(Theme.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(catalyst.why.resolved)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 8)
                    Text(marketLabel(catalyst.market))
                        .font(.caption2.bold())
                        .foregroundColor(marketColor(catalyst.market))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(
                            marketColor(catalyst.market).opacity(0.13),
                            in: Capsule()
                        )
                }
                if index < catalysts.count - 1 {
                    Divider().overlay(Theme.border)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.border, lineWidth: 1))
    }
}
