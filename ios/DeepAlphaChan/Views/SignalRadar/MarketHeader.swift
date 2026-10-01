import Charts
import SwiftUI

/// 雷达页顶部：市场分段控件 + 「宏观 / 情绪 / 行业」三格温度计。
///
/// 三格展示的都是当前所选市场；点任意一格打开对应的完整弹层。三格各自加载、各自失败
/// （失败那格显示重试），互不影响，也不影响下面的雷达。三格固定同一高度，异步数据到达
/// 时不挤动雷达画布。行业弹层里点某个行业 → 雷达在当前指数里只显示该行业的气泡。
struct MarketHeader: View {
    @ObservedObject var radarVM: SignalRadarViewModel
    @ObservedObject var panicVM: PanicIndexViewModel
    @ObservedObject var overviewVM: MarketOverviewViewModel

    private enum SheetKind: String, Identifiable {
        case macro, sentiment, sector
        var id: String { rawValue }
    }

    @State private var sheet: SheetKind?

    /// 三格内容区高度：标题行之下的两行内容。
    static let tileContentHeight: CGFloat = 40

    var body: some View {
        VStack(spacing: 8) {
            Picker(L("市场"), selection: Binding(get: { radarVM.market }, set: { radarVM.switchMarket($0) })) {
                ForEach(StockMarket.allCases) { m in
                    Text(m.title).tag(m)
                }
            }
            .pickerStyle(.segmented)

            HStack(spacing: 8) {
                macroTile
                sentimentTile
                sectorTile
            }
        }
        .task { panicVM.onAppear() }
        .task(id: radarVM.market) { overviewVM.load(radarVM.market) }
        .sheet(item: $sheet) { kind in
            switch kind {
            case .macro:
                MacroDetailSheet(market: radarVM.market)
            case .sentiment:
                if let resp = panicVM.responses[radarVM.market] {
                    PanicIndexDetailSheet(market: radarVM.market, response: resp)
                }
            case .sector:
                SectorBoardSheet(market: radarVM.market, radar: sectorRadarContext) { key, name in
                    radarVM.applySectorFilter(key: key, name: name)
                }
            }
        }
    }

    private var market: StockMarket { radarVM.market }

    /// 行业弹层里的买卖点数与可筛选状态：取雷达当前指数、当前选中日（与筛选条一致）。
    private var sectorRadarContext: SectorRadarContext? {
        guard let day = radarVM.baseSelectedDay, day.hasSectorData, let counts = day.sectorCounts else { return nil }
        let name = radarVM.universes.first(where: { $0.key == radarVM.activeUniverseKey })?.displayName ?? ""
        return SectorRadarContext(universeName: name, date: day.date, counts: counts, selectedKey: radarVM.sectorFilter?.key)
    }
    private var overview: MarketOverview? { overviewVM.overviews[market] }

    // MARK: - 三格

    private var macroTile: some View {
        tile(title: L("宏观"), enabled: overview?.macroState != nil, kind: .macro) {
            if let overview, !overview.available {
                buildingText
            } else if let state = overview?.macroState {
                HStack(alignment: .firstTextBaseline, spacing: 3) {
                    Text(state.labelText)
                        .font(.system(size: 17, weight: .bold, design: .rounded))
                        .foregroundColor(MarketHeader.regimeColor(state.label))
                    Text("\(Int((state.probability * 100).rounded()))%")
                        .font(.system(size: 10))
                        .foregroundColor(Theme.textSecondary)
                }
                Text(macroSubtitle(overview?.nextEvent, state: state))
                    .font(.system(size: 10))
                    .foregroundColor(Theme.textSecondary)
                    .lineLimit(1)
            } else if overview != nil {
                preparingText
            } else {
                loadingOrRetry(failed: overviewVM.failedMarkets.contains(market)) { overviewVM.retry(market) }
            }
        }
    }

    private var sentimentTile: some View {
        let resp = panicVM.responses[market]
        return tile(title: L("情绪"), enabled: resp != nil, kind: .sentiment) {
            if let resp {
                HStack(alignment: .firstTextBaseline, spacing: 3) {
                    Text("\(Int(resp.current.score.rounded()))")
                        .font(.system(size: 17, weight: .bold, design: .rounded))
                        .foregroundColor(PanicIndexStyle.ratingColor(resp.current.score))
                    Text(PanicIndexStyle.ratingLabel(resp.current.rating))
                        .font(.system(size: 10))
                        .foregroundColor(Theme.textSecondary)
                        .lineLimit(1)
                }
                sparkline(resp)
            } else {
                loadingOrRetry(failed: panicVM.failedMarkets.contains(market)) { panicVM.retry(market) }
            }
        }
    }

