import SwiftUI

/// 点击结构元素后从底部弹出的详情：是什么 / 为什么 / 概念 + 可选附加块
/// （买卖点三类对照 / 走势退化对照）+ 中枢类的「下钻到次级别」。
struct StructureSheet: View {
    let ref: ChanRef
    let analysis: ChanAnalysis

    @Environment(\.dismiss) private var dismiss

    private var topic: ChanTopic { ChanStructureInfo.topic(for: ref, in: analysis) }

    var body: some View {
        NavigationStack {
            ScrollView {
                let t = topic
                VStack(alignment: .leading, spacing: 12) {
                    HStack(spacing: 8) {
                        RoundedRectangle(cornerRadius: 3).fill(t.color).frame(width: 12, height: 12)
                        Text(t.name).font(.system(size: 17, weight: .bold)).foregroundColor(t.color)
                        Chip(text: t.tag, color: t.color)
                    }

                    HStack(alignment: .top, spacing: 7) {
                        Text(t.lead).font(.system(size: 14, weight: .bold)).foregroundColor(Theme.accent)
                        Text(t.why).font(.system(size: 14)).foregroundColor(Theme.textPrimary)
                            .lineSpacing(3).fixedSize(horizontal: false, vertical: true)
                    }

                    if !t.concept.isEmpty {
                        Text(t.concept).font(.system(size: 12)).foregroundColor(Theme.textSecondary)
                            .lineSpacing(2).fixedSize(horizontal: false, vertical: true)
                    }

                    switch t.extra {
                    case .buyTypes: BuyTypesView()
                    case .regime: RegimeView(analysis: analysis)
                    case .none: EmptyView()
                    }

                    if t.drillable {
                        NavigationLink {
                            RecursionInfoView(pivotName: t.name)
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: "magnifyingglass")
                                Text(L("下钻到次级别看内部"))
                            }
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(Theme.accent)
                            .frame(maxWidth: .infinity)
                            .padding(11)
                            .background(Theme.accent.opacity(0.12))
                            .overlay(RoundedRectangle(cornerRadius: 11).stroke(Theme.accent.opacity(0.5), lineWidth: 1))
                            .clipShape(RoundedRectangle(cornerRadius: 11))
                        }
                        .padding(.top, 2)
                    }
                }
                .padding(18)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .background(Theme.background)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(L("完成")) { dismiss() }
                }
            }
        }
    }
}

/// 买卖点三类各挂在哪：点选看区别（一买=背驰、二买=回抽不破、三买=离开中枢）。
private struct BuyTypesView: View {
    @State private var sel = "b3"

    private struct BuyRow: Identifiable { let id: String; let name: String; let desc: String }

    private var rows: [BuyRow] {
        [
            BuyRow(id: "b1", name: L("一类买卖点"), desc: L("涨/跌到尽头、劲用光了，往往是最早的转折点。空间最大，但也最靠前、最不确定。")),
            BuyRow(id: "b2", name: L("二类买卖点"), desc: L("转折后回踩没再创新低（或反弹没再创新高），算确认了一下，稳一点。")),
            BuyRow(id: "b3", name: L("三类买卖点"), desc: L("突破争夺区、回踩不再回到区里，说明新方向立住了。最稳，但空间也小。"))
        ]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(L("三类各挂在结构的不同位置（点看区别）"))
                .font(.system(size: 11)).foregroundColor(Theme.textSecondary)
            ForEach(rows) { r in
                Button { sel = r.id } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(r.name).font(.system(size: 12.5, weight: .bold)).foregroundColor(Theme.up)
                        Text(r.desc).font(.system(size: 11.5)).foregroundColor(Theme.textSecondary)
                            .lineSpacing(2).fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(9)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(sel == r.id ? Theme.up.opacity(0.10) : Color.clear)
                    .overlay(RoundedRectangle(cornerRadius: 8)
                        .stroke(sel == r.id ? Theme.up.opacity(0.5) : Theme.border, lineWidth: 1))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.top, 4)
    }
}

