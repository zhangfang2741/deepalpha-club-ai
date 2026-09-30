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
