import SwiftUI

/// 图表当前可见的那一段 K 线。
///
/// 本来是 `ChanChartView` 内部的两个 @State，显式化是为了让窗口可被外部驱动。
/// 原先的消费方（精排分享卡的离屏渲染）已随该方案删除，这三个参数目前无外部
/// 调用方 —— 保留是给未来「复现用户此刻所见窗口」的渲染需求留的口子。
struct ChartWindow: Equatable {
    /// 窗口左边缘的 K 线下标（可为小数，平移时连续变化）。
    var firstVisible: Double
    /// 窗口内可见的 K 线根数。
    var visibleCount: Double
}

/// 缠论主图表：K 线 + 缠论结构叠加 + MACD 副图。
///
/// 采用原生 Canvas 逐帧绘制，固定窗口显示最新数据。
struct ChanChartView: View {
    let analysis: ChanAnalysis
    @ObservedObject var vm: ChanViewModel

    /// 初始可见窗口。nil = 用默认值（最新约 60 根）。当前无调用方传入，
    /// 见类型注释 —— 保留给未来的外部驱动场景。
    var initialWindow: ChartWindow? = nil

    /// 是否响应手势。false = 不挂手势、不画十字光标。
    var interactive: Bool = true

    /// 窗口变化时回调（平移/缩放结束时触发一次，不在 onChanged 里刷）。
    var onWindowChange: ((ChartWindow) -> Void)? = nil

    /// 次级别下钻区间的起点（K 线时间，含）：从这根到最新用浅色底标出。nil = 不标。
    var highlightFrom: String? = nil

    /// 全屏入口：非 nil 时在主图左上角放全屏按钮（十字光标激活时让位给光标详情）。
    var onFullscreen: (() -> Void)? = nil

    /// 显式 init 只为一件事：把 `initialWindow` 灌进 @State 的**初始值**。
    ///
    /// 光靠 onAppear 里赋值不够 —— 离屏渲染不保证触发 onAppear，
    /// @State 会停在字面初始值（firstVisible = 0，即最老的 60 根）。
    init(analysis: ChanAnalysis,
         vm: ChanViewModel,
         initialWindow: ChartWindow? = nil,
         interactive: Bool = true,
         priceHeight: CGFloat = 240,
         macdHeight: CGFloat = 78,
         showsMACD: Bool = true,
         highlightFrom: String? = nil,
         onFullscreen: (() -> Void)? = nil,
         onWindowChange: ((ChartWindow) -> Void)? = nil) {
        self.analysis = analysis
        _vm = ObservedObject(wrappedValue: vm)
        self.initialWindow = initialWindow
        self.interactive = interactive
        self.priceHeight = priceHeight
        self.macdHeight = macdHeight
        self.showsMACD = showsMACD
        self.onWindowChange = onWindowChange
        self.highlightFrom = highlightFrom
        self.onFullscreen = onFullscreen
        _firstVisible = State(initialValue: initialWindow?.firstVisible ?? 0)
        _visibleCount = State(initialValue: initialWindow?.visibleCount ?? 60)
    }

    // 可见窗口：起始下标（可为小数）与可见根数。
    // 默认少显示一些根数，让单根蜡烛更宽、更接近富途那种清晰的看盘密度。
    @State private var firstVisible: Double = 0
    @State private var visibleCount: Double = 60

    // 拖动手势的基准值
    @State private var dragAnchor: Double? = nil

    // 光标：选中的 K 线索引（nil = 不显示）
    @State private var cursorIndex: Int? = nil
    /// 点中的缠论元素（弹出说明卡片，并在图上高亮）。
    @State private var selectedElement: ChartElement? = nil
    @State private var cursorDragging: Bool = false

    // 双指缩放基准值
    @State private var zoomAnchor: Double? = nil

    /// 本次拖动是否已判定为「横向平移图表」。第一次移动时按主方向定死，之后不再翻转，
    /// 避免拖到一半在平移和滚动之间来回横跳。nil = 尚未判定。
    @State private var panIsHorizontal: Bool? = nil

    /// 橡皮筋：滑到头后继续拖时，内容跟手位移的像素量（带阻尼），松手回弹到 0。
    /// 只作用于按时间定位的内容（蜡烛/笔/中枢/信号/时间轴），右轴刻度与价签不跟随。
    @State private var rubberOffset: CGFloat = 0
    @State private var rubberTimer: Timer? = nil

    /// 惯性滑动（甩动）：松手后按系统预测落点继续减速平移，撞边界转橡皮筋回弹。
    @State private var momentumTimer: Timer? = nil

    /// 主图与副图高度。全屏页要把图撑满整屏，所以做成可传入的参数；
    /// 写死 300 的时候点全屏只是换了个黑底，图一样大，等于没有全屏。
    // 主图偏矮，整体呈横向长方形（宽 ≈ 屏宽，明显大于高），看盘视觉更舒展
    var priceHeight: CGFloat = 240
    var macdHeight: CGFloat = 78
    /// 是否画 MACD 副图（详情页竖屏、全屏都画；背驰的 b / c 两段在副图上用粉色底标出）。
    var showsMACD = true
    private let timeAxisHeight: CGFloat = 22
    // 右轴不再预留固定列：K 线铺满整宽，价格刻度以透明浮层画在右边缘、不遮挡蜡烛。
    private let rightAxisWidth: CGFloat = 0
    // 浮层价签宽度（末价/光标价签贴右边缘绘制时用）。
    private let priceTagWidth: CGFloat = 46

    private var candles: [MergedCandle] { analysis.mergedCandles }

    var body: some View {
        VStack(spacing: 0) {
            priceChart
            // MACD 副图供对照（趋势背驰用它的红绿柱面积判定，结果标在主图上）
            if showsMACD, analysis.macd != nil {
                Divider().background(Theme.border)
                macdChart
            }
            Divider().background(Theme.border)
            timeAxis
        }
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .onAppear {
            resetWindow(honoringInitial: true)
            onWindowChange?(currentWindow)
        }
        .onChange(of: analysis.symbol) { _, _ in
            firstVisible = 0
            // 换标的时忽略 initialWindow：那是上一个标的的窗口，套到新数据上没有意义
            resetWindow(honoringInitial: false)
            // 换标的后清掉残留光标与橡皮筋
            cursorIndex = nil
            cursorDragging = false
            rubberTimer?.invalidate()
            momentumTimer?.invalidate()
            rubberOffset = 0
            onWindowChange?(currentWindow)
        }
    }

    // MARK: - 主图

    private var priceChart: some View {
        GeometryReader { geo in
            let plotWidth = geo.size.width - rightAxisWidth
            let range = visibleRange(plotWidth: plotWidth)
            let priceBounds = visiblePriceBounds(range: range)

            ZStack(alignment: .topLeading) {
                Canvas { ctx, size in
                    let plotW = size.width - rightAxisWidth
                    drawGrid(ctx, size: CGSize(width: plotW, height: size.height),
                             bounds: priceBounds)
                    drawHighlight(ctx, plotWidth: plotW, height: size.height, range: range)
                    drawVolume(ctx, plotWidth: plotW, height: size.height, range: range)
                    drawCandles(ctx, plotWidth: plotW, height: size.height,
                                range: range, bounds: priceBounds)
                    if vm.showPivots { drawPivots(ctx, plotWidth: plotW, height: size.height, range: range, bounds: priceBounds) }
                    if vm.showStrokes { drawStrokes(ctx, plotWidth: plotW, height: size.height, range: range, bounds: priceBounds) }
                    if vm.showDivergences { drawDivergences(ctx, plotWidth: plotW, height: size.height, range: range, bounds: priceBounds) }
                    if vm.showSegments { drawSegments(ctx, plotWidth: plotW, height: size.height, range: range, bounds: priceBounds) }
                    if vm.showFractals { drawFractals(ctx, plotWidth: plotW, height: size.height, range: range, bounds: priceBounds) }
                    if vm.showSignals { drawSignals(ctx, plotWidth: plotW, height: size.height, range: range, bounds: priceBounds) }
                    if let sel = selectedElement {
                        drawSelection(ctx, sel, plotWidth: plotW, height: size.height, range: range, bounds: priceBounds)
                    }
                    // 雷达快照锚点竖线：画在结构叠加层之上，避免被中枢/笔的色块盖住看不清
                    drawAnchorLine(ctx, plotWidth: plotW, height: size.height, range: range)
                    drawPriceAxis(ctx, size: size, bounds: priceBounds)
                    // 末价参考线（光标激活时让位给光标价签，避免右轴两个标签叠一起）
                    if cursorIndex == nil {
                        drawLastPrice(ctx, plotWidth: plotW, height: size.height, bounds: priceBounds)
                    }
                    // 十字光标
                    if let ci = cursorIndex, ci >= range.start, ci < range.end {
                        drawCursor(ctx, plotWidth: plotW, height: size.height,
                                   range: range, bounds: priceBounds, index: ci)
                    }
                }
            }
            .contentShape(Rectangle())
            // 全部用 simultaneousGesture：与外层 ScrollView 并存，互不抢占。
            // 横向拖动平移图表、纵向留给页面滚动、点按看十字光标、双指缩放；
            // 左边缘的系统「右滑返回」起点在图表左侧之外，不受影响。
            // including: 而不是 isEnabled:——后者是 iOS 18 才有的重载，本工程部署目标 17.0。
            .simultaneousGesture(inspectTap(plotWidth: plotWidth, hitHeight: priceHeight), including: gestureMask)
            .simultaneousGesture(panGesture(plotWidth: plotWidth), including: gestureMask)
            .simultaneousGesture(magnificationGesture(plotWidth: plotWidth), including: gestureMask)
            .sheet(item: $selectedElement) { element in
                ChartElementSheet(element: element)
                    .preferredColorScheme(.dark)
            }
            .overlay(alignment: .topLeading) {
                if let ci = cursorIndex, ci >= 0, ci < candles.count {
                    cursorDetail(index: ci)
                        .padding(6)
                        .background(Theme.surfaceAlt)
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                        .padding(8)
                        .allowsHitTesting(false)
                } else if let onFullscreen {
                    // 光标激活时让位给光标详情（同在左上角）；右上角留给价格轴与末价
                    fullscreenButton(onFullscreen)
                }
            }
        }
        .frame(height: priceHeight)
    }

