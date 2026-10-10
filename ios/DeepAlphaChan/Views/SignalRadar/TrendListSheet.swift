import SwiftUI

/// 基本面雷达 / 评级雷达名单：当前类别的全部公司，按圈（近 1 周 → 1 月 → 3 月）分组、组内按变化幅度。
/// 每行写综合等级与具体变化；点一行打开个股的「基本面研究」分段。只陈列事实、不是推荐。
struct TrendListSheet: View {
    let kind: QuantTrendKind
    let items: [QuantTrendItem]
    let asOf: String?
    /// 点某一行：先收起面板，收起后再打开个股。
    let onOpen: (String, String) -> Void

    private var groups: [(label: String, items: [QuantTrendItem])] {
        let labels = SignalRadarView.trendRingLabels
        return [(7, labels[0]), (30, labels[1]), (90, labels[2])].compactMap { ring, label in
            let g = items.filter { $0.ringDays == ring }
            return g.isEmpty ? nil : (label, g)
        }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    if items.isEmpty {
                        Text(L("暂时没有达到门槛的公司"))
                            .font(.footnote).foregroundColor(Theme.textSecondary)
                            .frame(maxWidth: .infinity).padding(.top, 40)
                    } else {
                        ForEach(groups, id: \.label) { group in
                            Text(group.label + " · \(group.items.count)")
                                .font(.footnote.weight(.semibold)).foregroundColor(Theme.accent)
                                .padding(.top, 4)
                            ForEach(group.items) { item in
                                Button { onOpen(item.symbol, item.name ?? "") } label: { row(item) }
                                    .buttonStyle(.plain)
                            }
                        }
                        Text(kind.flavor == .analyst
                             ? L("只陈列券商评级的变动事实，不代表股价会涨跌，不构成投资建议。")
                             : L("只陈列预期与财报的变化事实，不代表股价会涨跌，不构成投资建议。"))
                            .font(.caption2).foregroundColor(Theme.textSecondary)
                            .padding(.top, 8)
                    }
                }
                .padding(16)
            }
            .background(Theme.background)
            .navigationTitle(kind.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if let asOf {
                    ToolbarItem(placement: .topBarTrailing) {
                        Text(asOf).font(.caption).foregroundColor(Theme.textSecondary)
                    }
                }
            }
        }
    }

    private func row(_ item: QuantTrendItem) -> some View {
        HStack(alignment: .top, spacing: 10) {
            QuantGradeBlock(grade: item.grade, side: 32)
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(item.symbol).font(.subheadline.weight(.semibold)).foregroundColor(Theme.textPrimary)
                    if let name = item.name, !name.isEmpty {
                        Text(name).font(.caption).foregroundColor(Theme.textSecondary).lineLimit(1)
                    }
                }
                Text(TrendDerivations.factLine(item))
                    .font(.caption.monospacedDigit()).foregroundColor(Theme.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                Text(TrendDerivations.contextLine(item))
                    .font(.caption2).foregroundColor(Theme.textSecondary)
            }
            Spacer(minLength: 4)
            Image(systemName: "chevron.right").font(.caption2).foregroundColor(Theme.textSecondary)
        }
        .padding(10)
        .frame(minHeight: 44)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 12))
        .contentShape(Rectangle())
    }
}
