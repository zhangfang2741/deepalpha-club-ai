import SwiftUI

/// 摘要突出综合等级及整体排名，具体维度表现由下方五维列表呈现。
struct QuantResearchSummaryCard: View {
    let research: QuantResearch

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text(L("研究摘要")).font(QuantTypography.title).foregroundStyle(Theme.textPrimary)
                Spacer()
                Text(research.symbol).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
            }
            HStack(alignment: .center, spacing: 20) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(research.overall?.grade ?? "—")
                        .font(.largeTitle.weight(.semibold)).monospacedDigit()
                        .foregroundStyle(QuantGradeStyle.color(research.overall?.grade))
                    Text(L("综合等级")).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                }
                VStack(alignment: .leading, spacing: 6) {
                    if let text = research.overall?.text {
                        Text(text).font(QuantTypography.body).foregroundStyle(Theme.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if let note = research.overall?.note {
                        Text(note).font(QuantTypography.metadata)
                            .foregroundStyle(research.overall?.capped == true ? Theme.segment : Theme.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                Spacer(minLength: 0)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(LinearGradient(colors: [Theme.surfaceAlt, Theme.surface], startPoint: .topLeading, endPoint: .bottomTrailing),
                    in: RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Theme.border))
    }
}