    // MARK: - 副图（MACD）

    private var macdChart: some View {
        subChart { ctx, plotWidth, height, range in
            drawMACD(ctx, plotWidth: plotWidth, height: height, range: range)
        }
    }

    /// 副图容器：与主图共用可视窗口与手势，内容由 draw 决定。
    private func subChart(
        _ draw: @escaping (GraphicsContext, CGFloat, CGFloat, VisibleRange) -> Void
    ) -> some View {
        GeometryReader { geo in
            let plotWidth = geo.size.width - rightAxisWidth
            let range = visibleRange(plotWidth: plotWidth)
            Canvas { ctx, size in
                draw(ctx, size.width - rightAxisWidth, size.height, range)
            }
            // 副图与主图共用同一个可视窗口，手势也必须是同一套：手指落在 MACD 上
            // 拖不动、捏不动，用户会以为图卡住了（副图占了图表近三分之一高度，
            // 全屏页尤其容易落指在这里）。
            // 平移/缩放改的是 firstVisible / visibleCount，主副图同时跟着变；
            // 橡皮筋位移也已包含在共用的 x(for:range:) 里，两图不会错开。
            // contentShape 不能省：Canvas 只在绘制到的像素上响应命中，
            // 柱子之间的空隙会漏掉触摸。
            .contentShape(Rectangle())
            .simultaneousGesture(inspectTap(plotWidth: plotWidth), including: gestureMask)
            .simultaneousGesture(panGesture(plotWidth: plotWidth), including: gestureMask)
            .simultaneousGesture(magnificationGesture(plotWidth: plotWidth), including: gestureMask)
        }
        .frame(height: macdHeight)
    }

    // MARK: - 时间轴

    private var timeAxis: some View {
        GeometryReader { geo in
            let plotWidth = geo.size.width - rightAxisWidth
            let range = visibleRange(plotWidth: plotWidth)
            Canvas { ctx, size in
                drawTimeAxis(ctx, plotWidth: size.width - rightAxisWidth,
                             height: size.height, range: range)
            }
        }
        .frame(height: timeAxisHeight)
    }

    private func drawTimeAxis(_ ctx: GraphicsContext, plotWidth: CGFloat,
                              height: CGFloat, range: VisibleRange) {
        let count = range.end - range.start
        guard count > 0 else { return }
        // 根据可见根数决定标签数量；分钟线标签带时刻（"09/24 10:30"）更长，少画几个免得挤
        let isIntraday = candles.first?.time.contains(" ") ?? false
        let labelCount = min(isIntraday ? 4 : 6, count)
        guard labelCount > 0 else { return }
        let step = CGFloat(count) / CGFloat(labelCount)
        for i in 0..<labelCount {
            let idx = range.start + Int((CGFloat(i) * step).rounded())
            guard idx >= 0, idx < candles.count else { continue }
            let cx = x(for: idx, range: range)
            guard cx >= 0, cx <= plotWidth else { continue }
            let dateStr = formatTimeLabel(candles[idx].displayTime)
            let text = Text(dateStr)
                .font(.system(size: 9))
                .foregroundColor(Theme.textSecondary)
            ctx.draw(text, at: CGPoint(x: cx, y: height / 2), anchor: .center)
        }
    }

    /// 将 "2026-01-13" 格式化为 "01/13"；分钟线 "2026-01-13 10:30" 格式化为 "01/13 10:30"。
    private func formatTimeLabel(_ time: String) -> String {
        let halves = time.split(separator: " ")
        let parts = halves[0].split(separator: "-")
        guard parts.count >= 3 else { return time }
        let day = "\(parts[1])/\(parts[2])"
        return halves.count > 1 ? "\(day) \(halves[1])" : day
    }

    // MARK: - 可见窗口计算

    private struct VisibleRange {
        let start: Int
        let end: Int          // 不含
        let candleWidth: CGFloat
        let firstVisible: Double
    }

    private func visibleRange(plotWidth: CGFloat) -> VisibleRange {
        let count = max(10, min(Double(candles.count), visibleCount))
        let candleWidth = plotWidth / CGFloat(count)
        let first = max(0, min(firstVisible, Double(candles.count) - count))
        let start = max(0, Int(first.rounded(.down)))
        let end = min(candles.count, Int((first + count).rounded(.up)) + 1)
        return VisibleRange(start: start, end: end, candleWidth: candleWidth, firstVisible: first)
    }

    private func x(for index: Int, range: VisibleRange) -> CGFloat {
        // 叠加橡皮筋位移：滑到头继续拖时内容整体跟手偏移，松手回弹。
        (CGFloat(index) - CGFloat(range.firstVisible)) * range.candleWidth + range.candleWidth / 2 + rubberOffset
    }

    private func x(forIndex index: Double, range: VisibleRange) -> CGFloat {
        (CGFloat(index) - CGFloat(range.firstVisible)) * range.candleWidth + range.candleWidth / 2 + rubberOffset
    }

