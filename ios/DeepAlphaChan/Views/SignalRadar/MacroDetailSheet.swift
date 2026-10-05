import Charts
import SwiftUI

/// 环境弹层（雷达顶部「环境」格）：市场状态 + 三态概率条 + 近一年状态色带 + 情绪（恐慌贪婪）
/// + 驱动因素 + 未来 7 天宏观日历。只描述环境，不给操作建议。
struct MacroDetailSheet: View {
    let market: StockMarket
    /// 情绪（恐慌贪婪指数），由雷达页已拉到的数据传入；nil 时不显示情绪卡。
    var panic: PanicIndexResponse? = nil

    @Environment(\.dismiss) private var dismiss
    @State private var data: MacroResponse?
    @State private var failed = false
    @State private var showPanicDetail = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if let data, let state = data.state {
                        stateCard(state, sentimentScore: panic?.current.score)
                        if !data.history.isEmpty { historyBand(data.history) }
                        if let panic { sentimentCard(panic) }
                        // 驱动因素与宏观日历的数据源只覆盖美股；A 股 / 港股没有就不画空卡片
                        // （否则会写出「未来 7 天没有重要宏观事件」，其实是没有数据）
                        if !data.drivers.isEmpty { driversCard(data.drivers) }
                        if market == .us || !data.events.isEmpty { eventsCard(data.events) }
                        footnote
                    } else if let data, !data.available {
                        // 这个市场的大盘状态还没上线（A 股 / 港股）：重试没有意义，不给重试按钮；
                        // 情绪（恐慌贪婪）是有的，照常展示。
                        if let panic { sentimentCard(panic) }
                        Text(L("%@大盘状态建设中，暂时只有市场情绪。", market.title))
                            .font(.footnote).foregroundColor(Theme.textSecondary)
                            .frame(maxWidth: .infinity).padding(.top, panic == nil ? 60 : 8)
                    } else if failed || data != nil {
                        VStack(spacing: 10) {
                            Text(data == nil ? L("加载失败，请稍后再试") : L("数据准备中"))
                                .font(.footnote).foregroundColor(Theme.textSecondary)
                            Button(L("重试")) { Task { await load() } }
                                .buttonStyle(.bordered).tint(Theme.accent)
                        }
                        .frame(maxWidth: .infinity).padding(.top, 60)
                    } else {
                        ProgressView().frame(maxWidth: .infinity).padding(.top, 60)
                    }
                }
                .padding(16)
            }
            .background(Theme.background)
            .navigationTitle(L("%@市场环境", market.title))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) { Button(L("关闭")) { dismiss() } }
            }
        }
        .task { await load() }
    }

    private func load() async {
        failed = false
        do {
            data = try await MarketOverviewService.macro(market: market)
        } catch {
            failed = true
        }
    }

    // MARK: - 状态

    private func stateCard(_ state: MacroState, sentimentScore: Double?) -> some View {
        SectionCard(title: L("市场状态"), titleFont: .subheadline.weight(.semibold)) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(state.labelText)
                        .font(.system(size: 28, weight: .bold, design: .rounded))
                        .foregroundColor(MarketHeader.regimeColor(state.label))
                    Text(L("概率 %lld%%", Int((state.probability * 100).rounded())))
                        .font(.subheadline).foregroundColor(Theme.textSecondary)
                    Spacer()
                    Text(L("已持续 %lld 天", state.daysInState))
                        .font(.caption).foregroundColor(Theme.textSecondary)
                }
                probabilityBar(state)
                Text(L("由进攻、防御、现金三组资产的相对强弱，加上波动率和量能综合判定，按概率给出；%@ 收盘数据。", state.asOf))
                    .font(.caption2).foregroundColor(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                if let note = consistencyNote(state, sentimentScore: sentimentScore) {
                    Text(note)
                        .font(.caption2).foregroundColor(Theme.textSecondary)
                        .padding(8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 6))
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    /// 状态与情绪方向相反时的一句说明（口径不同，不是数据错误）。
    private func consistencyNote(_ state: MacroState, sentimentScore: Double?) -> String? {
        guard let score = sentimentScore,
              let kind = MacroConsistency.kind(label: state.label, score: score) else { return nil }
        switch kind {
        case .riskOnButFear:
            return L("资金偏向进攻资产，但整体情绪仍偏恐慌。市场状态看近 20 个交易日的资金流向，情绪分看市场整体温度，两者口径不同，常见于下跌后的修复初期。")
        case .riskOffButGreed:
            return L("资金偏向防御资产，但整体情绪仍偏乐观。市场状态看近 20 个交易日的资金流向，情绪分看市场整体温度，两者口径不同，常见于上涨后的降温初期。")
        }
    }

    private func probabilityBar(_ state: MacroState) -> some View {
        let parts: [(String, Double, String?)] = [
            (L("逐利"), state.pRiskOn, "risk_on"), (L("观望"), state.pNeutral, "neutral"),
            (L("避险"), state.pRiskOff, "risk_off"),
        ]
        return VStack(alignment: .leading, spacing: 6) {
            GeometryReader { geo in
                HStack(spacing: 2) {
                    ForEach(parts, id: \.0) { part in
                        Rectangle()
                            .fill(MarketHeader.regimeColor(part.2).opacity(part.2 == state.label ? 0.9 : 0.35))
                            .frame(width: max(2, (geo.size.width - 4) * part.1))
                    }
                }
            }
            .frame(height: 8)
            .clipShape(Capsule())
            HStack(spacing: 12) {
                ForEach(parts, id: \.0) { part in
                    HStack(spacing: 4) {
                        Circle().fill(MarketHeader.regimeColor(part.2)).frame(width: 6, height: 6)
                        Text("\(part.0) \(Int((part.1 * 100).rounded()))%")
                            .font(.caption2).foregroundColor(Theme.textSecondary)
                    }
                }
            }
        }
    }

    // MARK: - 状态色带

    private func historyBand(_ history: [MacroStatePoint]) -> some View {
        SectionCard(title: L("近一年状态"), titleFont: .subheadline.weight(.semibold)) {
            VStack(alignment: .leading, spacing: 8) {
                Canvas { ctx, size in
                    let w = size.width / CGFloat(history.count)
                    for (i, p) in history.enumerated() {
                        let rect = CGRect(x: CGFloat(i) * w, y: 0, width: w + 0.5, height: size.height)
                        let color = p.label == nil ? Theme.surfaceAlt : MarketHeader.regimeColor(p.label).opacity(p.pending == true ? 0.4 : 0.75)
                        ctx.fill(Path(rect), with: .color(color))
                    }
                }
                .frame(height: 18)
                .clipShape(RoundedRectangle(cornerRadius: 4))
                HStack {
                    Text(history.first?.date ?? "")
                    Spacer()
                    Text(history.last?.date ?? "")
                }
                .font(.caption2).foregroundColor(Theme.textSecondary)
                if history.contains(where: { $0.pending == true }) {
                    Text(L("最右侧浅色为尚未连续确认的最新判定。"))
                        .font(.caption2).foregroundColor(Theme.textSecondary)
                }
            }
        }
    }

    // MARK: - 情绪

    private func sentimentCard(_ panic: PanicIndexResponse) -> some View {
        SectionCard(title: L("情绪 · 恐慌贪婪"), titleFont: .subheadline.weight(.semibold)) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .firstTextBaseline, spacing: 16) {
                    sentimentItem(L("当前"), panic.current, large: true)
                    sentimentItem(L("一周前"), panic.previousWeek, large: false)
                    sentimentItem(L("一月前"), panic.previousMonth, large: false)
                    Spacer(minLength: 0)
                }
                Chart(Array(panic.history.suffix(60))) { p in
                    LineMark(x: .value("date", p.date), y: .value("score", p.score))
                        .foregroundStyle(PanicIndexStyle.ratingColor(panic.current.score))
                        .lineStyle(StrokeStyle(lineWidth: 1.5))
                        .interpolationMethod(.catmullRom)
                }
                .chartYScale(domain: 0...100)
                .chartXAxis(.hidden)
                .chartYAxis(.hidden)
                .frame(height: 44)
                HStack {
                    Text(L("近 60 个交易日。分数 0~100，越低越恐慌、越高越贪婪。"))
                        .font(.caption2).foregroundColor(Theme.textSecondary)
                    Spacer(minLength: 8)
                    Button(L("完整走势")) { showPanicDetail = true }
                        .font(.caption.weight(.semibold))
                        .tint(Theme.accent)
                }
            }
        }
        .sheet(isPresented: $showPanicDetail) {
            PanicIndexDetailSheet(market: market, response: panic)
        }
    }

    private func sentimentItem(_ title: String, _ snap: PanicIndexSnapshot, large: Bool) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.caption2).foregroundColor(Theme.textSecondary)
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text("\(Int(snap.score.rounded()))")
                    .font(large ? .title2.bold() : .subheadline.bold())
                    .foregroundColor(PanicIndexStyle.ratingColor(snap.score))
                Text(PanicIndexStyle.ratingLabel(snap.rating))
                    .font(.caption2).foregroundColor(Theme.textSecondary)
            }
        }
    }

    // MARK: - 驱动因素

    private func driversCard(_ drivers: [MacroDriver]) -> some View {
        SectionCard(title: L("驱动因素（近 20 个交易日）"), titleFont: .subheadline.weight(.semibold)) {
            VStack(alignment: .leading, spacing: 12) {
                ForEach(drivers) { d in
                    VStack(alignment: .leading, spacing: 3) {
                        HStack(alignment: .firstTextBaseline) {
                            Text(d.name).font(.footnote.weight(.medium)).foregroundColor(Theme.textPrimary)
                            Spacer()
                            if let value = MacroDetailSheet.valueText(d) {
                                Text(value).font(.footnote.monospacedDigit()).foregroundColor(Theme.textPrimary)
                            }
                            if let change = MacroDetailSheet.changeText(d) {
                                HStack(spacing: 2) {
                                    Image(systemName: MacroDetailSheet.arrow(d.direction)).font(.system(size: 9, weight: .bold))
                                    Text(change).font(.caption.monospacedDigit())
                                }
                                .foregroundColor(MacroDetailSheet.impactColor(d.impact))
                            }
                        }
                        Text(d.text).font(.caption).foregroundColor(Theme.textSecondary)
                    }
                    if d.id != drivers.last?.id { Divider().overlay(Theme.border) }
                }
            }
        }
    }

    // MARK: - 宏观日历

    private func eventsCard(_ events: [MacroEvent]) -> some View {
        SectionCard(title: L("未来 7 天宏观日历"), titleFont: .subheadline.weight(.semibold)) {
            VStack(alignment: .leading, spacing: 10) {
                if events.isEmpty {
                    Text(L("未来 7 天没有重要宏观事件")).font(.caption).foregroundColor(Theme.textSecondary)
                } else {
                    ForEach(events) { e in
                        HStack(spacing: 8) {
                            Text("\(MarketHeader.monthDay(e.date)) \(MarketHeader.weekday(e.date))")
                                .font(.caption.monospacedDigit()).foregroundColor(Theme.textSecondary)
                                .frame(width: 74, alignment: .leading)
                            Text(e.time).font(.caption.monospacedDigit()).foregroundColor(Theme.textSecondary)
                            Text(e.name).font(.footnote).foregroundColor(Theme.textPrimary)
                            Spacer()
                            HStack(spacing: 2) {
                                ForEach(0..<3, id: \.self) { i in
                                    Circle()
                                        .fill(i < e.importance ? Theme.accent : Theme.border)
                                        .frame(width: 5, height: 5)
                                }
                            }
                        }
                    }
                    Text(L("时间为当地交易所时间。")).font(.caption2).foregroundColor(Theme.textSecondary)
                }
            }
        }
    }

    private var footnote: some View {
        Text(L("以上内容为对市场环境的客观描述，不构成任何投资建议。"))
            .font(.caption2).foregroundColor(Theme.textSecondary)
            .frame(maxWidth: .infinity, alignment: .center)
    }

    // MARK: - 格式

    static func valueText(_ d: MacroDriver) -> String? {
        guard let v = d.value else { return nil }
        switch d.unit {
        case "percent": return String(format: "%.2f%%", v)
        default: return String(format: "%.1f", v)
        }
    }

    static func changeText(_ d: MacroDriver) -> String? {
        guard let c = d.change else { return nil }
        switch d.unit {
        case "percent": return String(format: "%+.0fbp", c)
        case "point": return String(format: "%+.1f", c)
        default: return String(format: "%+.1f%%", c)
        }
    }

    static func arrow(_ direction: String?) -> String {
        switch direction {
        case "up": return "arrow.up"
        case "down": return "arrow.down"
        default: return "arrow.right"
        }
    }

    /// 对股票偏有利红、偏不利绿、中性灰（全 App 红=偏多 / 绿=偏空）。
    static func impactColor(_ impact: String) -> Color {
        switch impact {
        case "positive": return Theme.up
        case "negative": return Theme.down
        default: return Theme.textSecondary
        }
    }
}
