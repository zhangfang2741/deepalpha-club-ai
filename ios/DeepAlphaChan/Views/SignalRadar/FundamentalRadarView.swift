import SwiftUI

/// 雷达「基本面研究」tab 的外框：概览行 + 雷达画布（由 SignalRadarView 传入，与缠论雷达同一块画布：多环、浮动动画、摆位）
/// + 图例 + 榜单入口行。画布里每个气泡 = 股票池里综合等级最高的一只股票：代码 + 名称 + 等级字母；
/// 环 = 等级段（A / B / C 及以下，越靠中心越高）；右上角白色小角标 = 近 30 天券商评级净上调 ▲n / 净下调 ▼n（仅美股）。
/// 不按日期，没有日期轨——榜单入口行占日期轨的位置，保证与缠论 tab 的画布同高。
struct FundamentalRadarView<Field: View>: View {
    @ObservedObject var vm: FundamentalRadarViewModel
    let universeName: String
    let sectorName: (String) -> String
    /// 「查看全部」半屏是否打开（按钮在画布和榜单入口行里，状态放在外面）。
    @Binding var showAll: Bool
    /// 点某只股票：去看这只股票（与雷达气泡同一入口）。
    let onOpen: (String, String) -> Void
    @ViewBuilder let field: () -> Field

    /// 在「查看全部」里点了某一行：等面板收起后再打开个股。
    @State private var pending: FundamentalItem?
    @State private var showInfo = false