/// 走势退化对照：中枢有几个 → 盘整还是趋势（当前态高亮）。
private struct RegimeView: View {
    let analysis: ChanAnalysis

    var body: some View {
        let cur = ChanStructureInfo.walkKey(analysis)
        VStack(alignment: .leading, spacing: 6) {
            Text(L("中枢有几个 → 盘整还是趋势"))
                .font(.system(size: 11)).foregroundColor(Theme.textSecondary)
            row(L("0 中枢"), L("单边推进"), highlighted: cur == "none")
            row(L("1 中枢"), L("盘整"), highlighted: cur == "consolidation")
            row(L("2+ 中枢"), L("趋势（依次移动）"), highlighted: cur == "up_trend" || cur == "down_trend")
        }
        .padding(.top, 4)
    }

    private func row(_ left: String, _ right: String, highlighted: Bool) -> some View {
        HStack {
            Text(left).font(.system(size: 11, weight: highlighted ? .bold : .regular))
                .foregroundColor(highlighted ? Theme.down : Theme.textSecondary)
                .frame(width: 60, alignment: .leading)
            Text(right).font(.system(size: 11)).foregroundColor(Theme.textSecondary)
            Spacer(minLength: 0)
            if highlighted {
                Text(L("← 当前")).font(.system(size: 10, weight: .bold)).foregroundColor(Theme.down)
            }
        }
        .padding(.horizontal, 10).padding(.vertical, 7)
        .background(highlighted ? Theme.down.opacity(0.08) : Theme.surfaceAlt)
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(highlighted ? Theme.down.opacity(0.4) : Color.clear, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

/// 下钻页（Phase 1 讲清「递归=多周期」的概念；接入多周期数据后这里显示真实次级别）。
private struct RecursionInfoView: View {
    let pivotName: String

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text(L("%@ 的内部", pivotName))
                    .font(.system(size: 17, weight: .bold)).foregroundColor(Theme.textPrimary)
                Text(L("这块争夺区，放大了看，就是更小周期（比如 30 分钟）的一整段行情。大周期套着小周期、小周期里又有更小的……这就是「多周期」：这块区域，本来就是下面更小的波动来回重叠出来的。"))
                    .font(.system(size: 14)).foregroundColor(Theme.textSecondary)
                    .lineSpacing(4).fixedSize(horizontal: false, vertical: true)

                VStack(alignment: .leading, spacing: 8) {
                    Text(L("级别递归")).font(.system(size: 12, weight: .semibold)).foregroundColor(Theme.pivotFill)
                    HStack(spacing: 6) {
                        Text(L("日线中枢")).font(.system(size: 12)).foregroundColor(Theme.textPrimary)
                        Image(systemName: "arrow.right").font(.system(size: 9)).foregroundColor(Theme.textSecondary)
                        Text(L("30分走势")).font(.system(size: 12)).foregroundColor(Theme.textPrimary)
                        Image(systemName: "arrow.right").font(.system(size: 9)).foregroundColor(Theme.textSecondary)
                        Text(L("30分中枢")).font(.system(size: 12)).foregroundColor(Theme.textPrimary)
                        Image(systemName: "ellipsis").font(.system(size: 9)).foregroundColor(Theme.textSecondary)
                    }
                    .padding(11)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.pivotFill.opacity(0.08))
                    .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.pivotFill.opacity(0.35), lineWidth: 1))
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                }

                Text(L("接入多周期数据后，这里会展开该中枢内部的真实次级别结构与买卖点。"))
                    .font(.system(size: 11)).foregroundColor(Theme.textSecondary)
                    .lineSpacing(2).fixedSize(horizontal: false, vertical: true)
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(Theme.background)
        .navigationTitle(L("下钻 · 次级别"))
        .navigationBarTitleDisplayMode(.inline)
    }
}
