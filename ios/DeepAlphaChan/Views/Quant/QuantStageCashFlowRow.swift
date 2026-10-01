import SwiftUI

struct QuantStageCashFlowRow: View {
    let title: String
    let value: Double

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(title).font(QuantTypography.body).foregroundStyle(Theme.textPrimary)
                Spacer()
                Text(QuantLifecycleStage.signLabel(value)).font(QuantTypography.metadata)
                    .foregroundStyle(Theme.textSecondary)
            }
            Text(value.formatted(.number.precision(.fractionLength(0...2))))
                .font(QuantTypography.value.monospacedDigit()).foregroundStyle(Theme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }
}

/// 营收增速一行；缺失时显示原因（如上市不足 3 年）。
struct QuantStageGrowthRow: View {
    let title: String
    let pct: Double?
    let missingNote: String

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title).font(QuantTypography.body).foregroundStyle(Theme.textPrimary)
            Spacer()
            if let pct {
                Text(String(format: "%+.1f%%", pct))
                    .font(QuantTypography.value.monospacedDigit()).foregroundStyle(Theme.textPrimary)
            } else {
                Text(missingNote).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
            }
        }
        .accessibilityElement(children: .combine)
    }
}
