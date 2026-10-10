import SwiftUI

/// 雷达页顶部，自上而下一条线：环境友不友好 → 钱往哪个行业走 → 哪些股票出现了结构信号。
///
/// 两块：
/// 1. **市场卡**——美股 / A 股 / 港股分段条（选中那段下面写当前指数名，点它弹出指数列表）与「大盘环境」条合在同一张卡里：
///    选哪个市场，紧挨着的下一行就是这个市场的环境（宏观状态 + 情绪），点开是环境面板。
/// 2. **行业横条**——「全部」+ 各行业胶囊（从强到弱，带相对大盘强弱 / 当日信号数），直接点选就筛雷达，不用再开面板；
///    末尾的列表按钮打开完整的行业强弱面板。
/// 只陈列事实。各块各自加载、各自失败（失败显示重试），固定高度，异步数据到达时不挤动雷达画布。
struct MarketHeader: View {
    @ObservedObject var radarVM: SignalRadarViewModel
    @ObservedObject var panicVM: PanicIndexViewModel
    @ObservedObject var overviewVM: MarketOverviewViewModel
    let onOpen: (RadarPanel) -> Void

    var body: some View {
        VStack(spacing: 8) {
            marketCard
            sectorRail
        }
        .task { panicVM.onAppear() }
        .task(id: radarVM.market) { overviewVM.load(radarVM.market) }
    }

    private var market: StockMarket { radarVM.market }

    private static let allChipID = "_all"

    // MARK: - 市场卡：分段条 + 大盘环境

