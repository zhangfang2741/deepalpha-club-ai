import SwiftUI

/// 方法说明（「等级是怎么算的？」）：服务端下发的说明段落、等级分档、各维度的指标清单。
struct QuantMethodologyView: View {
    @ObservedObject var vm: QuantResearchViewModel

    var body: some View {
        ScrollView {
            if let m = vm.methodology {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(m.sections) { s in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(s.title).font(.system(size: 15, weight: .semibold)).foregroundStyle(Theme.textPrimary)
                            Text(s.body).font(.footnote).foregroundStyle(Theme.textPrimary.opacity(0.85))
                                .lineSpacing(3).fixedSize(horizontal: false, vertical: true)
                        }
                        .padding(14)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
                    }
                    QuantSectionHeader(text: L("等级分档（板块百分位）"))
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 6), count: 4), spacing: 6) {
                        ForEach(m.gradeBands) { b in
                            VStack(spacing: 2) {
                                Text(b.grade).font(.system(size: 15, weight: .heavy))
                                    .foregroundStyle(QuantGradeStyle.color(b.grade))
                                Text("≥ \(Int(b.minPercentile))").font(.caption2.monospacedDigit())
                                    .foregroundStyle(Theme.textSecondary)
                            }
                            .frame(maxWidth: .infinity).padding(.vertical, 6)
                            .background(Theme.surface, in: RoundedRectangle(cornerRadius: 8))
                        }
                    }
                    ForEach(m.dimensions) { d in
                        QuantSectionHeader(text: d.name, trailing: L("%lld 项指标", d.metrics.count))
                        VStack(alignment: .leading, spacing: 0) {
                            Text(d.description).font(.caption).foregroundStyle(Theme.textSecondary)
                                .padding(.vertical, 8)
                            ForEach(d.metrics) { metric in
                                Divider().background(Theme.border)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(metric.name).font(.footnote.weight(.medium)).foregroundStyle(Theme.textPrimary)
                                    Text(metric.description).font(.caption2).foregroundStyle(Theme.textSecondary)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                                .padding(.vertical, 7)
                            }
                        }
                        .padding(.horizontal, 14)
                        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
                    }
                    Text(m.disclaimer).font(.caption2).foregroundStyle(Theme.textSecondary)
                        .multilineTextAlignment(.center).frame(maxWidth: .infinity).padding(.top, 6)
                }
                .padding(.horizontal, Theme.contentHInset)
                .padding(.vertical, Theme.contentVInset)
            } else {
                ProgressView().tint(Theme.accent).frame(maxWidth: .infinity, minHeight: 300)
            }
        }
        .background(Theme.background)
        .navigationTitle(L("等级是怎么算的"))
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.loadMethodology() }
    }
}