    var body: some View {
        // 行间距、行高、底部免责声明都与缠论雷达（SignalRadarView.radarContent）保持一致，两个 tab 的画布高度才一样
        VStack(spacing: 12) {
            if vm.hasError {
                message(L("评级数据暂时读取失败，稍后再试"))
            } else if vm.items.isEmpty {
                message(L("这个范围暂时没有综合评级，评级每日收盘后更新。"))
            } else if vm.filteredItems.isEmpty {
                message(L("这个行业里暂时没有上榜的股票。"))
            } else {
                summaryRow
                field()
                legend
                listEntry
                Spacer(minLength: 0)
                disclaimer
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .sheet(isPresented: $showAll, onDismiss: {
            guard let e = pending else { return }
            pending = nil
            onOpen(e.symbol, e.name)
        }) {
            allSheet
        }
    }

    // MARK: - 概览 / 图例 / 榜单入口

    /// 与缠论雷达的 metaRow 同一位置：指数名 + 评级日。
    private var summaryRow: some View {
        HStack(spacing: 8) {
            Text(L("%@ · 综合评级最高", universeName))
                .font(.footnote).foregroundColor(Theme.textSecondary)
            Spacer()
            if !vm.asOf.isEmpty {
                Text(L("评级日 %@", SignalRadarView.monthDay(vm.asOf)))
                    .foregroundColor(Theme.textSecondary)
            }
        }
        .font(.footnote)
    }

    private func message(_ text: String) -> some View {
        VStack {
            Spacer()
            Text(text).font(.footnote).foregroundColor(Theme.textSecondary).multilineTextAlignment(.center)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    private var legend: some View {
        HStack(spacing: 14) {
            Text(L("越靠中心综合等级越高 · 气泡里是等级"))
                .font(.system(size: 10)).foregroundColor(Theme.textSecondary)
                .lineLimit(1).minimumScaleFactor(0.8)
            if vm.analystSupported {
                HStack(spacing: 4) {
                    Text("▲")
                        .font(.system(size: 10, weight: .bold)).foregroundColor(Theme.up)
                        .padding(.horizontal, 4).padding(.vertical, 1).background(Color.white, in: Capsule())
                    Text(L("券商净上调"))
                        .font(.system(size: 10)).foregroundColor(Theme.textSecondary)
                    Text("▼")
                        .font(.system(size: 10, weight: .bold)).foregroundColor(Theme.down)
                        .padding(.horizontal, 4).padding(.vertical, 1).background(Color.white, in: Capsule())
                    Text(L("净下调"))
                        .font(.system(size: 10)).foregroundColor(Theme.textSecondary)
                }
                .lineLimit(1).minimumScaleFactor(0.8)
            }
            Spacer(minLength: 4)
            Button { showInfo = true } label: {
                Image(systemName: "questionmark.circle")
                    .font(.system(size: 15))
                    .foregroundColor(Theme.textSecondary)
            }
            .accessibilityLabel(L("算法说明"))
            .sheet(isPresented: $showInfo) { infoSheet }
        }
    }

    /// 占缠论日期轨的位置（同高，保证两个 tab 画布一样高）：榜单说明 + 打开完整榜单。
    private var listEntry: some View {
        Button { showAll = true } label: {
            HStack(spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(L("综合评级榜"))
                        .font(.subheadline.weight(.semibold)).foregroundColor(Theme.textPrimary)
                    Text(entryHint)
                        .font(.caption2).foregroundColor(Theme.textSecondary).lineLimit(2)
                }
                Spacer(minLength: 8)
                Text(L("查看完整榜单"))
                    .font(.footnote.weight(.semibold)).foregroundColor(Theme.accent)
                Image(systemName: "chevron.right").font(.footnote).foregroundColor(Theme.textSecondary)
            }
            .padding(.horizontal, 14)
            .frame(maxWidth: .infinity, minHeight: 76, maxHeight: 76, alignment: .leading)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    private var entryHint: String {
        var parts = [L("%@ 中共 %lld 只有评级，按综合等级从高到低排", universeName, vm.rated)]
        if vm.analystSupported && vm.analystPending > 0 { parts.append(L("分析师角标补充中…")) }
        return parts.joined(separator: " · ")
    }

    /// 与缠论雷达底部同一位置、同一字号的一行说明。
    private var disclaimer: some View {
        Text(L("评级由量化指标计算，仅为孤立观测，不构成投资建议。"))
            .font(.caption2)
            .foregroundColor(Theme.textSecondary)
            .frame(maxWidth: .infinity)
            .padding(.top, 4)
    }

    /// 图例旁问号：这张雷达怎么看。
    private var infoSheet: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    ForEach([
                        L("范围：当前所选指数的成分股。每只股票每天有一个综合等级（A+ 到 F 共 13 档），雷达取每只股票最新的一个，从高到低排。"),
                        L("环：综合等级所在的段。最里圈 A 段（A+ / A / A-），中间圈 B 段，最外圈 C 及以下。气泡越大、颜色越深，等级越高。"),
                        L("角标：气泡右上角的白色小标是近 30 天券商评级的净调整——▲n 表示上调比下调多 n 家，▼n 表示下调比上调多 n 家，相同或没有则不显示。只统计美股；A 股、港股暂时没有这项数据。"),
                        L("数量：画布只画等级最高的前 10 只，其余在「查看完整榜单」里看。"),
                        L("评级与券商调整只是事实陈列，不代表后续涨跌，不构成投资建议。")
                    ], id: \.self) { line in
                        Text(line).font(.subheadline).foregroundColor(Theme.textPrimary)
                    }
                }
                .padding(16)
            }
            .background(Theme.background)
            .navigationTitle(L("算法说明"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button(L("完成")) { showInfo = false } } }
        }
        .presentationDetents([.medium, .large])
    }

    // MARK: - 查看全部

    private var allSheet: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(Array(vm.filteredItems.enumerated()), id: \.element.id) { i, e in
                        Button {
                            pending = e
                            showAll = false
                        } label: { row(e, rank: i + 1) }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 12).padding(.vertical, 8)
            }
            .background(Theme.background)
            .navigationTitle(L("%@ 综合评级榜", universeName))
            .navigationBarTitleDisplayMode(.inline)
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
    }

    private func row(_ e: FundamentalItem, rank: Int) -> some View {
        HStack(spacing: 10) {
            Text("\(rank)")
                .font(.system(size: 12, weight: .semibold, design: .monospaced))
                .foregroundColor(Theme.textSecondary).frame(width: 24)
            VStack(alignment: .leading, spacing: 2) {
                Text(e.name).font(.system(size: 15, weight: .semibold)).foregroundColor(Theme.textPrimary)
                HStack(spacing: 6) {
                    Text(e.symbol)
                    if let sector = e.sector { Text("· " + sectorName(sector)) }
                }
                .font(.system(size: 11)).foregroundColor(Theme.textSecondary)
            }
            Spacer()
            if let mark = e.analystMark {
                Text(mark)
                    .font(.system(size: 11, weight: .bold).monospacedDigit())
                    .foregroundColor(mark.hasPrefix("▲") ? Theme.up : Theme.down)
            }
            VStack(alignment: .trailing, spacing: 2) {
                Text(e.grade).font(.system(size: 17, weight: .bold)).foregroundColor(Theme.textPrimary)
                if let score = e.score {
                    Text(String(format: "%.1f", score)).font(.system(size: 11)).foregroundColor(Theme.textSecondary)
                }
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 12))
    }
}
