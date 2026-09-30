import SwiftUI

/// 第二层把五个维度收成可快速扫读的行，点击后才进入指标依据。
struct QuantDimensionRow: View {
    let dimension: QuantDimension
    var isStatic = false
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var question: String {
        switch dimension.key {
        case "profitability": return L("赚钱能力如何")
        case "growth": return L("生意是否在成长")
        case "valuation": return L("价格相对基本面如何")
        case "momentum": return L("市场近期如何定价")
        case "revisions": return L("盈利预期有何变化")
        default: return dimension.description
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(dimension.name).font(QuantTypography.title).foregroundStyle(Theme.textPrimary)
                    Text(dimension.isOK ? question : (dimension.statusNote ?? L("暂无")))
                        .font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 8)
                if !dynamicTypeSize.isAccessibilitySize, let score = dimension.score, dimension.isOK {
                    QuantPercentileBar(percentile: score, color: QuantGradeStyle.color(dimension.grade))
                        .frame(width: 48).accessibilityHidden(true)
                }
                Text(dimension.grade ?? "—").font(QuantTypography.title)
                    .foregroundStyle(QuantGradeStyle.color(dimension.grade))
                    .frame(minWidth: 32, alignment: .trailing)
                if !isStatic {
                    Image(systemName: "chevron.right").font(QuantTypography.metadata)
                        .foregroundStyle(Theme.textSecondary).accessibilityHidden(true)
                }
            }
        }
        .padding(.vertical, 14)
        .frame(minHeight: 44)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityHint(isStatic ? "" : L("查看计算与价值解读"))
    }
}
