import SwiftUI

/// 缠论主图表：K 线 + 缠论结构叠加 + MACD 副图。
///
/// 采用原生 Canvas 逐帧绘制，固定窗口显示最新数据。
struct ChanChartView: View {
    let analysis: ChanAnalysis
    @ObservedObject var vm: ChanViewModel

    // 可见窗口：起始下标（可为小数）与可见根数。
    // 默认少显示一些根数，让单根蜡烛更宽、更接近富途那种清晰的看盘密度。
    @State private var firstVisible: Double = 0
    @State private var visibleCount: Double = 60

    // 拖动手势的基准值
    @State private var dragAnchor: Double? = nil

    // 光标：选中的 K 线索引（nil = 不显示）
    @State private var cursorIndex: Int? = nil
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

    /// 主图与副图高度。全屏页要把图撑满整屏，所以做成可传入的参数；
    /// 写死 300 的时候点全屏只是换了个黑底，图一样大，等于没有全屏。
    // 主图偏矮，整体呈横向长方形（宽 ≈ 屏宽，明显大于高），看盘视觉更舒展
    var priceHeight: CGFloat = 240
    var macdHeight: CGFloat = 78
    private let timeAxisHeight: CGFloat = 22
    // 右轴不再预留固定列：K 线铺满整宽，价格刻度以透明浮层画在右边缘、不遮挡蜡烛。
    private let rightAxisWidth: CGFloat = 0
    // 浮层价签宽度（末价/光标价签贴右边缘绘制时用）。
    private let priceTagWidth: CGFloat = 46

    private var candles: [MergedCandle] { analysis.mergedCandles }

    var body: some View {
        VStack(spacing: 0) {
            priceChart
            if analysis.macd != nil {
                Divider().background(Theme.border)
                macdChart
            }
            Divider().background(Theme.border)
            timeAxis
        }
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .onAppear { resetWindowIfNeeded() }
        .onChange(of: analysis.symbol) { _, _ in
            firstVisible = 0
            resetWindowIfNeeded()
            // 换标的后清掉残留光标与橡皮筋
            cursorIndex = nil
            cursorDragging = false
            rubberTimer?.invalidate()
            rubberOffset = 0
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
                    drawCandles(ctx, plotWidth: plotW, height: size.height,
                                range: range, bounds: priceBounds)
                    if vm.showPivots { drawPivots(ctx, plotWidth: plotW, height: size.height, range: range, bounds: priceBounds) }
                    if vm.showStrokes { drawStrokes(ctx, plotWidth: plotW, height: size.height, range: range, bounds: priceBounds) }
                    if vm.showSegments { drawSegments(ctx, plotWidth: plotW, height: size.height, range: range, bounds: priceBounds) }
                    if vm.showFractals { drawFractals(ctx, plotWidth: plotW, height: size.height, range: range, bounds: priceBounds) }
                    if vm.showSignals { drawSignals(ctx, plotWidth: plotW, height: size.height, range: range, bounds: priceBounds) }
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
            .simultaneousGesture(inspectTap(plotWidth: plotWidth))
            .simultaneousGesture(panGesture(plotWidth: plotWidth))
            .simultaneousGesture(magnificationGesture(plotWidth: plotWidth))
            .overlay(alignment: .topLeading) {
                if let ci = cursorIndex, ci >= 0, ci < candles.count {
                    cursorDetail(index: ci)
                        .padding(6)
                        .background(Theme.surfaceAlt)
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                        .padding(8)
                        .allowsHitTesting(false)
                }
            }
        }
        .frame(height: priceHeight)
    }

    // MARK: - MACD 副图