    private var marketCard: some View {
        VStack(spacing: 0) {
            marketSegments
            Divider().overlay(Theme.border)
            environmentStrip
        }
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 13))
        .overlay(RoundedRectangle(cornerRadius: 13).stroke(Theme.border, lineWidth: 1))
    }

    // MARK: - 市场 + 指数（合成一个选择器）

    /// 美股 / A 股 / 港股分段条。已选中的那一段下面写当前指数名并带下拉箭头，**点它弹出该市场的指数列表**
    /// （纳斯达克 100 / 标普 500 / 自选…）。其他段点一下切市场。
    private var marketSegments: some View {
        HStack(spacing: 2) {
            ForEach(StockMarket.allCases) { m in
                if m == radarVM.market {
                    Menu {
                        ForEach(radarVM.universes) { u in
                            Button { radarVM.switchUniverse(u.key) } label: {
                                if u.key == radarVM.activeUniverseKey {
                                    Label(u.displayName, systemImage: "checkmark")
                                } else {
                                    Text(u.displayName)
                                }
                            }
                        }
                    } label: { segment(m, selected: true, menu: true) }
                    .accessibilityLabel(L("切换指数范围"))
                } else {
                    Button { radarVM.switchMarket(m) } label: { segment(m, selected: m == radarVM.market, menu: false) }
                        .buttonStyle(.plain)
                }
            }
        }
        .padding(3)
    }

    private func segment(_ m: StockMarket, selected: Bool, menu: Bool) -> some View {
        VStack(spacing: 2) {
            Text(m.title).font(.system(size: 14, weight: selected ? .bold : .medium))
            // 固定占一行高度：未选中的段也留位，三段一样高，切换时分段条不会忽高忽低
            HStack(spacing: 3) {
                Text(selected ? radarVM.activeUniverseName : " ").font(.system(size: 10, weight: .medium)).lineLimit(1)
                if selected, menu { Image(systemName: "chevron.down").font(.system(size: 7, weight: .bold)) }
            }
            .opacity(selected ? 0.85 : 0)
        }
        .foregroundColor(selected ? Theme.textPrimary : Theme.textSecondary)
        .frame(maxWidth: .infinity, minHeight: 44)
        .background(selected ? Theme.accent.opacity(0.28) : Color.clear, in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(selected ? Theme.accent.opacity(0.7) : .clear, lineWidth: 1))
        .contentShape(Rectangle())
        .accessibilityAddTraits(selected ? [.isSelected] : [])
    }

    private var overview: MarketOverview? { overviewVM.overviews[market] }

    // MARK: - 大盘环境条（市场卡下半）

    /// 一行：「大盘环境」+ 宏观状态 + 概率 · 情绪分与档位；整行可点，打开环境面板。
    private var environmentStrip: some View {
        let panic = panicVM.responses[market]
        let state = overview?.macroState
        let enabled = state != nil || panic != nil
        return Button { onOpen(.environment) } label: {
            HStack(spacing: 8) {
                Text(L("大盘环境")).font(.caption.weight(.semibold)).foregroundColor(Theme.textSecondary)
                if let state {
                    HStack(alignment: .firstTextBaseline, spacing: 3) {
                        Text(state.labelText)
                            .font(.system(size: 14, weight: .bold, design: .rounded))
                            .foregroundColor(MarketHeader.regimeColor(state.label))
                        Text("\(Int((state.probability * 100).rounded()))%")
                            .font(.system(size: 10)).foregroundColor(Theme.textSecondary)
                    }
                    RegimeBar(up: state.pRiskOn, mid: state.pNeutral, down: state.pRiskOff)
                        .frame(width: 34, height: 4)
                        .accessibilityHidden(true)
                } else if let overview, !overview.available {
                    buildingText
                } else if overview != nil {
                    preparingText
                } else {
                    loadingOrRetry(failed: overviewVM.failedMarkets.contains(market)) { overviewVM.retry(market) }
                }
                if let panic {
                    Text("·").foregroundColor(Theme.textSecondary.opacity(0.6))
                    Text(L("情绪 %lld %@", Int(panic.current.score.rounded()), PanicIndexStyle.ratingLabel(panic.current.rating)))
                        .font(.system(size: 11)).foregroundColor(Theme.textSecondary)
                        .lineLimit(1).minimumScaleFactor(0.8)
                } else if panicVM.failedMarkets.contains(market) {
                    Button { panicVM.retry(market) } label: {
                        Text(L("情绪 重试")).font(.system(size: 11)).foregroundColor(Theme.textSecondary)
                    }
                }
                Spacer(minLength: 0)
                if enabled {
                    Image(systemName: "chevron.right")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(Theme.textSecondary.opacity(0.7))
                }
            }
            .padding(.horizontal, 12)
            .frame(height: 36)
            .contentShape(Rectangle())
        }
        .buttonStyle(TilePressStyle())
        .disabled(!enabled)
    }

    // MARK: - 行业横条

    /// 选中日行业：有强弱的从强到弱；没有强弱（A 股 / 港股）按当日信号数从多到少。
    private var sectorRows: [SectorRow] {
        let day = radarVM.baseSelectedDay
        return (radarVM.selectedSectorBoard?.sectors ?? []).sorted {
            switch ($0.rsVsMarket, $1.rsVsMarket) {
            case let (a?, b?): return a > b
            case (nil, nil): return (day?.signalCount(sector: $0.key) ?? 0) > (day?.signalCount(sector: $1.key) ?? 0)
            case (_?, nil): return true
            case (nil, _?): return false
            }
        }
    }

    /// 「全部」+ 各行业胶囊，点一下筛雷达（再点已选的取消）；末尾按钮打开完整行业面板。
    /// 没有行业数据（美股以外建设中 / 自选 / 旧快照 / 加载中）时同一高度显示状态文字，不挤动画布。
    private var sectorRail: some View {
        let rows = sectorRows
        let canPick = !rows.isEmpty && radarVM.baseSelectedDay?.sectorRailReady == true
        return HStack(spacing: 8) {
            if canPick {
                ScrollViewReader { proxy in
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            sectorChip(title: L("全部行业"), detail: nil, detailColor: Theme.textSecondary,
                                       selected: radarVM.sectorFilter == nil) { radarVM.setSectorFilter(nil) }
                                .id(MarketHeader.allChipID)
                            ForEach(rows) { row in
                                sectorChip(title: row.name, detail: chipDetail(row), detailColor: chipColor(row),
                                           selected: radarVM.sectorFilter == row.key) {
                                    radarVM.setSectorFilter(radarVM.sectorFilter == row.key ? nil : row.key)
                                }
                                .id(row.key)
                            }
                        }
                        .padding(.horizontal, 1)
                    }
                    // 右边缘淡出：提示后面还能滑，而不是把最后一个胶囊硬切一半
                    .mask(
                        HStack(spacing: 0) {
                            Rectangle()
                            LinearGradient(colors: [.black, .clear], startPoint: .leading, endPoint: .trailing)
                                .frame(width: 22)
                        }
                    )
                    // 从行业面板里选了行业时，横条自动滚到它，不会选了却看不见
                    .onChange(of: radarVM.sectorFilter) { _, key in
                        withAnimation(.easeInOut(duration: 0.25)) {
                            proxy.scrollTo(key ?? MarketHeader.allChipID, anchor: .center)
                        }
                    }
                    .sensoryFeedback(.selection, trigger: radarVM.sectorFilter)
                }
                Button { onOpen(.sectorPicker) } label: {
                    Image(systemName: "building.2")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(Theme.accent)
                        .frame(width: 34, height: 34)
                        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 10))
                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.border, lineWidth: 1))
                }
                .accessibilityLabel(L("行业强弱"))
            } else {
                HStack(spacing: 6) {
                    Text(L("行业")).font(.caption.weight(.semibold)).foregroundColor(Theme.textSecondary)
                    if let overview, !overview.available {
                        buildingText
                    } else if overview != nil {
                        preparingText
                    } else {
                        loadingOrRetry(failed: overviewVM.failedMarkets.contains(market)) { overviewVM.retry(market) }
                    }
                    Spacer(minLength: 0)
                }
                .padding(.horizontal, 12)
            }
        }
        .frame(height: 34)
    }

    private func chipDetail(_ row: SectorRow) -> String {
        if let rs = row.rsVsMarket { return SectorBoardList.rsText(rs) }
        return "\(radarVM.baseSelectedDay?.signalCount(sector: row.key) ?? 0)"
    }

    private func chipColor(_ row: SectorRow) -> Color {
        guard let rs = row.rsVsMarket else { return Theme.textSecondary }
        return rs >= 0 ? Theme.up : Theme.down
    }

    private func sectorChip(title: String, detail: String?, detailColor: Color, selected: Bool,
                            action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 5) {
                Text(title).font(.system(size: 13, weight: selected ? .bold : .medium)).lineLimit(1)
                if let detail {
                    Text(detail).font(.system(size: 10, weight: .semibold).monospacedDigit())
                        .foregroundColor(selected ? Theme.textPrimary.opacity(0.85) : detailColor)
                }
            }
            .foregroundColor(selected ? Theme.textPrimary : Theme.textSecondary)
            .padding(.horizontal, 11).frame(height: 32)
            .background(selected ? Theme.accent.opacity(0.28) : Theme.surface, in: Capsule())
            .overlay(Capsule().stroke(selected ? Theme.accent.opacity(0.7) : Theme.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? [.isSelected] : [])
    }

    // MARK: - 组件

    private var buildingText: some View {
        Text(L("数据建设中"))
            .font(.system(size: 11))
            .foregroundColor(Theme.textSecondary)
    }

    /// 已上线但当天的状态还没算出来（例如刚部署、每日重算还在跑）。
    private var preparingText: some View {
        Text(L("数据准备中"))
            .font(.system(size: 11))
            .foregroundColor(Theme.textSecondary)
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
        } else {
            ProgressView().controlSize(.mini)
        }
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


/// 三态概率条：逐利（红）/ 观望（灰）/ 避险（绿）按概率分段，一眼看出当前状态占多大优势。
/// 三个概率之和不到 1（取整、旧数据）时按比例归一化，全 0 时画一条灰底。
private struct RegimeBar: View {
    let up: Double
    let mid: Double
    let down: Double

    var body: some View {
        GeometryReader { geo in
            let total = max(up + mid + down, 0.0001)
            HStack(spacing: 1) {
                seg(Theme.up, up / total, geo.size.width)
                seg(Theme.textSecondary.opacity(0.55), mid / total, geo.size.width)
                seg(Theme.down, down / total, geo.size.width)
            }
        }
        .clipShape(Capsule())
        .background(Theme.border.opacity(0.6), in: Capsule())
    }

    @ViewBuilder
    private func seg(_ color: Color, _ share: Double, _ width: CGFloat) -> some View {
        if share > 0.01 { color.frame(width: max(width * share - 1, 1)) }
    }
}
