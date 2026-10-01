import SwiftUI

/// 雷达页顶部：市场分段控件 + 「大盘环境 › 行业」两张横向卡片，往下就是雷达，自上而下的一条线：
/// 环境友不友好 → 钱往哪个行业走 → 哪些股票出现了结构信号。
///
/// 三格都只陈列事实，点开是底部面板（留在雷达页，见 RadarPanels）：环境 = 宏观状态 + 情绪；
/// 行业 = 选中日相对大盘最强的行业（与扇区雷达同一份强弱表）；当日信号 = 选中日在场信号数。
/// 各格各自加载、各自失败（失败那格显示重试），固定同一高度，异步数据到达时不挤动雷达画布。
struct MarketHeader: View {
    @ObservedObject var radarVM: SignalRadarViewModel
    @ObservedObject var panicVM: PanicIndexViewModel
    @ObservedObject var overviewVM: MarketOverviewViewModel
    let onOpen: (RadarPanel) -> Void


    var body: some View {
        VStack(spacing: 8) {
            Picker(L("市场"), selection: Binding(get: { radarVM.market }, set: { radarVM.switchMarket($0) })) {
                ForEach(StockMarket.allCases) { m in
                    Text(m.title).tag(m)
                }
            }
            .pickerStyle(.segmented)

            // 两张卡片横排、中间一个「›」：大盘环境 → 行业，往下就是雷达
            HStack(spacing: 2) {
                environmentTile
                stepArrow
                sectorTile
            }
        }
        .task { panicVM.onAppear() }
        .task(id: radarVM.market) { overviewVM.load(radarVM.market) }
    }

    private var market: StockMarket { radarVM.market }

    private var overview: MarketOverview? { overviewVM.overviews[market] }

    // MARK: - 三格

    private var environmentTile: some View {
        let panic = panicVM.responses[market]
        let state = overview?.macroState
        return tile(step: 1, title: L("大盘环境"), enabled: state != nil || panic != nil, action: { onOpen(.environment) }) {
            if let state {
                HStack(alignment: .firstTextBaseline, spacing: 3) {
                    Text(state.labelText)
                        .font(.system(size: 14, weight: .bold, design: .rounded))
                        .foregroundColor(MarketHeader.regimeColor(state.label))
                    Text("\(Int((state.probability * 100).rounded()))%")
                        .font(.system(size: 10))
                        .foregroundColor(Theme.textSecondary)
                }
            } else if let overview, !overview.available {
                buildingText
            } else if overview != nil {
                preparingText
            } else {
                loadingOrRetry(failed: overviewVM.failedMarkets.contains(market)) { overviewVM.retry(market) }
            }
            if let panic {
                Text(L("情绪 %lld %@", Int(panic.current.score.rounded()), PanicIndexStyle.ratingLabel(panic.current.rating)))
                    .font(.system(size: 10))
                    .foregroundColor(Theme.textSecondary)
                    .lineLimit(1)
            } else if panicVM.failedMarkets.contains(market) {
                Button { panicVM.retry(market) } label: {
                    Text(L("情绪 重试")).font(.system(size: 10)).foregroundColor(Theme.textSecondary)
                }
            }
        }
    }

    /// 选中日相对大盘最强的行业；这一天没有行业统计（自选、旧快照）时退回最新的摘要。
    private var leadingSector: (key: String?, name: String, rs: Double?)? {
        if let top = radarVM.selectedSectorBoard?.sectors.max(by: { ($0.rsVsMarket ?? -.infinity) < ($1.rsVsMarket ?? -.infinity) }) {
            return (top.key, top.name, top.rsVsMarket)
        }
        if let s = overview?.strongest { return (nil, s.name, s.rsVsMarket) }
        return nil
    }

    /// 选中日行业从强到弱（筛选菜单的顺序）。
    private var sectorRows: [SectorRow] {
        (radarVM.selectedSectorBoard?.sectors ?? [])
            .sorted { ($0.rsVsMarket ?? -.infinity) > ($1.rsVsMarket ?? -.infinity) }
    }

    /// 行业卡片：点开选行业面板（行业强弱列表 + 「全部行业」），选了哪个行业雷达就只看这个行业
    /// （radarVM.sectorFilter）。默认「全部行业」，副标题写最强的行业。
    private var sectorTile: some View {
        let rows = radarVM.selectedSectorBoard?.sectors ?? []
        let canPick = !rows.isEmpty && radarVM.baseSelectedDay?.hasSectorData == true
        let selected = radarVM.sectorFilter.flatMap { key in rows.first { $0.key == key } }
        return tile(step: 2, title: L("行业"), enabled: canPick, action: { onOpen(.sectorPicker) }) {
            if let selected {
                Text(selected.name)
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(Theme.accent)
                    .minimumScaleFactor(0.8)
                Text(L("相对大盘 %@", SectorBoardList.rsText(selected.rsVsMarket)))
                    .font(.system(size: 10).monospacedDigit())
                    .foregroundColor((selected.rsVsMarket ?? 0) >= 0 ? Theme.up : Theme.down)
            } else if let lead = leadingSector {
                Text(L("全部行业"))
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(Theme.textPrimary)
                Text(L("最强 %@ %@", lead.name, SectorBoardList.rsText(lead.rs)))
                    .font(.system(size: 10).monospacedDigit())
                    .foregroundColor(Theme.textSecondary)
            } else if let overview, !overview.available {
                buildingText
            } else if overview != nil {
                preparingText
            } else {
                loadingOrRetry(failed: overviewVM.failedMarkets.contains(market)) { overviewVM.retry(market) }
            }
        }
    }

    // MARK: - 组件

    /// 卡片内容区高度：标题行之下的两行内容（固定高度，异步数据到达时不挤动雷达画布）。
    private static let tileContentHeight: CGFloat = 34

    /// 卡片之间表示递进的「›」。
    private var stepArrow: some View {
        Image(systemName: "chevron.compact.right")
            .font(.system(size: 14, weight: .semibold))
            .foregroundColor(Theme.textSecondary.opacity(0.6))
            .frame(width: 10)
            .accessibilityHidden(true)
    }

    /// 一张卡片：标题 + 两行内容；整张可点开对应面板。
    private func tile<Content: View>(
        step: Int, title: String, enabled: Bool, action: @escaping () -> Void, @ViewBuilder content: () -> Content
    ) -> some View {
        // 用 Button 而不是 onTapGesture：按下有反馈，读屏 / 辅助功能也能激活
        Button(action: action) {
            tileBody(step: step, title: title, trailingIcon: enabled ? "chevron.right" : nil, content: content)
        }
        .buttonStyle(TilePressStyle())
        .disabled(!enabled)
    }

    /// 卡片外观。最后一步（行业）用主题色描边，作为落点；trailingIcon 标出点了会怎样（打开面板 / 下拉选择）。
    private func tileBody<Content: View>(
        step: Int, title: String, trailingIcon: String?, @ViewBuilder content: () -> Content
    ) -> some View {
        let isLast = step == 2
        return VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 2) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundColor(Theme.textSecondary)
                    .lineLimit(1)
                Spacer(minLength: 0)
                if let trailingIcon {
                    Image(systemName: trailingIcon)
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundColor(Theme.textSecondary.opacity(0.7))
                }
            }
            VStack(alignment: .leading, spacing: 3) { content() }
                .lineLimit(1)
                .frame(maxWidth: .infinity, alignment: .leading)
                .frame(height: MarketHeader.tileContentHeight, alignment: .topLeading)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12)
            .stroke(isLast ? Theme.accent.opacity(0.55) : Theme.border, lineWidth: 1))
        .contentShape(Rectangle())
    }

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