    private var macdChart: some View {
        GeometryReader { geo in
            let plotWidth = geo.size.width - rightAxisWidth
            let range = visibleRange(plotWidth: plotWidth)
            Canvas { ctx, size in
                drawMACD(ctx, plotWidth: size.width - rightAxisWidth, height: size.height, range: range)
            }
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
        // 根据可见根数决定标签数量
        let labelCount = min(6, count)
        guard labelCount > 0 else { return }
        let step = CGFloat(count) / CGFloat(labelCount)
        for i in 0..<labelCount {
            let idx = range.start + Int((CGFloat(i) * step).rounded())
            guard idx >= 0, idx < candles.count else { continue }
            let cx = x(for: idx, range: range)
            guard cx >= 0, cx <= plotWidth else { continue }
            let dateStr = formatTimeLabel(candles[idx].time)
            let text = Text(dateStr)
                .font(.system(size: 9))
                .foregroundColor(Theme.textSecondary)
            ctx.draw(text, at: CGPoint(x: cx, y: height / 2), anchor: .center)
        }
    }

    /// 将 "2026-01-13" 格式化为 "01/13" 短日期标签。
    private func formatTimeLabel(_ time: String) -> String {
        let parts = time.split(separator: "-")
        guard parts.count >= 3 else { return time }
        return "\(parts[1])/\(parts[2])"
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

    private struct PriceBounds { let minP: Double; let maxP: Double }

    private func visiblePriceBounds(range: VisibleRange) -> PriceBounds {
        var lo = Double.greatestFiniteMagnitude
        var hi = -Double.greatestFiniteMagnitude
        for i in range.start..<min(range.end, candles.count) {
            lo = min(lo, candles[i].low)
            hi = max(hi, candles[i].high)
        }
        if lo > hi { return PriceBounds(minP: 0, maxP: 1) }
        // 12% 而不是 8%：买卖点标记要在价格上下各占约 30pt，留白太少会顶到边缘。
        // 夹取逻辑（drawSignals）是兜底，这里先给出自然的呼吸空间。
        let pad = (hi - lo) * 0.12
        return PriceBounds(minP: lo - pad, maxP: hi + pad)
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

    private func drawSignals(_ ctx: GraphicsContext, plotWidth: CGFloat, height: CGFloat,
                             range: VisibleRange, bounds: PriceBounds) {
        // 只取可见区内的信号，按 x 排序，用「相邻信号最小间距」判断是否会挤。
        // 用间距而非列宽：信号通常稀疏，60 根默认视图里也多半放得下完整标签；
        // 只有当两个信号靠得太近（< 完整药丸宽 ~28pt）才整体降级成数字徽标。
        let visible = analysis.signals
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

        for (sig, cx) in visible {
            let cy = y(for: sig.price, height: height, bounds: bounds)
            let color = sig.isBuy ? Theme.up : Theme.down
            let alpha: Double = sig.confirmed ? 1.0 : 0.5
            // 买点朝上画在价格下方，卖点朝下画在价格上方
            let dir: CGFloat = sig.isBuy ? 1 : -1

            // 徽标文字：紧凑态用「买1/卖3」（买卖+类型末位数字），完整态用中文标签
            let text = compact
                ? (sig.isBuy ? "买" : "卖") + String(sig.type.rawValue.suffix(1))
                : sig.label
            let resolved = ctx.resolve(
                Text(text).font(.system(size: 9, weight: .bold)).foregroundColor(.white))
            let textSize = resolved.measure(in: CGSize(width: 200, height: 40))
            // 药丸随文字自适应宽度（紧凑态因文字更短自然更窄）
            let padH: CGFloat = 5, padV: CGFloat = 2.5
            let badgeH = textSize.height + padV * 2
            let badgeW = textSize.width + padH * 2
            let tri: CGFloat = 4  // 指向蜡烛的小三角高度

            // 版面：蜡烛 →(间距7)→ 三角 →(贴着)→ 徽标。整体夹在可视区内。
            let gap: CGFloat = 7
            let span = gap + tri + badgeH
            let midY = min(max(cy + dir * (gap + tri + badgeH / 2), span), height - span)
            let badgeRect = CGRect(x: cx - badgeW / 2, y: midY - badgeH / 2, width: badgeW, height: badgeH)

            // 小三角（徽标朝蜡烛的一侧）
            let triBase = midY - dir * badgeH / 2
            var arrow = Path()
            arrow.move(to: CGPoint(x: cx, y: triBase - dir * tri))
            arrow.addLine(to: CGPoint(x: cx - tri, y: triBase))
            arrow.addLine(to: CGPoint(x: cx + tri, y: triBase))
            arrow.closeSubpath()
            ctx.fill(arrow, with: .color(color.opacity(alpha)))

            ctx.fill(Path(roundedRect: badgeRect, cornerRadius: badgeH / 2),
                     with: .color(color.opacity(alpha)))
            ctx.draw(resolved, at: CGPoint(x: badgeRect.midX, y: badgeRect.midY), anchor: .center)
        }
    }

    // MARK: - 绘制：MACD

    private func drawMACD(_ ctx: GraphicsContext, plotWidth: CGFloat, height: CGFloat, range: VisibleRange) {
        guard let macd = analysis.macd else { return }
        // 与主图对齐：MACD 的 times 与 merged_candles 一一对应
        var lo = 0.0, hi = 0.0
        for i in range.start..<min(range.end, macd.bar.count) {
            lo = min(lo, min(macd.bar[i], min(macd.dif[i], macd.dea[i])))
            hi = max(hi, max(macd.bar[i], max(macd.dif[i], macd.dea[i])))
        }
        let span = max(hi - lo, 0.0001)
        func yv(_ v: Double) -> CGFloat { height - CGFloat((v - lo) / span) * height }
        let zeroY = yv(0)

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
    private func inspectTap(plotWidth: CGFloat) -> some Gesture {
        SpatialTapGesture()
            .onEnded { value in
                let range = visibleRange(plotWidth: plotWidth)
                let rel = Double(value.location.x / range.candleWidth) + range.firstVisible
                let idx = max(0, min(candles.count - 1, Int(rel.rounded())))
                cursorIndex = (cursorIndex == idx) ? nil : idx
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
            .onEnded { _ in
                dragAnchor = nil
                cursorDragging = false
                panIsHorizontal = nil
                settleRubberBand()
            }
    }

    /// 双指缩放：放大=减少可见 K 线数量，缩小=增加。
    private func magnificationGesture(plotWidth: CGFloat) -> some Gesture {
        MagnificationGesture()
            .onChanged { scale in
                if zoomAnchor == nil { zoomAnchor = visibleCount }
                let base = zoomAnchor ?? visibleCount
                let newCount = max(15, min(Double(candles.count), base / scale))
                // 保持视图中心不变
                let oldCenter = firstVisible + visibleCount / 2
                visibleCount = newCount
                firstVisible = max(0, min(oldCenter - newCount / 2,
                                          Double(candles.count) - newCount))
            }
            .onEnded { _ in zoomAnchor = nil }
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

    // MARK: - 光标详情浮层

    private func cursorDetail(index: Int) -> some View {
        let c = candles[index]
        let change = c.open > 0 ? (c.close - c.open) / c.open * 100 : 0
        let changeColor = c.isUp ? Theme.up : Theme.down
        return VStack(alignment: .leading, spacing: 2) {
            Text(c.time)
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(Theme.textSecondary)
            HStack(spacing: 8) {
                infoText(L("开"), String(format: "%.2f", c.open))
                infoText(L("高"), String(format: "%.2f", c.high))
                infoText(L("低"), String(format: "%.2f", c.low))
                infoText(L("收"), String(format: "%.2f", c.close))
            }
            .font(.system(size: 10))
            HStack(spacing: 4) {
                Text(String(format: "%+.2f%%", change))
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(changeColor)
            }
        }
    }

    private func infoText(_ label: String, _ value: String) -> some View {
        HStack(spacing: 2) {
            Text(label).foregroundColor(Theme.textSecondary)
            Text(value).foregroundColor(Theme.textPrimary)
        }
    }

    // MARK: - 窗口重置

    private func resetWindowIfNeeded() {
        let total = Double(candles.count)
        // 默认约 60 根：蜡烛宽度适中、结构看得清，又不至于太少看不出趋势
        visibleCount = min(60, max(20, total))
        firstVisible = max(0, total - visibleCount)  // 默认显示最新
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
