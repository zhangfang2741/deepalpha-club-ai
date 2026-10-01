import SwiftUI

/// 成绩单的一行：左侧彩色等级块一眼可扫，右侧维度名 + 最能说明问题的一条事实。
struct QuantDimensionRow: View {
    let dimension: QuantDimension
    var isStatic = false

    private var subtitle: String {
        guard dimension.isOK else { return dimension.statusNote ?? L("暂无") }
        return dimension.keyFact?.text ?? QuantDimensionGuide.question(dimension.key) ?? dimension.description
    }

    var body: some View {
        HStack(spacing: 12) {
            QuantGradeBlock(grade: dimension.isOK ? dimension.grade : nil)
            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(dimension.name).font(QuantTypography.title).foregroundStyle(Theme.textPrimary)
                    if let q = QuantDimensionGuide.question(dimension.key) {
                        Text(q).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                            .lineLimit(1)
                    }
                }
                Text(subtitle)
                    .font(QuantTypography.body)
                    .foregroundStyle(dimension.isOK ? Theme.textPrimary.opacity(0.85) : Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 4)
            if !isStatic {
                Image(systemName: "chevron.right").font(QuantTypography.metadata)
                    .foregroundStyle(Theme.textSecondary).accessibilityHidden(true)
            }
        }
        .padding(.vertical, 12)
        .frame(minHeight: 44)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityHint(isStatic ? "" : L("查看各项指标与解读"))
    }
}