    private var sectorTile: some View {
        tile(title: L("行业"), enabled: overview?.strongest != nil, kind: .sector) {
            if let overview, !overview.available {
                buildingText
            } else if let strongest = overview?.strongest {
                sectorLine(strongest, up: true)
                if let weakest = overview?.weakest { sectorLine(weakest, up: false) }
            } else if overview != nil {
                preparingText
            } else {
                loadingOrRetry(failed: overviewVM.failedMarkets.contains(market)) { overviewVM.retry(market) }
            }
        }
    }

    // MARK: - 组件

    private func tile<Content: View>(
        title: String, enabled: Bool, kind: SheetKind, @ViewBuilder content: () -> Content
    ) -> some View {
        // 用 Button 而不是 onTapGesture：按下有反馈，读屏 / 辅助功能也能激活
        Button { sheet = kind } label: {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 2) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundColor(Theme.textSecondary)
                Spacer(minLength: 0)
                if enabled {
                    Image(systemName: "chevron.right")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundColor(Theme.textSecondary.opacity(0.7))
                }
            }
            VStack(alignment: .leading, spacing: 3) { content() }
                .frame(maxWidth: .infinity, alignment: .leading)
                .frame(height: MarketHeader.tileContentHeight, alignment: .topLeading)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.border, lineWidth: 1))
        .contentShape(Rectangle())
        }
        .buttonStyle(TilePressStyle())
        .disabled(!enabled)
    }

    private var buildingText: some View {
        Text(L("数据建设中"))
            .font(.system(size: 11))
            .foregroundColor(Theme.textSecondary)
            .padding(.top, 4)
    }

    /// 已上线但当天的状态还没算出来（例如刚部署、每日重算还在跑）。
    private var preparingText: some View {
        Text(L("数据准备中"))
            .font(.system(size: 11))
            .foregroundColor(Theme.textSecondary)
            .padding(.top, 4)
    }

    @ViewBuilder
    private func loadingOrRetry(failed: Bool, retry: @escaping () -> Void) -> some View {
        if failed {
            Button(action: retry) {
                HStack(spacing: 3) {
                    Image(systemName: "arrow.clockwise").font(.system(size: 10))
                    Text(L("重试")).font(.system(size: 11))
                }
                .foregroundColor(Theme.textSecondary)
            }
            .padding(.top, 4)
        } else {
            ProgressView().controlSize(.mini).padding(.top, 6)
        }
    }

    private func sectorLine(_ s: SectorBrief, up: Bool) -> some View {
        HStack(spacing: 3) {
            Image(systemName: up ? "arrow.up" : "arrow.down")
                .font(.system(size: 9, weight: .bold))
            Text(s.name)
                .font(.system(size: 13, weight: .semibold))
                .lineLimit(1)
                .minimumScaleFactor(0.8)
        }
        .foregroundColor(up ? Theme.up : Theme.down)
    }

    /// 迷你走势：近 60 个交易日，只给形状。
    private func sparkline(_ resp: PanicIndexResponse) -> some View {
        Chart(Array(resp.history.suffix(60))) { p in
            LineMark(x: .value("date", p.date), y: .value("score", p.score))
                .foregroundStyle(PanicIndexStyle.ratingColor(resp.current.score))
                .lineStyle(StrokeStyle(lineWidth: 1.5))
                .interpolationMethod(.catmullRom)
        }
        .chartYScale(domain: 0...100)
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
        .frame(height: 16)
    }

    private func macroSubtitle(_ event: MacroEvent?, state: MacroState) -> String {
        if let event {
            return "\(MarketHeader.weekday(event.date)) \(event.name)"
        }
        return L("已持续 %lld 天", state.daysInState)
    }

    // MARK: - 共用格式

    /// 市场状态配色：沿用全 App 红=偏多 / 绿=偏空——逐利红、避险绿、观望灰。
    static func regimeColor(_ label: String?) -> Color {
        switch label {
        case "risk_on": return Theme.up
        case "risk_off": return Theme.down
        default: return Theme.textSecondary
        }
    }

    private static let isoParser: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "UTC")
        return f
    }()

    /// "2026-10-02" → 「周五」/「Fri」。
    static func weekday(_ date: String) -> String {
        guard let d = isoParser.date(from: date) else { return date }
        let f = DateFormatter()
        f.timeZone = TimeZone(identifier: "UTC")
        f.locale = Locale(identifier: Localized.language() == .english ? "en_US" : "zh_Hans_CN")
        f.dateFormat = "EEE"
        return f.string(from: d)
    }

    /// "2026-10-02" → 「10/02」。
    static func monthDay(_ date: String) -> String {
        let parts = date.split(separator: "-")
        guard parts.count == 3 else { return date }
        return "\(parts[1])/\(parts[2])"
    }
}

/// 三格按下时略微缩小、调暗；不可点时保持原样（不置灰，内容仍要看得清）。
private struct TilePressStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .opacity(configuration.isPressed ? 0.8 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}