    private static let dayFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(secondsFromGMT: 0)
        return f
    }()

    /// 时间对应的 K 线下标（可为负的小数）：窗口内取精确下标；早于窗口第一根时按日历天数外推
    /// （用窗口内「每个自然日约几根 K 线」换算），用于把起点在可见区左侧之外的线段画到边缘。
    private func legIndex(_ time: String) -> Double? {
        if let i = timeIndex[time] { return Double(i) }
        let candles = analysis.mergedCandles
        guard candles.count > 1, let first = candles.first?.time, let last = candles.last?.time, time < first,
              let d0 = Self.dayFormatter.date(from: String(first.prefix(10))),
              let dl = Self.dayFormatter.date(from: String(last.prefix(10))),
              let d = Self.dayFormatter.date(from: String(time.prefix(10))), dl > d0 else { return nil }
        let barsPerDay = Double(candles.count - 1) / (dl.timeIntervalSince(d0) / 86400)
        return -(d0.timeIntervalSince(d) / 86400) * barsPerDay
    }

    private struct PriceBounds { let minP: Double; let maxP: Double }

    private func visiblePriceBounds(range: VisibleRange) -> PriceBounds {
        var lo = Double.greatestFiniteMagnitude
        var hi = -Double.greatestFiniteMagnitude
        for i in range.start..<min(range.end, candles.count) {
            lo = min(lo, candles[i].low)
            hi = max(hi, candles[i].high)
        }
        if lo > hi { return PriceBounds(minP: 0, maxP: 1) }
        // 保留原有上下各 12% 价差的标记留白。
        let dataSpan = hi - lo
        let midpoint = lo + dataSpan / 2
        // 日线纵轴至少覆盖中间价的 12%，避免窄幅行情被放大到几乎占满主图。
        // 最小跨度包含留白；大幅行情继续自适应，分钟线与周线保持原有比例。
        let minimumSpan = vm.freq == "daily" ? abs(midpoint) * 0.12 : 0
        let span = max(dataSpan * 1.24, minimumSpan)
        // 有量柱时向下扩出一截：量柱占主图底部 volumeShare，K 线最低点落在量柱区之上
        let volumePad = hasVolume ? span * 0.24 : 0
        // 左上角有全屏按钮时顶部略多留白，最高的 K 线与卖点标记不被按钮压住
        let topPad = onFullscreen != nil ? span * 0.10 : 0
        return PriceBounds(minP: midpoint - span / 2 - volumePad, maxP: midpoint + span / 2 + topPad)
    }

    private func y(for price: Double, height: CGFloat, bounds: PriceBounds) -> CGFloat {
        let span = bounds.maxP - bounds.minP
        guard span > 0 else { return height / 2 }
        let ratio = (price - bounds.minP) / span
        return height - CGFloat(ratio) * height
    }

    // 时间字符串 -> 下标
    private var timeIndex: [String: Int] {
        ChartIndexCache.shared.index(for: analysis)
    }

    /// 锚点日期对应的下标：exact 匹配不到时退回小于等于该日期的最近一根K线。
    ///
    /// anchorDate 不保证一定落在某根K线上——信号雷达免费预览锚定「上个月 1 号」是
    /// 自然日历日期，恰好是周末/节假日（非交易日）时精确匹配会失败，此时应显示
    /// 「那一天收盘时的状态」，即往前找最近的交易日，语义上与后端按日重建快照时
    /// 的 carry-forward 逻辑一致，而不是直接找不到就整个跳过定位/画线。
    private func anchorIndex(_ anchor: String) -> Int? {
        if let idx = timeIndex[anchor] { return idx }
        var result: Int?
        for (idx, c) in candles.enumerated() {
            if c.time > anchor { break }
            result = idx
        }
        return result
    }

    // MARK: - 绘制：网格与坐标轴

    private func drawGrid(_ ctx: GraphicsContext, size: CGSize, bounds: PriceBounds) {
        // 更淡的虚线网格：起分隔作用但不与蜡烛争视线（富途也是这种若隐若现的横线）
        let lines = 4
        for i in 0...lines {
            let yPos = size.height / CGFloat(lines) * CGFloat(i)
            var path = Path()
            path.move(to: CGPoint(x: 0, y: yPos))
            path.addLine(to: CGPoint(x: size.width, y: yPos))
            ctx.stroke(path, with: .color(Theme.border.opacity(0.28)),
                       style: StrokeStyle(lineWidth: 0.5, dash: [2, 3]))
        }
    }

    // MARK: - 绘制：末价参考线

    /// 最新收盘价的贯穿横线 + 右轴价签，颜色随当日涨跌。
    /// 富途最显眼的一条线，随时知道"现在多少钱、相对可视区在什么位置"。
    private func drawLastPrice(_ ctx: GraphicsContext, plotWidth: CGFloat, height: CGFloat,
                              bounds: PriceBounds) {
        guard let last = candles.last else { return }
        let cy = y(for: last.close, height: height, bounds: bounds)
        guard cy >= 0, cy <= height else { return }  // 末价被滚出可视价格区间时不画
        let color = last.isUp ? Theme.up : Theme.down

        var line = Path()
        line.move(to: CGPoint(x: 0, y: cy))
        line.addLine(to: CGPoint(x: plotWidth, y: cy))
        ctx.stroke(line, with: .color(color.opacity(0.6)),
                   style: StrokeStyle(lineWidth: 0.8, dash: [4, 3]))

        // 末价价签：贴右边缘浮在 K 线之上（右轴已无预留列）
        let labelH: CGFloat = 15
        let labelRect = CGRect(x: plotWidth - priceTagWidth, y: clampY(cy, height) - labelH / 2,
                               width: priceTagWidth, height: labelH)
        ctx.fill(Path(roundedRect: labelRect, cornerRadius: 3), with: .color(color))
        ctx.draw(Text(String(format: "%.2f", last.close))
                    .font(.system(size: 10, weight: .semibold)).foregroundColor(.white),
                 at: CGPoint(x: labelRect.midX, y: labelRect.midY), anchor: .center)
    }

    // MARK: - 绘制：雷达日期锚点竖线

    /// 从信号雷达点气泡进来时，在雷达那天画一条竖线（见 ChanViewModel.anchorDate），
    /// 让用户一眼看出分析对应的是雷达上正在看的哪一天，不用去猜。手动分析等其它入口
    /// anchorDate 为 nil，不画。
    private func drawAnchorLine(_ ctx: GraphicsContext, plotWidth: CGFloat, height: CGFloat,
                                range: VisibleRange) {
        guard let anchor = vm.anchorDate, let idx = anchorIndex(anchor), idx < range.end else { return }
        // 雷达日期之后的 K 线盖一层淡遮罩：那是雷达当时还看不到的「未来」，
        // 让人一眼分清哪段是雷达判断的依据、哪段是事后走势。锚点已滑出可视区左侧时
        // 整个可视区都属于「之后」，全盖。
        let maskStart = idx >= range.start ? x(for: idx, range: range) : 0
        if maskStart < plotWidth {
            ctx.fill(Path(CGRect(x: maskStart, y: 0, width: plotWidth - maskStart, height: height)),
                     with: .color(Color.black.opacity(0.28)))
        }
        guard idx >= range.start else { return }
        let cx = x(for: idx, range: range)
        var line = Path()
        line.move(to: CGPoint(x: cx, y: 0))
        line.addLine(to: CGPoint(x: cx, y: height))
        // 白色虚线：不占用任何结构图层的配色（线段/中枢/买卖点各有专属色），不会被误读成结构线
        ctx.stroke(line, with: .color(.white.opacity(0.85)),
                   style: StrokeStyle(lineWidth: 1.4, dash: [5, 3]))
        // 标签横向夹在图内，贴着左右边界时不截断
        let clampedX = min(max(cx, 24), plotWidth - 24)
        // 直接标具体日期（yyyy.MM.dd），比「雷达日期」更一眼看出是哪天
        ctx.draw(Text(String(anchor.prefix(10)).replacingOccurrences(of: "-", with: "."))
                    .font(.system(size: 9, weight: .bold)).foregroundColor(.white),
                 at: CGPoint(x: clampedX, y: 4), anchor: .top)
    }

    private func drawPriceAxis(_ ctx: GraphicsContext, size: CGSize, bounds: PriceBounds) {
        let lines = 4
        // 透明浮层：刻度文字右对齐贴右边缘，直接浮在 K 线之上、不占用横向空间。
        let axisX = size.width - 3
        for i in 0...lines {
            let price = bounds.maxP - (bounds.maxP - bounds.minP) / Double(lines) * Double(i)
            let yPos = size.height / CGFloat(lines) * CGFloat(i)
            let text = Text(String(format: "%.2f", price))
                .font(.system(size: 9))
                .foregroundColor(Theme.textSecondary)
            ctx.draw(text, at: CGPoint(x: axisX, y: clampY(yPos, size.height)), anchor: .trailing)
        }
    }

    private func clampY(_ y: CGFloat, _ h: CGFloat) -> CGFloat { min(max(y, 8), h - 8) }

    // MARK: - 绘制：K 线

    private func drawCandles(_ ctx: GraphicsContext, plotWidth: CGFloat, height: CGFloat,
                             range: VisibleRange, bounds: PriceBounds) {
        // 实体占列宽 ~72%，两侧留出细缝；影线随列宽收放但始终保持发丝级。
        let bodyWidth = max(1, range.candleWidth * 0.72)
        let wickWidth = max(0.8, min(1.4, range.candleWidth * 0.12))
        for i in range.start..<min(range.end, candles.count) {
            let c = candles[i]
            let cx = x(for: i, range: range)
            if cx < -bodyWidth || cx > plotWidth + bodyWidth { continue }
            let color = c.isUp ? Theme.up : Theme.down
            // 影线
            var wick = Path()
            wick.move(to: CGPoint(x: cx, y: y(for: c.high, height: height, bounds: bounds)))
            wick.addLine(to: CGPoint(x: cx, y: y(for: c.low, height: height, bounds: bounds)))
            ctx.stroke(wick, with: .color(color), lineWidth: wickWidth)
            // 实体：十字星（开≈收）时至少给 1pt 高度，否则整根蜡烛只剩影线
            let openY = y(for: c.open, height: height, bounds: bounds)
            let closeY = y(for: c.close, height: height, bounds: bounds)
            let top = min(openY, closeY)
            let bodyH = max(1, abs(openY - closeY))
            let rect = CGRect(x: cx - bodyWidth / 2, y: top, width: bodyWidth, height: bodyH)
            ctx.fill(Path(roundedRect: rect, cornerSize: CGSize(width: 1, height: 1)),
                     with: .color(color))
        }
    }

    // MARK: - 绘制：分型

    private func drawFractals(_ ctx: GraphicsContext, plotWidth: CGFloat, height: CGFloat,
                              range: VisibleRange, bounds: PriceBounds) {
        for f in analysis.fractals {
            guard let idx = timeIndex[f.time], idx >= range.start, idx < range.end else { continue }
            let cx = x(for: idx, range: range)
            let cy = y(for: f.price, height: height, bounds: bounds)
            let color = f.type == .top ? Theme.topFractal : Theme.bottomFractal
            let r: CGFloat = 3.2
            let dot = Path(ellipseIn: CGRect(x: cx - r, y: cy - r, width: r * 2, height: r * 2))
            ctx.fill(dot, with: .color(f.confirmed ? color : color.opacity(0.4)))
        }
    }

    // MARK: - 绘制：笔 / 线段

    private func drawStrokes(_ ctx: GraphicsContext, plotWidth: CGFloat, height: CGFloat,
                             range: VisibleRange, bounds: PriceBounds) {
        for s in analysis.strokes {
            drawConnector(ctx, startTime: s.startTime, endTime: s.endTime,
                          startPrice: s.startPrice, endPrice: s.endPrice,
                          height: height, range: range, bounds: bounds,
                          color: Theme.stroke, width: 1.4, dashed: !s.confirmed)
        }
    }

    private func drawSegments(_ ctx: GraphicsContext, plotWidth: CGFloat, height: CGFloat,
                              range: VisibleRange, bounds: PriceBounds) {
        for seg in analysis.segments {
            drawConnector(ctx, startTime: seg.startTime, endTime: seg.endTime,
                          startPrice: seg.startPrice, endPrice: seg.endPrice,
                          height: height, range: range, bounds: bounds,
                          color: Theme.segment, width: 2.4, dashed: !seg.confirmed)
        }
    }

    private func drawConnector(_ ctx: GraphicsContext, startTime: String, endTime: String,
                               startPrice: Double, endPrice: Double, height: CGFloat,
                               range: VisibleRange, bounds: PriceBounds,
                               color: Color, width: CGFloat, dashed: Bool) {
        guard let si = timeIndex[startTime], let ei = timeIndex[endTime] else { return }
        // 两端至少有一端落在可见区才画
        guard ei >= range.start, si < range.end else { return }
        let p1 = CGPoint(x: x(for: si, range: range), y: y(for: startPrice, height: height, bounds: bounds))
        let p2 = CGPoint(x: x(for: ei, range: range), y: y(for: endPrice, height: height, bounds: bounds))
        var path = Path()
        path.move(to: p1)
        path.addLine(to: p2)
        let style = StrokeStyle(lineWidth: width, lineCap: .round,
                                dash: dashed ? [4, 4] : [])
        ctx.stroke(path, with: .color(dashed ? color.opacity(0.7) : color), style: style)
    }

    // MARK: - 绘制：中枢

    private func drawPivots(_ ctx: GraphicsContext, plotWidth: CGFloat, height: CGFloat,
                            range: VisibleRange, bounds: PriceBounds) {
        // 只画线段级中枢 + 笔级中枢，笔级更透明避免喧宾夺主
        for p in analysis.segmentPivots { drawPivot(ctx, p, height: height, range: range, bounds: bounds, alpha: 0.20) }
        for p in analysis.strokePivots { drawPivot(ctx, p, height: height, range: range, bounds: bounds, alpha: 0.12) }
    }

    private func drawPivot(_ ctx: GraphicsContext, _ p: Pivot, height: CGFloat,
                           range: VisibleRange, bounds: PriceBounds, alpha: Double) {
        guard let si = timeIndex[p.startTime], let ei = timeIndex[p.endTime] else { return }
        guard ei >= range.start, si < range.end else { return }
        let x1 = x(for: si, range: range)
        let x2 = x(for: ei, range: range)
        let yTop = y(for: p.zg, height: height, bounds: bounds)
        let yBottom = y(for: p.zd, height: height, bounds: bounds)
        let rect = CGRect(x: x1, y: yTop, width: max(2, x2 - x1), height: max(1, yBottom - yTop))
        ctx.fill(Path(rect), with: .color(Theme.pivotFill.opacity(p.confirmed ? alpha : alpha * 0.5)))
        ctx.stroke(Path(rect), with: .color(Theme.pivotFill.opacity(0.6)),
                   style: StrokeStyle(lineWidth: 1, dash: p.confirmed ? [] : [3, 3]))
    }

    // MARK: - 绘制：买卖点

    /// 买卖点徽标的版面：绘制与选中高亮共用，保证高亮框正好套在徽标上。
    private struct SignalBadge {
        let signal: Signal
        let anchorX: CGFloat
        let rect: CGRect
        let text: GraphicsContext.ResolvedText
    }

    private func signalBadges(_ ctx: GraphicsContext, plotWidth: CGFloat, height: CGFloat,
                              range: VisibleRange, bounds: PriceBounds) -> [SignalBadge] {
        // 只取可见区内的信号，按 x 排序，用「相邻信号最小间距」判断是否会挤。
        // 用间距而非列宽：信号通常稀疏，60 根默认视图里也多半放得下完整标签；
        // 只有当两个信号靠得太近（< 完整药丸宽 ~28pt）才整体降级成数字徽标。
        let visible = analysis.chartSignals
            .compactMap { sig -> (Signal, CGFloat)? in
                guard let idx = timeIndex[sig.time], idx >= range.start, idx < range.end else { return nil }
                return (sig, x(for: idx, range: range))
            }
            .sorted { $0.1 < $1.1 }
        var minGap = CGFloat.greatestFiniteMagnitude
        for i in 1..<max(1, visible.count) {
            minGap = min(minGap, visible[i].1 - visible[i - 1].1)
        }
        // 密度自适应：够宽时用完整术语（一买/三卖…），太挤时缩成「买1/卖3」这种
        // 自解释短标签——比完整术语窄，又不用猜数字含义；完整解读仍在「买卖点」列表。
        let compact = minGap < 28

        return visible.map { sig, cx in
            let cy = y(for: sig.price, height: height, bounds: bounds)
            // 徽标文字：紧凑态用「买卖+类型末位数字」并跟随界面语言（中文买1/卖3、英文 B1/S3），
            // 完整态用后端已本地化的 label
            let n = String(sig.type.rawValue.suffix(1))
            let compactPrefix = Localized.language() == .english
                ? (sig.isBuy ? "B" : "S")
                : (sig.isBuy ? "买" : "卖")
            var text = compact ? compactPrefix + n : sig.label
            // 待确认候选前缀「待」，和已成立的买卖点（同样叫「卖 3」/ 三卖）一眼分开
            if sig.isCandidate { text = (Localized.language() == .english ? "? " : "待") + text }
            let resolved = ctx.resolve(
                Text(text).font(.system(size: 9, weight: .bold)).foregroundColor(.white))
            let textSize = resolved.measure(in: CGSize(width: 200, height: 40))
            // 药丸随文字自适应宽度（紧凑态因文字更短自然更窄）
            let padH: CGFloat = 5, padV: CGFloat = 2.5
            let badgeH = textSize.height + padV * 2
            let badgeW = textSize.width + padH * 2

            // 版面：蜡烛 →(间距7)→ 三角 →(贴着)→ 徽标。整体夹在可视区内。
            // 位置与点击判定共用同一个函数（上下左右都夹在可视区内），画在哪就点得到哪。
            let center = ChartHitResolver.badgeCenter(
                anchor: CGPoint(x: cx, y: cy), isBuy: sig.isBuy, plotWidth: plotWidth, height: height,
                badgeSize: CGSize(width: badgeW, height: badgeH))
            let rect = CGRect(x: center.x - badgeW / 2, y: center.y - badgeH / 2, width: badgeW, height: badgeH)
            return SignalBadge(signal: sig, anchorX: cx, rect: rect, text: resolved)
        }
    }

    private func drawSignals(_ ctx: GraphicsContext, plotWidth: CGFloat, height: CGFloat,
                             range: VisibleRange, bounds: PriceBounds) {
        for badge in signalBadges(ctx, plotWidth: plotWidth, height: height, range: range, bounds: bounds) {
            let sig = badge.signal
            let cx = badge.anchorX
            let badgeRect = badge.rect
            // 已确认 / 未确认同一纯色：半透明叠在深色底上会显得更暗，最近（多为未确认）的买卖点
            // 就比历史的「深一截」，与雷达气泡、列表圆点对不上。未确认由虚线末笔、列表图标与说明表达。
            let color = sig.isBuy ? Theme.up : Theme.down
            // 买点朝上画在价格下方，卖点朝下画在价格上方
            let dir: CGFloat = sig.isBuy ? 1 : -1
            let badgeH = badgeRect.height
            let midY = badgeRect.midY
            let tri = ChartHitResolver.badgeTriangle  // 指向蜡烛的小三角高度

            // 小三角（徽标朝蜡烛的一侧）；仍指向真实蜡烛位置（原始 cx，不受夹取影响）
            let triBase = midY - dir * badgeH / 2
            var arrow = Path()
            arrow.move(to: CGPoint(x: cx, y: triBase - dir * tri))
            arrow.addLine(to: CGPoint(x: cx - tri, y: triBase))
            arrow.addLine(to: CGPoint(x: cx + tri, y: triBase))
            arrow.closeSubpath()
            let pill = Path(roundedRect: badgeRect, cornerRadius: badgeH / 2)
            if sig.isCandidate {
                // 待确认候选（严格模式，最后一笔还在走、不算买卖点）：灰底 + 灰色虚线边框，文字前缀「待」。
                // 不再带买卖方向色：绿色虚线「卖 3」放在红色「买 1」旁边，会被读成又买又卖（APP 2026-09-01）
                ctx.fill(arrow, with: .color(Theme.textSecondary.opacity(0.6)))
                ctx.fill(pill, with: .color(Theme.textSecondary.opacity(0.35)))
                ctx.stroke(pill, with: .color(Theme.textSecondary), style: StrokeStyle(lineWidth: 1, dash: [3, 2]))
            } else {
                ctx.fill(arrow, with: .color(color))
                ctx.fill(pill, with: .color(color))
            }
            ctx.draw(badge.text, at: CGPoint(x: badgeRect.midX, y: badgeRect.midY), anchor: .center)

            drawEstablishedMark(ctx, signal: sig, fromX: cx, height: height, range: range, bounds: bounds, color: color)
        }
    }

    /// 成立日标记的圆点位置：徽标画在所属笔的极值 K 线上，但买卖点要等下一笔成形才成立（可能晚好几周，
    /// 如 AVGO 三卖：极值 09-22、成立 10-02）。成立日那根 K 线上什么都没有时，用户会以为「那天没有这个信号」。
    /// 所以从徽标价位水平向右拉一条细虚线，终点画一个小空心圆点并写「成立」——圆点所在的 K 线就是列表里的成立日。
    /// 绘制与点击命中共用这个位置。待确认候选没有成立日；成立日还没滚进可见区（或和极值同一天）时返回 nil。
    private func establishedPoint(_ sig: Signal, range: VisibleRange, height: CGFloat,
                                  bounds: PriceBounds) -> CGPoint? {
        guard !sig.isCandidate, let detected = sig.detectedTime, detected != sig.time,
              let si = timeIndex[sig.time], si >= range.start, si < range.end,
              let idx = timeIndex[detected], idx >= range.start, idx < range.end else { return nil }
        let endX = x(for: idx, range: range)
        guard endX > x(for: si, range: range) + 6 else { return nil }
        return CGPoint(x: endX, y: y(for: sig.price, height: height, bounds: bounds))
    }

    private func drawEstablishedMark(_ ctx: GraphicsContext, signal sig: Signal, fromX: CGFloat,
                                     height: CGFloat, range: VisibleRange, bounds: PriceBounds, color: Color) {
        guard let end = establishedPoint(sig, range: range, height: height, bounds: bounds) else { return }
        var line = Path()
        line.move(to: CGPoint(x: fromX, y: end.y))
        line.addLine(to: end)
        ctx.stroke(line, with: .color(color.opacity(0.55)), style: StrokeStyle(lineWidth: 1, dash: [2, 3]))
        let dot = Path(ellipseIn: CGRect(x: end.x - 3.5, y: end.y - 3.5, width: 7, height: 7))
        ctx.fill(dot, with: .color(Theme.background))
        ctx.stroke(dot, with: .color(color), style: StrokeStyle(lineWidth: 1.5))
        // 圆点旁写「成立」：只有虚线和圆点没人看得懂。字放在圆点左上方、线的上面，靠右的信号不会被价格轴裁掉。
        // 点圆点或这两个字都弹说明（见 hitTest）
        let label = ctx.resolve(Text(L("成立")).font(.system(size: 9, weight: .bold)).foregroundColor(color))
        ctx.draw(label, at: CGPoint(x: end.x - 2, y: end.y - 6), anchor: .bottomTrailing)
    }

    // MARK: - 绘制：次级别下钻区间

    /// 从 highlightFrom 到最新一根铺浅色底——在次级别弹出图里标出对应大级别最后一段的区间。
    private func drawHighlight(_ ctx: GraphicsContext, plotWidth: CGFloat, height: CGFloat, range: VisibleRange) {
        guard let from = highlightFrom,
              let start = candles.firstIndex(where: { $0.time >= from }) else { return }
        let x1 = max(0, x(for: start, range: range) - range.candleWidth / 2)
        let x2 = min(plotWidth, x(for: candles.count - 1, range: range) + range.candleWidth / 2)
        guard x2 > x1 else { return }
        ctx.fill(Path(CGRect(x: x1, y: 0, width: x2 - x1, height: height)),
                 with: .color(Theme.accent.opacity(0.10)))
    }

    // MARK: - 绘制：量柱（主图底部）

    /// 量柱占主图高度的比例。
    private let volumeShare: CGFloat = 0.18

    private var hasVolume: Bool {
        candles.contains { ($0.volume ?? 0) > 0 }
    }

    /// 主图底部的半透明量柱：与蜡烛同宽、红涨绿跌，高度相对可见区最大量。
    /// 先于蜡烛绘制，被价格压住时不抢视线。
    private func drawVolume(_ ctx: GraphicsContext, plotWidth: CGFloat, height: CGFloat, range: VisibleRange) {
        guard hasVolume else { return }
        let end = min(range.end, candles.count)
        guard range.start < end else { return }
        let maxVol = (range.start..<end).map { candles[$0].volume ?? 0 }.max() ?? 0
        guard maxVol > 0 else { return }
        let areaH = height * volumeShare
        let bodyWidth = max(1, range.candleWidth * 0.72)
        for i in range.start..<end {
            let c = candles[i]
            let cx = x(for: i, range: range)
            if cx < -bodyWidth || cx > plotWidth + bodyWidth { continue }
            let h = CGFloat((c.volume ?? 0) / maxVol) * areaH
            guard h > 0 else { continue }
            let rect = CGRect(x: cx - bodyWidth / 2, y: height - h, width: bodyWidth, height: h)
            ctx.fill(Path(rect), with: .color((c.isUp ? Theme.up : Theme.down).opacity(0.28)))
        }
    }

    // MARK: - 绘制：背驰标注

    /// 背驰直接标在主图（缠论原文：离开中枢的 c 段对两个中枢之间的 b 段，比 MACD 红绿柱面积，与一类买卖点同一口径）：
    /// 粉色细实线连起 b 段终点和 c 段终点，线中间标「趋势背驰 0.52」（面积比）。与行情软件画背离的习惯一致
    /// （实线连两个高点/低点 + 方向文字）；不用虚线，虚线在本图里专指「未确认」。旧后端没有 b 段信息时，
    /// 退回「当前笔与前一个同向笔」的老画法。
    private func drawDivergences(_ ctx: GraphicsContext, plotWidth: CGFloat, height: CGFloat,
                                 range: VisibleRange, bounds: PriceBounds) {
        let strokes = analysis.strokes
        for k in strokes.indices {
            let cur = strokes[k]
            guard cur.diverged == true, let ci = timeIndex[cur.endTime], ci >= range.start else { continue }
            let p2 = CGPoint(x: x(for: ci, range: range), y: y(for: cur.endPrice, height: height, bounds: bounds))
            var p1: CGPoint
            if let legs = cur.divergenceLegs {
                // 缠论原文：分别标出 b 段与 c 段；b 段淡一些，c 段（信号所在）实线，比值标在 c 段上。
                // 线段起点可能在可见区左侧之外（b 段常有几个月长）：按日历天数外推到窗口外，再裁到可见区内，
                // 不能因为起点不在窗口里就整条不画。
                func pt(_ t: String, _ price: Double) -> CGPoint? {
                    legIndex(t).map { CGPoint(x: x(forIndex: $0, range: range), y: y(for: price, height: height, bounds: bounds)) }
                }
                var drawn: [(CGPoint, CGPoint)] = []
                for (leg, alpha, w) in [(legs.b, 0.55, 1.6), (legs.c, 1.0, 2.0)] as [((t0: String, p0: Double, t1: String, p1: Double), Double, CGFloat)] {
                    guard let a0 = pt(leg.t0, leg.p0), let a1 = pt(leg.t1, leg.p1),
                          max(a0.x, a1.x) >= 0, min(a0.x, a1.x) <= plotWidth else { drawn.append((p2, p2)); continue }
                    let (c0, c1) = Self.clipSegment(a0, a1, toX: 0...plotWidth)
                    var l = Path()
                    l.move(to: c0)
                    l.addLine(to: c1)
                    ctx.stroke(l, with: .color(Theme.divergence.opacity(alpha)),
                               style: StrokeStyle(lineWidth: w, lineCap: .round))
                    for (orig, shown) in [(a0, c0), (a1, c1)] where orig.x == shown.x {
                        let r: CGFloat = 2.4
                        ctx.fill(Path(ellipseIn: CGRect(x: shown.x - r, y: shown.y - r, width: r * 2, height: r * 2)),
                                 with: .color(Theme.divergence.opacity(alpha)))
                    }
                    drawn.append((c0, c1))
                }
                if drawn[0].0 != drawn[0].1 {
                    let tagB = ctx.resolve(Text("b").font(.system(size: 9, weight: .semibold)).foregroundColor(Theme.divergence.opacity(0.8)))
                    ctx.draw(tagB, at: CGPoint(x: (drawn[0].0.x + drawn[0].1.x) / 2,
                                               y: (drawn[0].0.y + drawn[0].1.y) / 2 + (cur.direction == .up ? 9 : -9)), anchor: .center)
                }
                p1 = drawn[1].0
            } else if let ref = cur.divergenceRef(previous: k >= 2 ? strokes[k - 2] : nil),
                      let pi = timeIndex[ref.time], pi < range.end {
                p1 = CGPoint(x: x(for: pi, range: range), y: y(for: ref.price, height: height, bounds: bounds))
                var line = Path()
                line.move(to: p1)
                line.addLine(to: p2)
                ctx.stroke(line, with: .color(Theme.divergence),
                           style: StrokeStyle(lineWidth: 1.3, lineCap: .round))
                for pt in [p1, p2] {
                    let r: CGFloat = 2.6
                    ctx.fill(Path(ellipseIn: CGRect(x: pt.x - r, y: pt.y - r, width: r * 2, height: r * 2)),
                             with: .color(Theme.divergence))
                }
            } else {
                continue
            }

            // 标签放在虚线中点、朝外侧（顶背驰在线上方、底背驰在线下方），避开端点上的买卖点徽标
            let kind = cur.divergenceName
            let label = cur.divergenceRatioText.map { kind + " " + $0 } ?? kind
            let resolved = ctx.resolve(Text(label).font(.system(size: 9, weight: .semibold))
                                        .foregroundColor(Theme.divergence))
            let size = resolved.measure(in: CGSize(width: 200, height: 40))
            let dir: CGFloat = cur.direction == .up ? -1 : 1
            // b 段终点常在可见区左侧之外（线横跨整个中枢）：标签取线在可见区内那一截的中点，
            // 而不是两端点中点，否则标签贴在图边缘、还会压在 c 段终点的买卖点徽标上。
            let (vp1, vp2) = Self.clipSegment(p1, p2, toX: 0...plotWidth)
            let midY = clampY((vp1.y + vp2.y) / 2 + dir * (size.height / 2 + 5), height)
            let boxW = size.width + 6
            let boxX = min(max((vp1.x + vp2.x) / 2 - boxW / 2, 0), plotWidth - boxW)
            let box = CGRect(x: boxX, y: midY - size.height / 2 - 1,
                             width: boxW, height: size.height + 2)
            ctx.fill(Path(roundedRect: box, cornerRadius: 3), with: .color(Theme.surface.opacity(0.85)))
            ctx.draw(resolved, at: CGPoint(x: box.midX, y: box.midY), anchor: .center)
        }
    }

    /// 把线段裁到 x 区间内（按斜率插值 y）；整段在区间外时原样返回。
    static func clipSegment(_ a: CGPoint, _ b: CGPoint, toX r: ClosedRange<CGFloat>) -> (CGPoint, CGPoint) {
        guard a.x != b.x else { return (a, b) }
        func at(_ x: CGFloat) -> CGPoint {
            CGPoint(x: x, y: a.y + (b.y - a.y) * (x - a.x) / (b.x - a.x))
        }
        let (l, rt) = a.x <= b.x ? (a, b) : (b, a)
        guard rt.x >= r.lowerBound, l.x <= r.upperBound else { return (a, b) }
        let p = l.x < r.lowerBound ? at(r.lowerBound) : l
        let q = rt.x > r.upperBound ? at(r.upperBound) : rt
        return (p, q)
    }

    // MARK: - 绘制：MACD

    /// 把按原始 K 线算的 MACD 取成与合并 K 线一一对应（按合并 K 线的 `time` 查同一时刻的值）。
    /// 找不到对应时刻（理论上不会）时用前一根的值，保证数组长度 = 合并 K 线数。
    static func alignedMACD(_ macd: MACDData, to candles: [MergedCandle]) -> MACDData {
        var index: [String: Int] = [:]
        for (i, t) in macd.times.enumerated() { index[t] = i }
        var times: [String] = [], dif: [Double] = [], dea: [Double] = [], bar: [Double] = []
        for c in candles {
            if let i = index[c.time], i < macd.dif.count, i < macd.dea.count, i < macd.bar.count {
                dif.append(macd.dif[i]); dea.append(macd.dea[i]); bar.append(macd.bar[i])
            } else {
                dif.append(dif.last ?? 0); dea.append(dea.last ?? 0); bar.append(0)
            }
            times.append(c.time)
        }
        return MACDData(times: times, dif: dif, dea: dea, bar: bar)
    }

    private func drawMACD(_ ctx: GraphicsContext, plotWidth: CGFloat, height: CGFloat, range: VisibleRange) {
        guard let raw = analysis.macd else { return }
        // MACD 按原始 K 线算（点数比去包含后的合并 K 线多），必须按时间对到合并 K 线上再画：
        // 直接用同一个下标会越往右错位越多（603019 实测中段差约 3 个月）。口径与网页 ChanChart 一致。
        let macd = Self.alignedMACD(raw, to: candles)
        var lo = 0.0, hi = 0.0
        for i in range.start..<min(range.end, macd.bar.count) {
            lo = min(lo, min(macd.bar[i], min(macd.dif[i], macd.dea[i])))
            hi = max(hi, max(macd.bar[i], max(macd.dif[i], macd.dea[i])))
        }
        let span = max(hi - lo, 0.0001)
        func yv(_ v: Double) -> CGFloat { height - CGFloat((v - lo) / span) * height }
        let zeroY = yv(0)

        // 趋势背驰的 b 段、c 段：在副图上铺粉色底并标 b / c，比的就是这两段里同向柱子的面积
        for st in analysis.strokes where st.diverged == true {
            guard let legs = st.divergenceLegs else { continue }
            for (tag, leg, alpha) in [("b", legs.b, 0.10), ("c", legs.c, 0.18)] as [(String, (t0: String, p0: Double, t1: String, p1: Double), Double)] {
                guard let i0 = legIndex(leg.t0), let i1 = legIndex(leg.t1) else { continue }
                let x0 = max(0, x(forIndex: i0, range: range)), x1 = min(plotWidth, x(forIndex: i1, range: range))
                guard x1 > x0 else { continue }
                ctx.fill(Path(CGRect(x: x0, y: 0, width: x1 - x0, height: height)),
                         with: .color(Theme.divergence.opacity(alpha)))
                let t = ctx.resolve(Text(tag).font(.system(size: 9, weight: .semibold)).foregroundColor(Theme.divergence))
                ctx.draw(t, at: CGPoint(x: (x0 + x1) / 2, y: 8), anchor: .center)
            }
        }
        // 柱
        let bw = max(1, range.candleWidth * 0.5)
        for i in range.start..<min(range.end, macd.bar.count) {
            let cx = x(for: i, range: range)
            if cx < 0 || cx > plotWidth { continue }
            let v = macd.bar[i]
            let color = v >= 0 ? Theme.up : Theme.down
            let top = min(zeroY, yv(v))
            let h = max(0.5, abs(yv(v) - zeroY))
            ctx.fill(Path(CGRect(x: cx - bw / 2, y: top, width: bw, height: h)),
                     with: .color(color.opacity(0.7)))
        }
        // DIF / DEA 线
        drawLineSeries(ctx, values: macd.dif, range: range, plotWidth: plotWidth, yv: yv, color: Theme.stroke)
        drawLineSeries(ctx, values: macd.dea, range: range, plotWidth: plotWidth, yv: yv, color: Theme.segment)
        // 光标竖线，与主图同一根 K 线对齐。样式跟 drawCursor 保持一致。
        // 只画竖线不画横线/价签：横线的纵坐标在主图是收盘价，在副图没有对应含义，
        // 数值统一由主图左上的详情框给出。
        if let ci = cursorIndex, ci >= range.start, ci < range.end {
            let cx = x(for: ci, range: range)
            if cx >= 0, cx <= plotWidth {
                var vLine = Path()
                vLine.move(to: CGPoint(x: cx, y: 0))
                vLine.addLine(to: CGPoint(x: cx, y: height))
                ctx.stroke(vLine, with: .color(Theme.textSecondary.opacity(0.4)),
                           style: StrokeStyle(lineWidth: 0.5, dash: [3, 3]))
            }
        }

        // 标签
        let tag = Text("MACD").font(.system(size: 8)).foregroundColor(Theme.textSecondary)
        ctx.draw(tag, at: CGPoint(x: 6, y: 8), anchor: .leading)
    }

    private func drawLineSeries(_ ctx: GraphicsContext, values: [Double], range: VisibleRange,
                                plotWidth: CGFloat, yv: (Double) -> CGFloat, color: Color) {
        var path = Path()
        var started = false
        for i in range.start..<min(range.end, values.count) {
            let cx = x(for: i, range: range)
            let pt = CGPoint(x: cx, y: yv(values[i]))
            if started { path.addLine(to: pt) } else { path.move(to: pt); started = true }
        }
        ctx.stroke(path, with: .color(color), lineWidth: 1)
    }

    // MARK: - 手势

    /// 点按看十字光标。tap 不会拦截外层 ScrollView 的滚动。
    /// 再次点中当前已选中的那根 K 线 → 收起光标（自然的开/关切换）。
    /// 点按：主图（hitHeight 非 nil）先判定是否点中缠论元素——点中弹出说明卡片；
    /// 没点中或在副图上，切换十字光标。
    private func inspectTap(plotWidth: CGFloat, hitHeight: CGFloat? = nil) -> some Gesture {
        SpatialTapGesture()
            .onEnded { value in
                if let h = hitHeight,
                   let hit = hitTest(value.location, plotWidth: plotWidth, height: h) {
                    cursorIndex = nil
                    selectedElement = hit
                    return
                }
                let range = visibleRange(plotWidth: plotWidth)
                let rel = Double(value.location.x / range.candleWidth) + range.firstVisible
                let idx = max(0, min(candles.count - 1, Int(rel.rounded())))
                cursorIndex = (cursorIndex == idx) ? nil : idx
            }
    }

    // MARK: - 元素命中与高亮

    /// 点到线段 ab 的距离。
    private func distance(_ p: CGPoint, _ a: CGPoint, _ b: CGPoint) -> CGFloat {
        let dx = b.x - a.x, dy = b.y - a.y
        let len2 = dx * dx + dy * dy
        guard len2 > 0 else { return hypot(p.x - a.x, p.y - a.y) }
        let t = max(0, min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2))
        return hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy))
    }

    private func point(_ time: String, _ price: Double, range: VisibleRange, height: CGFloat,
                       bounds: PriceBounds) -> CGPoint? {
        guard let i = timeIndex[time] else { return nil }
        return CGPoint(x: x(for: i, range: range), y: y(for: price, height: height, bounds: bounds))
    }

    /// 命中判定：只看图例里打开的图层；按「买卖点徽标 > 分型 > 背驰 > 笔 > 线段 > 中枢」优先，
    /// 同一层取最近的。阈值按手指大小给（约 10–22pt）。
    private func hitTest(_ loc: CGPoint, plotWidth: CGFloat, height: CGFloat) -> ChartElement? {
        let range = visibleRange(plotWidth: plotWidth)
        let bounds = visiblePriceBounds(range: range)
        func pt(_ t: String, _ p: Double) -> CGPoint? { point(t, p, range: range, height: height, bounds: bounds) }

        // 买卖点徽标与分型圆点一起比距离，取视觉中心离手指最近的一个——以前固定「买卖点
        // 优先」，底分型圆点的命中区与下方买点徽标重叠，点圆点略下方就弹出买点说明。
        var nearby: [(ChartElement, CGFloat)] = []
        if vm.showSignals {
            for s in analysis.chartSignals {
                guard let p = pt(s.time, s.price) else { continue }
                let badge = ChartHitResolver.badgeCenter(
                    anchor: p, isBuy: s.isBuy, plotWidth: plotWidth, height: height,
                    badgeSize: ChartHitResolver.typicalBadgeSize)
                let dx = abs(loc.x - badge.x), dy = abs(loc.y - badge.y)
                if dx < 18, dy < 11 { nearby.append((.signal(s), hypot(dx, dy))) }
                // 分型图层关闭时端点上没有圆点，点端点也算点买卖点
                if !vm.showFractals {
                    let d = hypot(loc.x - p.x, loc.y - p.y)
                    if d < 12 { nearby.append((.signal(s), d)) }
                }
            }
        }
        // 成立日标记（圆点 + 「成立」两个字）：和徽标一样可点，弹出为什么成立日比徽标晚
        if vm.showSignals {
            for s in analysis.chartSignals {
                guard let e = establishedPoint(s, range: range, height: height, bounds: bounds) else { continue }
                let d = hypot(loc.x - e.x, loc.y - e.y)
                let labelRect = CGRect(x: e.x - 30, y: e.y - 22, width: 32, height: 18)
                if d < 14 {
                    nearby.append((.established(s), d))
                } else if labelRect.contains(loc) {
                    nearby.append((.established(s), hypot(loc.x - labelRect.midX, loc.y - labelRect.midY)))
                }
            }
        }
        // 分型先于背驰：背驰虚线两端就是分型点，点端点应出分型说明
        if vm.showFractals {
            for f in analysis.fractals {
                guard let p = pt(f.time, f.price) else { continue }
                let d = hypot(loc.x - p.x, loc.y - p.y)
                if d < 12 { nearby.append((.fractal(f), d)) }
            }
        }
        if let hit = ChartHitResolver.nearest(nearby) { return hit }
        let strokes = analysis.strokes
        if vm.showDivergences {
            var best: (ChartElement, CGFloat)?
            for k in strokes.indices where strokes[k].diverged == true {
                guard let ref = strokes[k].divergenceRef(previous: k >= 2 ? strokes[k - 2] : nil),
                      let a = pt(ref.time, ref.price),
                      let b = pt(strokes[k].endTime, strokes[k].endPrice) else { continue }
                var d = distance(loc, a, b)
                if let legs = strokes[k].divergenceLegs,
                   let b0 = pt(legs.b.t0, legs.b.p0), let b1 = pt(legs.b.t1, legs.b.p1),
                   let c0 = pt(legs.c.t0, legs.c.p0), let c1 = pt(legs.c.t1, legs.c.p1) {
                    d = min(distance(loc, b0, b1), distance(loc, c0, c1))
                }
                if d < 12, d < (best?.1 ?? .infinity) {
                    best = (.divergence(current: strokes[k], refTime: ref.time, refPrice: ref.price), d)
                }
            }
            if let best { return best.0 }
        }
        if vm.showStrokes {
            let hit = strokes.compactMap { s -> (Stroke, CGFloat)? in
                guard let a = pt(s.startTime, s.startPrice), let b = pt(s.endTime, s.endPrice) else { return nil }
                let d = distance(loc, a, b)
                return d < 10 ? (s, d) : nil
            }.min { $0.1 < $1.1 }
            if let (s, _) = hit { return .stroke(s) }
        }
        if vm.showSegments {
            let hit = analysis.segments.compactMap { s -> (Segment, CGFloat)? in
                guard let a = pt(s.startTime, s.startPrice), let b = pt(s.endTime, s.endPrice) else { return nil }
                let d = distance(loc, a, b)
                return d < 10 ? (s, d) : nil
            }.min { $0.1 < $1.1 }
            if let (s, _) = hit { return .segment(s) }
        }
        if vm.showPivots {
            // 线段级中枢更大，先看笔级（更小、更具体）
            for p in analysis.strokePivots + analysis.segmentPivots {
                guard let a = pt(p.startTime, p.zg), let b = pt(p.endTime, p.zd) else { continue }
                if CGRect(x: a.x, y: a.y, width: max(2, b.x - a.x), height: max(1, b.y - a.y)).contains(loc) {
                    return .pivot(p)
                }
            }
        }
        return nil
    }

    /// 选中元素的高亮：白色描边，让说明卡片说的是哪一个一目了然。
    private func drawSelection(_ ctx: GraphicsContext, _ e: ChartElement, plotWidth: CGFloat, height: CGFloat,
                               range: VisibleRange, bounds: PriceBounds) {
        func pt(_ t: String, _ p: Double) -> CGPoint? { point(t, p, range: range, height: height, bounds: bounds) }
        let glow = Color.white.opacity(0.9)
        func line(_ a: CGPoint?, _ b: CGPoint?, _ w: CGFloat) {
            guard let a, let b else { return }
            var path = Path(); path.move(to: a); path.addLine(to: b)
            ctx.stroke(path, with: .color(glow), style: StrokeStyle(lineWidth: w, lineCap: .round))
        }
        func ring(_ c: CGPoint?, _ r: CGFloat) {
            guard let c else { return }
            ctx.stroke(Path(ellipseIn: CGRect(x: c.x - r, y: c.y - r, width: r * 2, height: r * 2)),
                       with: .color(glow), lineWidth: 2)
        }
        switch e {
        case .fractal(let f): ring(pt(f.time, f.price), 7)
        case .stroke(let s): line(pt(s.startTime, s.startPrice), pt(s.endTime, s.endPrice), 3)
        case .segment(let s): line(pt(s.startTime, s.startPrice), pt(s.endTime, s.endPrice), 4)
        case .signal(let s):
            // 点的是徽标，高亮也套在徽标上（而不是笔端点），与手指位置一致
            if vm.showSignals,
               let badge = signalBadges(ctx, plotWidth: plotWidth, height: height, range: range, bounds: bounds)
                .first(where: { $0.signal.id == s.id }) {
                let r = badge.rect.insetBy(dx: -2, dy: -2)
                ctx.stroke(Path(roundedRect: r, cornerRadius: r.height / 2), with: .color(glow), lineWidth: 2)
            } else {
                ring(pt(s.time, s.price), 8)
            }
        case .established(let s): ring(establishedPoint(s, range: range, height: height, bounds: bounds), 9)
        case .divergence(let c, let refTime, let refPrice):
            if let legs = c.divergenceLegs {
                line(pt(legs.b.t0, legs.b.p0), pt(legs.b.t1, legs.b.p1), 2.5)
                line(pt(legs.c.t0, legs.c.p0), pt(legs.c.t1, legs.c.p1), 2.5)
            } else {
                line(pt(refTime, refPrice), pt(c.endTime, c.endPrice), 2.5)
            }
        case .pivot(let p):
            guard let a = pt(p.startTime, p.zg), let b = pt(p.endTime, p.zd) else { return }
            ctx.stroke(Path(CGRect(x: a.x, y: a.y, width: max(2, b.x - a.x), height: max(1, b.y - a.y))),
                       with: .color(glow), lineWidth: 2)
        }
    }

    /// 把手指横坐标换算成 K 线下标（光标定位/滑动共用）。
    private func candleIndex(atX locationX: CGFloat, plotWidth: CGFloat) -> Int {
        let range = visibleRange(plotWidth: plotWidth)
        let rel = Double((locationX - rubberOffset) / range.candleWidth) + range.firstVisible
        return max(0, min(candles.count - 1, Int(rel.rounded())))
    }

    /// iOS 风格橡皮筋阻尼：位移越大，跟手比例越小，越界感受得到「拉不动」的张力。
    private func rubberband(_ offset: CGFloat, dimension: CGFloat) -> CGFloat {
        guard dimension > 0 else { return 0 }
        let c: CGFloat = 0.55
        let sign: CGFloat = offset < 0 ? -1 : 1
        let x = abs(offset)
        return sign * (1 - 1 / (x / dimension * c + 1)) * dimension
    }

    /// 松手后把橡皮筋位移用 easeOut 在 ~0.3s 内衰减回 0。
    /// Canvas 是过程式绘制，withAnimation 不会给它补间，所以用定时器逐帧回弹。
    private func settleRubberBand() {
        rubberTimer?.invalidate()
        let start = rubberOffset
        guard abs(start) > 0.5 else { rubberOffset = 0; return }
        let startTime = Date()
        let duration = 0.3
        rubberTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 60.0, repeats: true) { t in
            let p = min(1, Date().timeIntervalSince(startTime) / duration)
            let e = 1 - pow(1 - p, 3)          // easeOutCubic
            rubberOffset = start * CGFloat(1 - e)
            if p >= 1 { rubberOffset = 0; t.invalidate() }
        }
    }

    /// 惯性滑动：松手后由 `deltaCandles`（系统预测还会滑过的 K 线数）驱动，
    /// easeOut 减速到落点；中途撞到边界则按撞击速度甩出一段橡皮筋再回弹。
    private func startMomentum(deltaCandles: Double, plotWidth: CGFloat) {
        momentumTimer?.invalidate()
        let count = max(10, min(Double(candles.count), visibleCount))
        let maxFirst = max(0, Double(candles.count) - count)
        let start = firstVisible
        let target = start + deltaCandles
        let cw = visibleRange(plotWidth: plotWidth).candleWidth
        // 时长随甩动距离，夹在 0.25~0.7s
        let dur = min(0.7, max(0.25, abs(deltaCandles) / 45.0 + 0.2))
        let startTime = Date()
        var lastPos = start
        momentumTimer = Timer.scheduledTimer(withTimeInterval: 1.0 / 60.0, repeats: true) { t in
            let p = min(1, Date().timeIntervalSince(startTime) / dur)
            let e = 1 - pow(1 - p, 3)          // easeOutCubic 减速
            let pos = start + (target - start) * e
            let clamped = min(max(pos, 0), maxFirst)
            firstVisible = clamped
            if pos != clamped {
                // 撞边界：按撞击速度甩出一段橡皮筋，随后回弹
                let speed = abs(pos - lastPos)                 // 每帧 K 线数
                let kick = min(plotWidth * 0.5, CGFloat(speed) * cw * 6)
                rubberOffset = rubberband(pos < 0 ? kick : -kick, dimension: plotWidth)
                t.invalidate(); momentumTimer = nil
                settleRubberBand()
                onWindowChange?(currentWindow)
                return
            }
            lastPos = pos
            if p >= 1 {
                t.invalidate(); momentumTimer = nil
                // 惯性停下来，窗口才算定下来，这时才上报给调用方（分享用）
                onWindowChange?(currentWindow)
            }
        }
    }

    /// 横向拖动平移图表；纵向拖动放行给页面滚动。
    ///
    /// 用 simultaneousGesture + 首次移动定方向：第一帧就判定主方向，横向才平移、
    /// 纵向则整段忽略（此时 ScrollView 照常竖滚）。minimumDistance 给一点，避免点按
    /// 被当成拖动，也让左边缘的系统返回手势有机会先接管。
    private func panGesture(plotWidth: CGFloat) -> some Gesture {
        DragGesture(minimumDistance: 8)
            .onChanged { value in
                if panIsHorizontal == nil {
                    panIsHorizontal = abs(value.translation.width) > abs(value.translation.height)
                }
                guard panIsHorizontal == true else { return }  // 纵向：交给页面滚动

                // 光标已激活：横向拖动 = 移动光标到手指所在的 K 线（不再平移图表）
                if cursorIndex != nil {
                    cursorDragging = true
                    cursorIndex = candleIndex(atX: value.location.x, plotWidth: plotWidth)
                    return
                }

                // 否则：平移图表，滑到头进入橡皮筋
                cursorDragging = true
                rubberTimer?.invalidate()
                momentumTimer?.invalidate()   // 新的拖动打断上一次惯性滑动
                let range = visibleRange(plotWidth: plotWidth)
                if dragAnchor == nil { dragAnchor = firstVisible }
                let count = max(10, min(Double(candles.count), visibleCount))
                let maxFirst = max(0, Double(candles.count) - count)
                let deltaCandles = Double(-value.translation.width / range.candleWidth)
                let target = (dragAnchor ?? firstVisible) + deltaCandles
                let clamped = min(max(target, 0), maxFirst)
                firstVisible = clamped
                // 越界量（K 线单位）转成像素并加阻尼；越左 target<0 → 内容右移露白，反之亦然。
                let over = target - clamped
                rubberOffset = over == 0 ? 0
                    : rubberband(-CGFloat(over) * range.candleWidth, dimension: plotWidth)
            }
            .onEnded { value in
                dragAnchor = nil
                cursorDragging = false
                let wasHorizontal = panIsHorizontal == true
                panIsHorizontal = nil
                // 光标态 / 非横向：不做惯性
                guard cursorIndex == nil, wasHorizontal else {
                    settleRubberBand()
                    onWindowChange?(currentWindow)
                    return
                }
                // 已在橡皮筋越界中：直接回弹，不叠加惯性
                if abs(rubberOffset) > 1 {
                    settleRubberBand()
                    onWindowChange?(currentWindow)
                    return
                }
                // 用系统预测落点得到「还会再滑过多少根 K 线」，据此做惯性减速
                let cw = visibleRange(plotWidth: plotWidth).candleWidth
                let predictedExtra = value.predictedEndTranslation.width - value.translation.width
                let extraCandles = Double(-predictedExtra / cw)
                if abs(extraCandles) > 0.8 {
                    // 惯性还会继续改窗口，此刻上报的位置是过时的；
                    // 回调挪到 startMomentum 停下来时发，否则分享图会是甩动前那一段。
                    startMomentum(deltaCandles: extraCandles, plotWidth: plotWidth)
                } else {
                    settleRubberBand()
                    onWindowChange?(currentWindow)
                }
            }
    }

    /// 双指缩放：放大=减少可见 K 线数量，缩小=增加。
    private func magnificationGesture(plotWidth: CGFloat) -> some Gesture {
        MagnificationGesture()
            .onChanged { scale in
                if zoomAnchor == nil { zoomAnchor = visibleCount; momentumTimer?.invalidate(); rubberTimer?.invalidate(); rubberOffset = 0 }
                let base = zoomAnchor ?? visibleCount
                let newCount = max(15, min(Double(candles.count), base / scale))
                // 保持视图中心不变
                let oldCenter = firstVisible + visibleCount / 2
                visibleCount = newCount
                firstVisible = max(0, min(oldCenter - newCount / 2,
                                          Double(candles.count) - newCount))
            }
            .onEnded { _ in
                zoomAnchor = nil
                onWindowChange?(currentWindow)
            }
    }

    // MARK: - 光标绘制

    private func drawCursor(_ ctx: GraphicsContext, plotWidth: CGFloat, height: CGFloat,
                            range: VisibleRange, bounds: PriceBounds, index: Int) {
        let cx = x(for: index, range: range)
        guard cx >= 0, cx <= plotWidth else { return }
        let c = candles[index]

        // 竖线
        var vLine = Path()
        vLine.move(to: CGPoint(x: cx, y: 0))
        vLine.addLine(to: CGPoint(x: cx, y: height))
        ctx.stroke(vLine, with: .color(Theme.textSecondary.opacity(0.4)), style:StrokeStyle(lineWidth: 0.5, dash: [3, 3]))

        // 横线（在收盘价位置）
        let cy = y(for: c.close, height: height, bounds: bounds)
        var hLine = Path()
        hLine.move(to: CGPoint(x: 0, y: cy))
        hLine.addLine(to: CGPoint(x: plotWidth, y: cy))
        ctx.stroke(hLine, with: .color(Theme.textSecondary.opacity(0.4)), style: StrokeStyle(lineWidth: 0.5, dash: [3, 3]))

        // 高亮选中 K 线柱体
        let bodyWidth = max(1, range.candleWidth * 0.6)
        let rect = CGRect(x: cx - range.candleWidth / 2, y: 0, width: range.candleWidth, height: height)
        ctx.fill(Path(rect), with: .color(Theme.accent.opacity(0.06)))

        // 价格标签：贴右边缘浮在 K 线之上（右轴已无预留列）
        let labelText = Text(String(format: "%.2f", c.close))
            .font(.system(size: 10, weight: .semibold))
            .foregroundColor(.white)
        let labelW: CGFloat = priceTagWidth
        let labelH: CGFloat = 14
        let labelRect = CGRect(x: plotWidth - labelW, y: clampY(cy, height) - labelH / 2, width: labelW, height: labelH)
        ctx.fill(Path(labelRect), with: .color(Theme.accent))
        ctx.draw(labelText, at: CGPoint(x: labelRect.midX, y: labelRect.midY), anchor: .center)
    }

    // MARK: - 全屏按钮

    private func fullscreenButton(_ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: "arrow.up.left.and.arrow.down.right")
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(Theme.accent)
                .frame(width: 24, height: 24)
                .background(Theme.surfaceAlt.opacity(0.85), in: Circle())
                // 视觉尺寸缩小，点击区域仍保留 44pt。
                .frame(width: 44, height: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        // 纯图标按钮必须给 label，否则 VoiceOver 只会念出「按钮」
        .accessibilityLabel(L("全屏查看图表"))
        .accessibilityHint(L("横屏显示，可看到更多 K 线"))
    }

    // MARK: - 光标详情浮层

    private func cursorDetail(index: Int) -> some View {
        let c = candles[index]
        let change = c.open > 0 ? (c.close - c.open) / c.open * 100 : 0
        let changeColor = c.isUp ? Theme.up : Theme.down
        return VStack(alignment: .leading, spacing: 2) {
            // 多根合并成一根时标出起止，看得出今天被并进了前一根（不是缺数据）
            Text(c.displayTime == c.time ? c.time : "\(c.time) ~ \(c.displayTime)")
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(Theme.textSecondary)
            HStack(spacing: 8) {
                infoText(L("开"), String(format: "%.2f", c.open))
                infoText(L("高"), String(format: "%.2f", c.high))
                infoText(L("低"), String(format: "%.2f", c.low))
                infoText(L("收"), String(format: "%.2f", c.close))
            }
            .font(.system(size: 10))
            HStack(spacing: 8) {
                Text(String(format: "%+.2f%%", change))
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(changeColor)
                if let v = c.volume, v > 0 {
                    infoText(L("量"), Self.formatVolume(v)).font(.system(size: 10))
                }
            }
        }
    }

    /// 成交量缩写：中文用万/亿，英文用 K/M/B。
    static func formatVolume(_ v: Double) -> String {
        if Localized.language() == .english {
            if v >= 1e9 { return String(format: "%.2fB", v / 1e9) }
            if v >= 1e6 { return String(format: "%.2fM", v / 1e6) }
            if v >= 1e3 { return String(format: "%.1fK", v / 1e3) }
            return String(format: "%.0f", v)
        }
        if v >= 1e8 { return String(format: "%.2f亿", v / 1e8) }
        if v >= 1e4 { return String(format: "%.1f万", v / 1e4) }
        return String(format: "%.0f", v)
    }

    private func infoText(_ label: String, _ value: String) -> some View {
        HStack(spacing: 2) {
            Text(label).foregroundColor(Theme.textSecondary)
            Text(value).foregroundColor(Theme.textPrimary)
        }
    }

    // MARK: - 窗口重置

    /// 手势开关。非交互模式（分享渲染）下整体屏蔽，光标也不会被点出来。
    private var gestureMask: GestureMask { interactive ? .all : .none }

    /// 当前窗口快照，回调给调用方保存。
    private var currentWindow: ChartWindow {
        ChartWindow(firstVisible: firstVisible, visibleCount: visibleCount)
    }

    private func resetWindow(honoringInitial: Bool) {
        // 调用方指定了窗口（分享渲染要复现用户看到的那一段）就用它，不要重置成最新
        if honoringInitial, let w = initialWindow {
            visibleCount = w.visibleCount
            firstVisible = w.firstVisible
            return
        }
        let total = Double(candles.count)
        // 默认约 60 根：蜡烛宽度适中、结构看得清，又不至于太少看不出趋势
        visibleCount = min(60, max(20, total))
        // 从雷达点进来：把雷达快照那天摆在可见窗口正中间，而不是像默认那样停在
        // 最新数据——不然用户点进来看到的是「今天」，不是气泡所在的那一天，
        // 容易误以为点错了标的。只在真正 onAppear（honoringInitial）时生效，
        // 换标的（.onChange(of: analysis.symbol)）走的是 honoringInitial: false，
        // 不会沿用上一个标的的锚点日期。
        if honoringInitial, let anchor = vm.anchorDate, let idx = anchorIndex(anchor) {
            firstVisible = max(0, min(Double(idx) - visibleCount / 2, total - visibleCount))
        } else {
            firstVisible = max(0, total - visibleCount)  // 默认显示最新
        }
    }
}

/// 缓存 time->index 映射，避免每帧重建（Canvas 会频繁重绘）。
final class ChartIndexCache {
    static let shared = ChartIndexCache()
    private var cachedSymbol: String?
    private var cachedCount: Int = -1
    private var map: [String: Int] = [:]

    func index(for analysis: ChanAnalysis) -> [String: Int] {
        if cachedSymbol == analysis.symbol && cachedCount == analysis.mergedCandles.count {
            return map
        }
        var m: [String: Int] = [:]
        // 存数组下标（绘制时按数组顺序定位 x），而非 c.idx
        for (pos, c) in analysis.mergedCandles.enumerated() { m[c.time] = pos }
        map = m
        cachedSymbol = analysis.symbol
        cachedCount = analysis.mergedCandles.count
        return m
    }
}
