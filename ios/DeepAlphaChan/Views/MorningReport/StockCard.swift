import SwiftUI

/// 晨报个股卡：整卡可点跳转缠论分析，内含 Bull/Base/Bear 三列情景。
struct StockCard: View {
    let stock: MRStockPick
    let onOpen: (String) -> Void

    private func directionColor(_ direction: String) -> Color {
        switch direction {
        case "up": return Theme.up
        case "down": return Theme.down
        default: return Theme.textSecondary
        }
    }

    /// 三列情景之一的浅色背景块：9pt heavy 标题 + 10.5pt 正文。
    private func scenario(title: String, text: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.system(size: 9, weight: .heavy))
                .foregroundColor(color)
                .tracking(0.8)
            Text(text)
                .font(.system(size: 10.5))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(8)
        .background(color.opacity(0.10), in: RoundedRectangle(cornerRadius: 8))
    }

    var body: some View {
        Button {
            onOpen(stock.symbol)
        } label: {
            VStack(alignment: .leading, spacing: 9) {
                HStack(spacing: 8) {
                    Text(stock.symbol)
                        .font(.subheadline.bold())
                        .foregroundColor(Theme.textPrimary)
                    Text(stock.name.resolved)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                    Spacer(minLength: 8)
                    Text(stock.changePct)
                        .font(.subheadline.bold().monospacedDigit())
                        .foregroundColor(directionColor(stock.direction))
                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.tertiary)
                }
                HStack(alignment: .top, spacing: 8) {
                    scenario(title: "BULL", text: stock.bull.resolved, color: Theme.up)
                    scenario(title: "BASE", text: stock.base.resolved, color: Theme.segment)
                    scenario(title: "BEAR", text: stock.bear.resolved, color: Theme.down)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .accessibilityHint(L("查看缠论分析"))
    }
}
