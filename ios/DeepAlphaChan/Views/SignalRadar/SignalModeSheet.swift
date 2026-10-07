import SwiftUI

/// 买卖点口径切换面板（市场雷达右上角）：三套口径看同一批股票，区别只在「什么算买卖点」。
/// 每一项写清楚怎么判定、信号多少、代价是什么，让人明白为什么切了之后气泡会变多 / 变少。
struct SignalModeSheet: View {
    let current: String
    let onSelect: (String) -> Void
    @Environment(\.dismiss) private var dismiss

    private struct Option {
        let key: String
        let tagline: String
        let how: String
        let tradeoff: String
    }

    private var options: [Option] {
        [
            Option(key: "strict", tagline: L("最少，最贴教科书"),
                   how: L("一买一卖必须出现在两段依次下移（上移）的走势之后，并且离开段的力度比前一段弱（缠论原文的「趋势背驰」）。"),
                   tradeoff: L("只算已经走完的笔。信号最少，每一个都符合原文定义，但可能漏掉盘整里的转折。")),
            Option(key: "medium", tagline: L("多一倍信号（默认）"),
                   how: L("在严格的基础上，盘整行情里的背驰也算一类买卖点。"),
                   tradeoff: L("信号约是严格口径的 2 倍；多出来的来自盘整，不是教科书里的趋势背驰，参考时要多看一眼大的走势。仍只算已走完的笔。")),
            Option(key: "loose", tagline: L("最多，出得最早"),
                   how: L("最后一笔还没走完时也先标出来，气泡上带 ✓ 的才是已经走完的。"),
                   tradeoff: L("信号约是严格口径的 6 倍，出现得更早；但最后一笔还会变，后面的走势可能把它推翻。")),
        ]
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 10) {
                    Text(L("三种口径看的是同一批股票，区别只在「什么算买卖点」：越宽松，信号越多、出现越早，也越容易被后来的走势推翻。"))
                        .font(.footnote).foregroundColor(Theme.textSecondary)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 4)

                    ForEach(options, id: \.key) { opt in
                        Button {
                            onSelect(opt.key)
                            dismiss()
                        } label: { optionCard(opt) }
                            .buttonStyle(.plain)
                    }

                    Text(L("切换后，雷达和个股详情页都按所选口径显示。所有内容仅供学习参考，不构成投资建议。"))
                        .font(.caption2).foregroundColor(Theme.textSecondary)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 4).padding(.top, 4)
                }
                .padding(.horizontal, 16).padding(.vertical, 12)
            }
            .background(Theme.background)
            .navigationTitle(L("买卖点口径"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button(L("完成")) { dismiss() } }
            }
        }
        .presentationDetents([.large])
    }

    private func optionCard(_ opt: Option) -> some View {
        let selected = opt.key == current
        return VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Text(SignalMode.title(opt.key)).font(.headline).foregroundColor(Theme.textPrimary)
                Text(opt.tagline).font(.caption).foregroundColor(Theme.textSecondary)
                Spacer()
                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .font(.title3).foregroundColor(selected ? Theme.accent : Theme.textSecondary)
            }
            labeled(L("怎么判定"), opt.how)
            labeled(L("特点与代价"), opt.tradeoff)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(selected ? Theme.accent : .clear, lineWidth: 1.5))
        .contentShape(RoundedRectangle(cornerRadius: 12))
    }

    private func labeled(_ title: String, _ text: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.caption.weight(.semibold)).foregroundColor(Theme.textSecondary)
            Text(text).font(.footnote).foregroundColor(Theme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}
