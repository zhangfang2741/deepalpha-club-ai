import SwiftUI

/// 当前节点展示该公司的实际依据；其余节点仅展示规则，避免将概念说明误认为本股结论。
struct QuantStageDetailContent: View {
    let selected: QuantLifecycleStage
    let research: QuantResearch

    private var isCurrent: Bool { research.stage?.key == selected.rawValue }

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            VStack(alignment: .leading, spacing: 10) {
                if isCurrent {
                    Label(research.symbol + " · " + L("当前阶段"), systemImage: "record.circle")
                        .font(QuantTypography.metadata.weight(.semibold)).foregroundStyle(Theme.accent)
                } else {
                    Text(L("阶段释义")).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                }
                Text(selected.title).font(QuantTypography.summary).foregroundStyle(Theme.textPrimary)
                Text(selected.explanation).font(QuantTypography.body).foregroundStyle(Theme.textPrimary)
                    .lineSpacing(4).fixedSize(horizontal: false, vertical: true)
            }
            VStack(alignment: .leading, spacing: 10) {
                Text(L("判定规则")).font(QuantTypography.title).foregroundStyle(Theme.textPrimary)
                Text(selected.rule).font(QuantTypography.body.monospacedDigit()).foregroundStyle(Theme.accent)
                    .fixedSize(horizontal: false, vertical: true)
                Text(L("营收同比 = 最近 12 个月营收 ÷ 上一个 12 个月 − 1；不足 3 年历史只看同比。经营现金流取最近 12 个月，零值归为 ≤ 0 一侧。"))
                    .font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
            }
            .padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: 16))
            if isCurrent, let stage = research.stage {
                VStack(alignment: .leading, spacing: 12) {
                    Text(L("为什么判为%@？", selected.title))
                         .font(QuantTypography.title).foregroundStyle(Theme.textPrimary)
                    Text(L("实际营收增速与经营现金流符合上面的规则。"))
                        .font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
                    QuantStageGrowthRow(title: L("营收同比"), pct: stage.revenueGrowthPct,
                                        missingNote: L("营收基数为零"))
                    Divider().overlay(Theme.border)
                    QuantStageGrowthRow(title: L("营收 3 年复合增速"), pct: stage.revenueCagr3yPct,
                                        missingNote: L("不足 3 年历史"))
                    Divider().overlay(Theme.border)
                    QuantStageCashFlowRow(title: L("经营现金流"), value: stage.cashFlows.operating)
                    if let period = research.asOf?.fiscalPeriod {
                        Text(L("财报参考期：%@", period)).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                    }
                    Text(stage.note).font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(16)
                .background(Theme.surface, in: RoundedRectangle(cornerRadius: 16))
            }
            QuantStageRankingSection(selected: selected, research: research)
            Text(L("这是按营收增速与经营现金流做的阶段定位，不是完成进度。企业可能跨阶段变化。阶段会影响各维度在综合分里的占比（点综合等级可看），在门槛附近是平滑过渡的；但不改变任何单项指标在同板块里的百分位。"))
                .font(QuantTypography.body).foregroundStyle(Theme.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(20)
    }
}
