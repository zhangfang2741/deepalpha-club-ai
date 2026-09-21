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
            Text(L("你在标准阶段的哪一步"))
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Theme.textSecondary)
            VStack(alignment: .leading, spacing: 14) {
                ForEach(Array(pivotPhase.stageGuide.steps.enumerated()), id: \.offset) { idx, step in
                    let isCurrent = idx == pivotPhase.stageGuide.currentIndex
                    let isPast = idx < pivotPhase.stageGuide.currentIndex
                    HStack(alignment: .top, spacing: 10) {
                        Circle()
                            .fill(isCurrent ? Theme.segment : (isPast ? Theme.accent : Theme.textSecondary.opacity(0.3)))
                            .frame(width: 10, height: 10)
                            .padding(.top, 4)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(isCurrent ? currentStepTitle(step.title) : step.title)
                                .font(.system(size: 14, weight: isCurrent ? .semibold : .regular))
                                .foregroundColor(isCurrent ? Theme.segment : Theme.textPrimary)
                            Text(step.detail)
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
            Text(L("这一步为什么关键？"))
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Theme.accent)
            Text(pivotPhase.stageGuide.whyItMatters)
                .font(.system(size: 14))
                .foregroundColor(Theme.textPrimary)
                .lineSpacing(4)
        }
    }

    private var satisfiedSoFarSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(L("现在满足到哪了？"))
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Theme.textSecondary)
            ForEach(pivotPhase.checklist) { item in
                HStack(alignment: .top, spacing: 6) {
                    Image(systemName: item.state == .done ? "checkmark.circle.fill" : "exclamationmark.circle")
                        .foregroundColor(item.state == .done ? .green : Theme.segment)
                        .font(.system(size: 14))
                    VStack(alignment: .leading, spacing: 2) {
                        Text(item.state == .done ? L("已满足：%@", item.label) : L("尚未满足：%@", item.label))
                            .font(.system(size: 13))
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
