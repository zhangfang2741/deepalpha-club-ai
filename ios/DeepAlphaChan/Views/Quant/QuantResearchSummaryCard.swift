import SwiftUI

/// 首屏摘要：大号综合等级 + 排名一句话 + 比较对象；护城河紧接在下方，维度明细在成绩单。
struct QuantResearchSummaryCard: View {
    let research: QuantResearch
    var isStatic = false

    private var gradeColor: Color { QuantGradeStyle.color(research.overall?.grade) }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .center, spacing: 16) {
                Text(research.overall?.grade ?? "—")
                    .font(.system(size: 40, weight: .bold, design: .rounded)).monospacedDigit()
                    .foregroundStyle(gradeColor)
                    .frame(width: 80, height: 80)
                    .background(gradeColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 18))
                    .overlay(RoundedRectangle(cornerRadius: 18).stroke(gradeColor.opacity(0.35)))
                    .accessibilityLabel(L("综合等级") + " " + (research.overall?.grade ?? L("暂无")))
                    .quantExplain(L("综合等级怎么来的"), enabled: !isStatic) {
                        QuantOverallGradeExplanation(research: research)
                    }
                VStack(alignment: .leading, spacing: 5) {
                    Text(L("综合等级")).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                    if let text = research.overall?.text {
                        HStack(alignment: .firstTextBaseline, spacing: 4) {
                            Text(text).font(QuantTypography.value).foregroundStyle(Theme.textPrimary)
                                .fixedSize(horizontal: false, vertical: true)
                            if !isStatic { QuantInfoMark() }
                        }
                        .quantExplain(L("综合分和排名是什么"), enabled: !isStatic) {
                            QuantOverallGradeExplanation(research: research)
                        }
                    }
                    if let peer = research.peerGroup {
                        HStack(alignment: .firstTextBaseline, spacing: 4) {
                            Text(peer.text).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                            if !isStatic { QuantInfoMark() }
                        }
                        .quantExplain(L("为什么只和同板块比"), enabled: !isStatic) {
                            QuantPeerExplanation(peer: peer)
                        }
                    }
                }
                Spacer(minLength: 0)
            }
            if !isStatic, research.scoredDimensions.count >= 3 {
                Divider().overlay(Theme.border)
                // 五维图：越靠外 = 在同板块里排名越靠前；只读展示，各维度的详情在下方成绩单里点开
                FiveDimensionChart(dimensions: research.scoredDimensions, symbol: research.symbol)
                    .allowsHitTesting(false)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(research.scoredDimensions.map { "\($0.name) \($0.grade ?? L("暂无"))" }.joined(separator: "，"))
                Text(L("越靠外，说明在同板块里排名越靠前；虚线是板块中位水平。"))
                    .font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .center).multilineTextAlignment(.center)
            }
            if research.overall?.capped == true, let note = research.overall?.note {
                Text(note).font(QuantTypography.metadata).foregroundStyle(Theme.segment)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(LinearGradient(colors: [Theme.surfaceAlt, Theme.surface], startPoint: .topLeading, endPoint: .bottomTrailing),
                    in: RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Theme.border))
    }
}
