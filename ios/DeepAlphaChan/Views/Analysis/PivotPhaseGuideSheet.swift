import SwiftUI

/// 「走到哪一步」阶段徽标点击后弹出的讲解层：标准五步阶梯 + 为什么关键 +
/// 现在满足到哪了。
///
/// 「现在满足到哪了」直接复用主页面的 `checklist`（同一份数据源，只是图标从
/// ✓/○ 换成 ✅/⚠️），不重复建模——两处一旦各自维护，迟早会在某次改动后对不上。
struct PivotPhaseGuideSheet: View {
    let pivotPhase: PivotPhase
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                stageStepper
                whyItMattersSection
                satisfiedSoFarSection
                Text(L("点图上的笔/线段/中枢/买卖点，可逐个看它在当前图形怎么形成"))
                    .font(.caption2)
                    .foregroundColor(Theme.textSecondary)
            }
            .padding(16)
        }
        .background(Theme.background)
        .navigationTitle(L("%@·讲解", pivotPhase.phaseLabel))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    dismiss()
                } label: {
                    Image(systemName: "xmark")
                }
                .accessibilityLabel(L("关闭"))
            }
        }
    }

    /// 拼「标题（你在这）」——用字符串拼接而不是嵌套插值，避免圆括号和全角括号
    /// 混在一起数错层数。
    private func currentStepTitle(_ title: String) -> String {
        title + "（" + L("你在这") + "）"
    }

    private var stageStepper: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(L("阶段参考 · 非必经顺序"))
                .font(.footnote.weight(.semibold))
                .foregroundColor(Theme.textSecondary)
            VStack(alignment: .leading, spacing: 14) {
                ForEach(pivotPhase.stageGuide.steps) { step in
                    let isCurrent = step.key == pivotPhase.phase
                    HStack(alignment: .top, spacing: 10) {
                        Circle()
                            .fill(isCurrent ? Theme.pivotPhaseColor(pivotPhase.phase) : Theme.textSecondary.opacity(0.3))
                            .frame(width: 10, height: 10)
                            .padding(.top, 4)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(isCurrent ? currentStepTitle(step.title) : step.title)
                                .font(.subheadline.weight(isCurrent ? .semibold : .regular))
                                .foregroundColor(isCurrent ? Theme.pivotPhaseColor(pivotPhase.phase) : Theme.textPrimary)
                            Text(AnalysisInterpretation.stageExplanation(step.key))
                                .font(.caption)
                                .foregroundColor(Theme.textSecondary)
                        }
                    }
                }
            }
        }
    }

    private var whyItMattersSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(L("本次判定依据"))
                .font(.footnote.weight(.semibold))
                .foregroundColor(Theme.accent)
            Text(pivotPhase.reason)
                .font(.subheadline)
                .foregroundColor(Theme.textPrimary)
                .lineSpacing(4)
        }
    }

    private var satisfiedSoFarSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(L("现在满足到哪了？"))
                .font(.footnote.weight(.semibold))
                .foregroundColor(Theme.textSecondary)
            ForEach(pivotPhase.checklist) { item in
                HStack(alignment: .top, spacing: 6) {
                    Image(systemName: item.state == .done ? "checkmark.circle.fill" : "exclamationmark.circle")
                        .foregroundColor(item.state == .done ? Theme.accent : Theme.textSecondary)
                        .font(.subheadline)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(item.state == .done ? L("已满足：%@", item.label) : L("尚未满足：%@", item.label))
                            .font(.footnote)
                            .foregroundColor(Theme.textPrimary)
                        if !item.detail.isEmpty {
                            Text(item.detail).font(.caption2).foregroundColor(Theme.textSecondary)
                        }
                    }
                }
            }
        }
    }
}
