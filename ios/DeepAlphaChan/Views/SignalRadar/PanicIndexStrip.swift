import Charts
import SwiftUI

/// 三地恐慌指数小卡片 + 市场选择合二为一：点哪张卡就切到哪个市场（驱动下面的信号雷达），
/// 三张卡本身永远同时可见，方便一眼对比三地情绪；选中的那张卡右上角多一个展开按钮，
/// 点开看近一年完整曲线。
struct PanicIndexStrip: View {
    @ObservedObject var radarVM: SignalRadarViewModel
    @ObservedObject var panicVM: PanicIndexViewModel

    @State private var expanded: StockMarket?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 8) {
                ForEach(StockMarket.allCases) { market in
                    tile(market)
                }
            }
            // 卡片本身"既展示数据又是市场切换器"这件事不明显，容易被当成纯信息卡——
            // 点一下才发现下面的信号雷达跟着变了市场。补一行提示说明这个副作用。
            Text(L("点击卡片切换市场"))
                .font(.system(size: 9))
                .foregroundColor(Theme.textSecondary)
        }
        .task { panicVM.onAppear() }
        .sheet(item: $expanded) { market in
            if let resp = panicVM.responses[market] {
                PanicIndexDetailSheet(market: market, response: resp)
            }
        }
    }

    private func tile(_ market: StockMarket) -> some View {
        let isSelected = radarVM.market == market
        let resp = panicVM.responses[market]

        return VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(market.title)
                    .font(.caption.weight(.semibold))
                    .foregroundColor(isSelected ? Theme.textPrimary : Theme.textSecondary)
                Spacer()
                if isSelected && resp != nil {
                    Button { expanded = market } label: {
                        Image(systemName: "arrow.up.left.and.arrow.down.right")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(Theme.textSecondary)
                    }
                    .accessibilityLabel(L("查看完整曲线"))
                }
            }

            // 三种状态共用分数行、间距和走势图的高度，避免异步响应挤动下方雷达。
            VStack(alignment: .leading, spacing: 6) {
                if let resp {
                    HStack(alignment: .firstTextBaseline, spacing: 3) {
                        Text("\(Int(resp.current.score.rounded()))")
                            .font(.system(size: 20, weight: .bold, design: .rounded))
                            .foregroundColor(PanicIndexStrip.ratingColor(resp.current.score))
                        Text(PanicIndexStrip.ratingLabel(resp.current.rating))
                            .font(.system(size: 10))
                            .foregroundColor(Theme.textSecondary)
                            .lineLimit(1)
                    }
                    .frame(height: 24)
                    sparkline(resp)
                } else if panicVM.failedMarkets.contains(market) {
                    Button { panicVM.retry(market) } label: {
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
            .frame(maxWidth: .infinity, alignment: .leading)
            .frame(height: 54, alignment: .leading)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(isSelected ? Theme.accent.opacity(0.12) : Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(isSelected ? Theme.accent : Theme.border, lineWidth: isSelected ? 1.5 : 1)
        )
        .contentShape(Rectangle())
        .onTapGesture { radarVM.switchMarket(market) }
    }

    /// 迷你走势图：只取近 60 个交易日（约 3 个月），隐藏坐标轴，纯粹给个「形状」。
    private func sparkline(_ resp: PanicIndexResponse) -> some View {
        let points = Array(resp.history.suffix(60))
        return Chart(points) { p in
            LineMark(x: .value("date", p.date), y: .value("score", p.score))
                .foregroundStyle(PanicIndexStrip.ratingColor(resp.current.score))
                .lineStyle(StrokeStyle(lineWidth: 1.5))
                .interpolationMethod(.catmullRom)
        }
        .chartYScale(domain: 0...100)
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
        .frame(height: 24)
    }

    /// 分数 → 颜色，5 个锚点对应五档中心（0-25 极度恐慌/25-45 恐慌/45-55 中性/
    /// 55-75 贪婪/75-100 极度贪婪的区间中点），锚点之间线性插值出连续渐变——
    /// 不是卡在几个色块之间突变，分数差 1 分颜色也只差一点点。
    /// 配色：绿=恐慌、灰=中性、红=贪婪，跟本 App 全局「涨=红/跌=绿」以及
    /// 网页端 `frontend/lib/constants/fearGreed.ts`（红色系=贪婪、绿色系=恐惧）
    /// 保持一致——此前 iOS 端反过来用的是国际通行的 CNN Fear & Greed 配色
    /// （红=恐慌/绿=贪婪），跟网页端对不上，是两端不一致，不是要在两种配色间
    /// 反复横跳；这次是把 iOS 对齐到网页端已经在用的口径，之后不要再改回
    /// CNN 那套。
    private static let ratingAnchors: [(pos: Double, r: Double, g: Double, b: Double)] = [
        (12.5, 20, 83, 45),      // 深绿：极度恐慌
        (35, 34, 197, 94),       // 绿：恐慌
        (50, 156, 163, 175),     // 灰色：中性
        (65, 220, 38, 38),       // 红：贪婪
        (87.5, 69, 10, 10),      // 乌红：极度贪婪
    ]

    static func ratingColor(_ score: Double) -> Color {
        let s = min(max(score, 0), 100)
        guard let first = ratingAnchors.first, let last = ratingAnchors.last else { return .gray }
        if s <= first.pos { return Color(.sRGB, red: first.r / 255, green: first.g / 255, blue: first.b / 255) }
        if s >= last.pos { return Color(.sRGB, red: last.r / 255, green: last.g / 255, blue: last.b / 255) }
        for i in 0..<(ratingAnchors.count - 1) {
            let a = ratingAnchors[i], b = ratingAnchors[i + 1]
            guard s >= a.pos && s <= b.pos else { continue }
            let t = (s - a.pos) / (b.pos - a.pos)
            return Color(
                .sRGB,
                red: (a.r + (b.r - a.r) * t) / 255,
                green: (a.g + (b.g - a.g) * t) / 255,
                blue: (a.b + (b.b - a.b) * t) / 255
            )
        }
        return Color(.sRGB, red: last.r / 255, green: last.g / 255, blue: last.b / 255)
    }

    static func ratingLabel(_ rating: String) -> String {
        switch rating {
        case "Extreme Fear": return L("极度恐慌")
        case "Fear": return L("恐慌")
        case "Neutral": return L("中性")
        case "Greed": return L("贪婪")
        case "Extreme Greed": return L("极度贪婪")
        default: return rating
        }
    }
}

/// 曲线上的一个可绘制点：把后端的日期字符串转成真正的 Date，
/// 才能让 Swift Charts 的横向滚动 / 取点手势按时间轴工作。
private struct PlotPoint: Identifiable {
    let date: Date
    let score: Double
    let rating: String
    let rawValue: Double?
    var id: Date { date }
}

/// 展开态：完整曲线（默认停在最近约 3 个月，可左右拖动回看更早）+ 点按看具体数值
/// + 当前/一周前/一月前快照。
private struct PanicIndexDetailSheet: View {
    let market: StockMarket
    let response: PanicIndexResponse

    @Environment(\.dismiss) private var dismiss
    /// 用 Apple 内置的 `chartXSelection` 而不是手写 chartOverlay + 手势：
    /// 后者不管是 .gesture 还是 .simultaneousGesture，一个盖住整个绘图区的
    /// Rectangle 手势识别器仍然会跟 chartScrollableAxes 内部的横向滚动手势抢
    /// 优先级，实测点开后完全划不动。chartXSelection 是苹果专门设计用来和
    /// 可滚动图表共存的取值手势，两者不冲突。
    @State private var selectedDate: Date?
    /// 日期解析 + Chart 建图的结果只算一次（见 `loadPoints`），而不是每次 `selected`
    /// 变化触发重绘时都重新跑一遍——A股/港股指数历史能有几千个交易日，之前用计算属性
    /// 导致每点一下图表就要重新解析全量日期，这才是"点开/点按都卡很久"的真正原因。
    @State private var points: [PlotPoint] = []
    @State private var isLoading = true

    /// 默认可视窗口长度：数据本身可能横跨十来年（A股/港股指数历史很长），
    /// 全塞进一屏只会挤成一条线看不出细节；限定窗口 + 可横向拖动回看更早。
    private let visibleDays: Double = 90

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    snapshotRow
                    if isLoading {
                        RoundedRectangle(cornerRadius: 12)
                            .fill(Theme.surface.opacity(0.4))
                            .frame(height: 240)
                            .overlay(ProgressView())
                    } else {
                        chart
                            .transition(.opacity)
                    }
                    Text(L("拖动图表查看更早历史，点按看某一天的具体分值。分数 0~100，越低越恐慌、越高越贪婪；按近一年区间分位数折算，三地口径统一可比。"))
                        .font(.caption2)
                        .foregroundColor(Theme.textSecondary)
                }
                .padding(16)
            }
            .background(Theme.background)
            .navigationTitle(response.label)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(L("关闭")) { dismiss() }
                }
            }
        }
        .task { await loadPoints() }
    }

    /// 在后台线程把整段历史一次性解析成 `PlotPoint`，避免在主线程阻塞 sheet 的展开动画。
    private func loadPoints() async {
        let history = response.history
        let parsed = await Task.detached(priority: .userInitiated) {
            let parser = DateFormatter()
            parser.dateFormat = "yyyy-MM-dd"
            parser.locale = Locale(identifier: "en_US_POSIX")
            parser.timeZone = TimeZone(identifier: "UTC")
            return history.compactMap { p -> PlotPoint? in
                guard let d = parser.date(from: p.date) else { return nil }
                return PlotPoint(date: d, score: p.score, rating: p.rating, rawValue: p.rawValue)
            }
        }.value
        withAnimation(.easeInOut(duration: 0.2)) {
            points = parsed
            isLoading = false
        }
    }

    private var snapshotRow: some View {
        HStack(spacing: 20) {
            snapshotItem(L("当前"), response.current)
            snapshotItem(L("一周前"), response.previousWeek)
            snapshotItem(L("一月前"), response.previousMonth)
        }
    }

    private func snapshotItem(_ title: String, _ snap: PanicIndexSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.caption2).foregroundColor(Theme.textSecondary)
            Text("\(Int(snap.score.rounded()))")
                .font(.title3.bold())
                .foregroundColor(PanicIndexStrip.ratingColor(snap.score))
            Text(PanicIndexStrip.ratingLabel(snap.rating))
                .font(.caption2)
                .foregroundColor(Theme.textSecondary)
        }
    }

    /// 取离手指最近的一个点——数据是不连续交易日，直接按 x 反查大概率落不到点上。
    private func nearest(to date: Date) -> PlotPoint? {
        points.min { abs($0.date.timeIntervalSince(date)) < abs($1.date.timeIntervalSince(date)) }
    }

    private var selected: PlotPoint? {
        guard let selectedDate else { return nil }
        return nearest(to: selectedDate)
    }

    /// 跟小卡片/迷你走势图用同一套恐慌-贪婪配色，不再是一条跟分数无关的蓝线——
    /// 之前展开大图和入口小卡片配色不统一，从花花绿绿的卡片点进来却看到素蓝线。
    private var lineColor: Color { PanicIndexStrip.ratingColor(response.current.score) }

    private var chart: some View {
        Chart {
            ForEach(points) { p in
                LineMark(x: .value(L("日期"), p.date), y: .value(L("分数"), p.score))
                    .foregroundStyle(lineColor)
                    .lineStyle(StrokeStyle(lineWidth: 1.5))
                    .interpolationMethod(.catmullRom)
                AreaMark(x: .value(L("日期"), p.date), y: .value(L("分数"), p.score))
                    .foregroundStyle(
                        LinearGradient(colors: [lineColor.opacity(0.22), lineColor.opacity(0.0)],
                                       startPoint: .top, endPoint: .bottom)
                    )
                    .interpolationMethod(.catmullRom)
            }
            if let selected {
                RuleMark(x: .value(L("日期"), selected.date))
                    .foregroundStyle(Theme.textSecondary.opacity(0.6))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
                PointMark(x: .value(L("日期"), selected.date), y: .value(L("分数"), selected.score))
                    .foregroundStyle(PanicIndexStrip.ratingColor(selected.score))
                    .symbolSize(70)
                    .annotation(position: .top, overflowResolution: .init(x: .fit, y: .fit)) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(selected.date, format: .dateTime.year().month().day())
                                .font(.caption2)
                                .foregroundColor(Theme.textSecondary)
                            HStack(spacing: 4) {
                                Text("\(Int(selected.score.rounded()))")
                                    .font(.subheadline.bold())
                                    .foregroundColor(PanicIndexStrip.ratingColor(selected.score))
                                Text(PanicIndexStrip.ratingLabel(selected.rating))
                                    .font(.caption2)
                                    .foregroundColor(Theme.textSecondary)
                            }
                        }
                        .padding(8)
                        .background(Theme.surfaceAlt)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Theme.border, lineWidth: 1))
                    }
            }
        }
        .chartYScale(domain: 0...100)
        .chartYAxis {
            AxisMarks(values: [0, 25, 45, 56, 76, 100]) {
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5, dash: [2, 3]))
                AxisValueLabel().font(.caption2).foregroundStyle(Theme.textSecondary)
            }
        }
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 4)) {
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                AxisValueLabel().font(.caption2).foregroundStyle(Theme.textSecondary)
            }
        }
        .chartScrollableAxes(.horizontal)
        .chartXVisibleDomain(length: visibleDays * 86400)
        .chartScrollPosition(initialX: points.last.map {
            $0.date.addingTimeInterval(-visibleDays * 86400)
        } ?? Date())
        .chartXSelection(value: $selectedDate)
        .frame(height: 240)
        .padding(.vertical, 8)
        .padding(.trailing, 8)
        .background(Theme.surface.opacity(0.4))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}
