import SwiftUI

/// 「好股票」名单：当前综合等级达标的股票，按「近期有买点 / 近期只有卖点 / 暂无买卖点」分组（买点优先），
/// 每行写等级、分析师角标与最近一个买卖点。只陈列事实：不排序推荐，组内按综合等级从高到低。
struct GoodStocksSheet: View {
    @ObservedObject var vm: GoodStocksViewModel
    /// 最低综合等级（如 "B+"，后端门槛）。
    let threshold: String?
    let universeName: String
    /// 雷达当前所有展示日（最新在前），用来找每只股票最近的买卖点。
    let days: [RadarDay]
    /// 免费用户看示例日时的日期：名单里的买卖点只按这一天判断，顶部写明。会员为 nil。
    var demoDate: String? = nil
    let sectorName: (String) -> String
    /// 雷达顶部「行业」当前的筛选（nil = 全部行业）：名单跟着只列该行业的股票（后端按 sector 过滤，这里只用来写标题和空态）。
    var sectorKey: String? = nil
    /// 点某一行：先收起面板，收起后再打开个股。
    let onOpen: (String, String) -> Void

    /// 每只股票最近的一个买卖点（days 最新在前，每天信号也是新到旧）；买点优先：近期有买点时展示最近的买点，
    /// 没有买点才展示最近的卖点。
    private func latestSignal(for symbol: String) -> RadarSignal? {
        var firstSell: RadarSignal?
        for day in days {
            for s in day.signals where s.symbol == symbol {
                if s.side == "buy" { return s }
                if firstSell == nil { firstSell = s }
            }
        }
        return firstSell
    }

    var body: some View {
        let items = vm.items(atLeast: threshold)
        let withBuy = items.filter { latestSignal(for: $0.symbol)?.side == "buy" }
        let onlySell = items.filter { latestSignal(for: $0.symbol).map { $0.side != "buy" } ?? false }
        let without = items.filter { latestSignal(for: $0.symbol) == nil }
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    if vm.failed {
                        Text(L("评级数据暂时读取失败，稍后再试"))
                            .font(.footnote).foregroundColor(Theme.textSecondary)
                            .frame(maxWidth: .infinity).padding(.top, 40)
                    } else if items.isEmpty {
                        Text(vm.isLoading ? L("正在加载基本面名单…")
                             : (sectorKey == nil ? L("这个范围暂时没有达标的股票") : L("这个行业暂时没有达标的股票")))
                            .font(.footnote).foregroundColor(Theme.textSecondary)
                            .frame(maxWidth: .infinity).padding(.top, 40)
                    } else {
                        if let demoDate {
                            Text(L("示例日 %@ · 买卖点按这一天", demoDate))
                                .font(.caption).foregroundColor(Theme.textSecondary)
                        }
                        if let sectorKey {
                            Text(L("行业：%@ · %lld 只", sectorName(sectorKey), items.count))
                                .font(.footnote.weight(.semibold)).foregroundColor(Theme.accent)
                        }
                        columnHeader
                        // 买点优先：先列近期有买点的，再列只有卖点的，最后是暂无买卖点的
                        section(L("近期有买点 · %lld 只", withBuy.count), withBuy)
                        section(L("近期只有卖点 · %lld 只", onlySell.count), onlySell)
                        section(L("暂无买卖点 · %lld 只", without.count), without)
                    }
                    Text(L("基本面靠前 = 当前综合等级不低于 %@ 的股票；分析师评级变动角标为近 90 天净上调 / 净下调（仅美股）。仅为事实陈列，不构成投资建议。", threshold ?? ""))
                        .font(.caption2).foregroundColor(Theme.textSecondary)
                        .padding(.top, 8)
                }
                .padding(.horizontal, 12).padding(.vertical, 8)
            }
            .background(Theme.background)
            .navigationTitle(universeName)
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    /// 列标题：与行内各列同宽、同对齐（券商 / 等级 / 最近买卖点列固定宽度，行与表头才对得齐）。
    private var columnHeader: some View {
        HStack(spacing: 10) {
            Text(L("股票")).frame(maxWidth: .infinity, alignment: .leading)
            Text(L("分析师\n评级变动")).multilineTextAlignment(.trailing).frame(width: Self.markWidth, alignment: .trailing)
            Text(L("等级")).frame(width: Self.gradeWidth, alignment: .trailing)
            Text(L("最近买卖点")).frame(width: Self.signalWidth, alignment: .trailing)
        }
        .font(.system(size: 11)).foregroundColor(Theme.textSecondary)
        .lineLimit(2).minimumScaleFactor(0.8)
        .padding(.horizontal, 12).padding(.top, 2)
    }

    private static let markWidth: CGFloat = 46
    private static let gradeWidth: CGFloat = 32
    private static let signalWidth: CGFloat = 88

    @ViewBuilder
    private func section(_ title: String, _ list: [FundamentalItem]) -> some View {
        if !list.isEmpty {
            Text(title).font(.footnote.weight(.semibold)).foregroundColor(Theme.textSecondary).padding(.top, 6)
            ForEach(list) { e in
                Button { onOpen(e.symbol, e.name) } label: { row(e) }.buttonStyle(.plain)
            }
        }
    }

    private func row(_ e: FundamentalItem) -> some View {
        let signal = latestSignal(for: e.symbol)
        return HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                // 代码在上、名称在下（与自选列表一致）
                Text(e.symbol).font(.system(size: 15, weight: .semibold)).foregroundColor(Theme.textPrimary)
                HStack(spacing: 6) {
                    if e.name != e.symbol { Text(e.name).lineLimit(1) }
                    if let sector = e.sector { Text((e.name != e.symbol ? "· " : "") + sectorName(sector)).lineLimit(1) }
                }
                .font(.system(size: 11)).foregroundColor(Theme.textSecondary)
            }
            Spacer()
            Group {
                if let mark = e.analystMark {
                    Text(mark)
                        .font(.system(size: 11, weight: .bold).monospacedDigit())
                        .foregroundColor(mark.hasPrefix("▲") ? Theme.up : Theme.down)
                }
            }
            .frame(width: Self.markWidth, alignment: .trailing)
            Text(e.grade).font(.system(size: 17, weight: .bold)).foregroundColor(Theme.textPrimary).frame(width: Self.gradeWidth, alignment: .trailing)
            // 最近一个买卖点放在最后（行尾），固定宽度让各行的日期、标签上下对齐
            VStack(alignment: .trailing, spacing: 2) {
                if let signal {
                    RadarPanelStyle.tag(signal)
                    Text(signal.date).font(.system(size: 10)).foregroundColor(Theme.textSecondary)
                }
            }
            .frame(width: Self.signalWidth, alignment: .trailing)
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 12))
    }
}
