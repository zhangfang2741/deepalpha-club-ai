import SwiftUI

/// 首屏摘要：大号综合等级 + 排名一句话 + 强项 / 短板，三秒内读完结论；维度明细在下方成绩单。
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
            highlights
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

    @ViewBuilder
    private var highlights: some View {
        let strengths = research.strengths
        let weaknesses = research.weaknesses
        VStack(alignment: .leading, spacing: 8) {
            if strengths.isEmpty && weaknesses.isEmpty {
                Text(L("各维度都在板块中游，没有特别突出的强项或短板。"))
                    .font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                if !strengths.isEmpty {
                    highlightLine(title: L("强项"), color: Theme.up, dimensions: strengths)
                }
                if !weaknesses.isEmpty {
                    highlightLine(title: L("短板"), color: Theme.down, dimensions: weaknesses)
                }
            }
        }
        .padding(.top, 2)
    }

    private func highlightLine(title: String, color: Color, dimensions: [QuantDimension]) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(title)
                .font(QuantTypography.metadata.weight(.semibold)).foregroundStyle(color)
                .padding(.horizontal, 7).padding(.vertical, 3)
                .background(color.opacity(0.14), in: Capsule())
                .quantExplain(L("强项和短板怎么定"), enabled: !isStatic) { QuantHighlightExplanation() }
            Text(dimensions.map { "\($0.name) \($0.grade ?? "")" }
                    .joined(separator: Localized.language() == .english ? " · " : "、"))
                .font(QuantTypography.emphasis).foregroundStyle(Theme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }
}
