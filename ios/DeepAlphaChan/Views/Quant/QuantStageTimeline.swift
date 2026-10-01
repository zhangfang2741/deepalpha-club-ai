import SwiftUI

/// 展示完整阶段路径，只强调接口返回的当前节点，不暗示之前的阶段均已完成。
struct QuantStageTimeline: View {
    let research: QuantResearch
    var isStatic = false
    @State private var selectedStage: QuantLifecycleStage?
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var current: QuantLifecycleStage? {
        research.stage.flatMap { QuantLifecycleStage(rawValue: $0.key) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                Text(L("企业阶段")).font(QuantTypography.title).foregroundStyle(Theme.textPrimary)
                Spacer(minLength: 8)
                Text(current?.title ?? L("暂无阶段判定"))
                    .font(QuantTypography.title).foregroundStyle(current == nil ? Theme.textSecondary : Theme.accent)
            }
            if dynamicTypeSize.isAccessibilitySize {
                VStack(spacing: 6) {
                    ForEach(QuantLifecycleStage.allCases) { stage in
                        stageButton(stage, vertical: true)
                    }
                }
            } else {
                HStack(alignment: .top, spacing: 0) {
                    ForEach(QuantLifecycleStage.allCases) { stage in
                        stageButton(stage, vertical: false)
                    }
                }
            }
            if current == nil {
                Text(research.peerGroup?.sectorKey == "financials"
                     ? L("金融公司的营收与现金流口径不同，本模型不判定阶段。")
                     : L("暂时没有可用的阶段结果，仍可点开了解各阶段。"))
                    .font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
            } else {
                Text(L("点阶段看释义，点当前阶段看判定依据。"))
                    .font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
            }
        }
        .padding(14)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
        .sheet(item: $selectedStage) { stage in
            QuantStageSheet(selected: stage, research: research)
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
        }
    }

    @ViewBuilder
    private func stageButton(_ stage: QuantLifecycleStage, vertical: Bool) -> some View {
        if isStatic {
            QuantStageNode(stage: stage, isCurrent: stage == current, vertical: vertical)
        } else {
            Button { selectedStage = stage } label: {
                QuantStageNode(stage: stage, isCurrent: stage == current, vertical: vertical)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(stage.title + (stage == current ? " · " + L("当前阶段") : ""))
            .accessibilityHint(stage == current ? L("查看阶段释义与判定依据") : L("查看阶段释义"))
        }
    }
}
