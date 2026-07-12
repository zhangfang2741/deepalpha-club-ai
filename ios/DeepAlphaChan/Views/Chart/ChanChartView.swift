import SwiftUI

/// 缠论主图表：K 线 + 缠论结构叠加 + MACD 副图，支持双指缩放、拖动、十字光标。
///
/// 采用原生 Canvas 逐帧绘制，保证手势跟手、渲染丝滑。
struct ChanChartView: View {
    let analysis: ChanAnalysis
    @ObservedObject var vm: ChanViewModel

    // 可见窗口：起始下标（可为小数）与可见根数。
    @State private var firstVisible: Double = 0
    @State private var visibleCount: Double = 80

    // 缩放/拖动手势的基准值
    @State private var dragAnchor: Double? = nil
    @State private var zoomAnchor: Double? = nil

    // 十字光标选中的下标（nil 表示未选中）
    @State private var crosshairIndex: Int? = nil

    private let priceHeight: CGFloat = 300
    private let macdHeight: CGFloat = 110
    private let rightAxisWidth: CGFloat = 52

    private var candles: [MergedCandle] { analysis.mergedCandles }

    var body: some View {
        VStack(spacing: 0) {
            priceChart
            if analysis.macd != nil {
                Divider().background(Theme.border)
                macdChart
            }
        }
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .onAppear { resetWindowIfNeeded() }
        .onChange(of: analysis.symbol) { _, _ in
            firstVisible = 0
            crosshairIndex = nil
            resetWindowIfNeeded()
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
                    drawCrosshair(ctx, plotWidth: plotW, height: size.height, range: range, bounds: priceBounds)
                }
                crosshairInfo
            }
            .contentShape(Rectangle())
            .gesture(dragGesture(plotWidth: plotWidth))
            .gesture(magnifyGesture(plotWidth: plotWidth))
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
        (CGFloat(index) - CGFloat(range.firstVisible)) * range.candleWidth + range.candleWidth / 2
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
        let pad = (hi - lo) * 0.08
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
        let lines = 4
        for i in 0...lines {
            let yPos = size.height / CGFloat(lines) * CGFloat(i)
            var path = Path()
            path.move(to: CGPoint(x: 0, y: yPos))
            path.addLine(to: CGPoint(x: size.width, y: yPos))
            ctx.stroke(path, with: .color(Theme.border.opacity(0.4)), lineWidth: 0.5)
        }
    }

    private func drawPriceAxis(_ ctx: GraphicsContext, size: CGSize, bounds: PriceBounds) {
        let lines = 4
        let axisX = size.width - rightAxisWidth + 4
        for i in 0...lines {
            let price = bounds.maxP - (bounds.maxP - bounds.minP) / Double(lines) * Double(i)
            let yPos = size.height / CGFloat(lines) * CGFloat(i)
            let text = Text(String(format: "%.2f", price))
                .font(.system(size: 9))
                .foregroundColor(Theme.textSecondary)
            ctx.draw(text, at: CGPoint(x: axisX, y: clampY(yPos, size.height)), anchor: .leading)
        }
    }

    private func clampY(_ y: CGFloat, _ h: CGFloat) -> CGFloat { min(max(y, 8), h - 8) }

    // MARK: - 绘制：K 线

    private func drawCandles(_ ctx: GraphicsContext, plotWidth: CGFloat, height: CGFloat,
                             range: VisibleRange, bounds: PriceBounds) {
        let bodyWidth = max(1, range.candleWidth * 0.6)
        for i in range.start..<min(range.end, candles.count) {
            let c = candles[i]
            let cx = x(for: i, range: range)
            if cx < -bodyWidth || cx > plotWidth + bodyWidth { continue }
            let color = c.isUp ? Theme.up : Theme.down
            // 影线
            var wick = Path()
            wick.move(to: CGPoint(x: cx, y: y(for: c.high, height: height, bounds: bounds)))
            wick.addLine(to: CGPoint(x: cx, y: y(for: c.low, height: height, bounds: bounds)))
            ctx.stroke(wick, with: .color(color), lineWidth: 1)
            // 实体
            let openY = y(for: c.open, height: height, bounds: bounds)
            let closeY = y(for: c.close, height: height, bounds: bounds)
            let top = min(openY, closeY)
            let bodyH = max(1, abs(openY - closeY))
            let rect = CGRect(x: cx - bodyWidth / 2, y: top, width: bodyWidth, height: bodyH)
            ctx.fill(Path(rect), with: .color(color))
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
        for sig in analysis.signals {
            guard let idx = timeIndex[sig.time], idx >= range.start, idx < range.end else { continue }
            let cx = x(for: idx, range: range)
            let cy = y(for: sig.price, height: height, bounds: bounds)
            let color = sig.isBuy ? Theme.up : Theme.down
            // 三角标记：买点朝上，卖点朝下，卖点画在价格上方
            let dir: CGFloat = sig.isBuy ? 1 : -1
            let baseY = cy + dir * 14
            var tri = Path()
            let s: CGFloat = 6
            tri.move(to: CGPoint(x: cx, y: baseY - dir * s))
            tri.addLine(to: CGPoint(x: cx - s, y: baseY + dir * s))
            tri.addLine(to: CGPoint(x: cx + s, y: baseY + dir * s))
            tri.closeSubpath()
            ctx.fill(tri, with: .color(sig.confirmed ? color : color.opacity(0.45)))
            // 标签
            let label = Text(sig.label).font(.system(size: 8, weight: .bold)).foregroundColor(.white)
            let labelY = baseY + dir * 16
            ctx.draw(label, at: CGPoint(x: cx, y: labelY), anchor: .center)
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

    // MARK: - 绘制：十字光标

    private func drawCrosshair(_ ctx: GraphicsContext, plotWidth: CGFloat, height: CGFloat,
                               range: VisibleRange, bounds: PriceBounds) {
        guard let idx = crosshairIndex, idx >= range.start, idx < range.end else { return }
        let cx = x(for: idx, range: range)
        var v = Path()
        v.move(to: CGPoint(x: cx, y: 0))
        v.addLine(to: CGPoint(x: cx, y: height))
        ctx.stroke(v, with: .color(Theme.textSecondary.opacity(0.6)),
                   style: StrokeStyle(lineWidth: 0.5, dash: [3, 3]))
    }

    /// 十字光标选中根的信息浮层。
    private var crosshairInfo: some View {
        Group {
            if let idx = crosshairIndex, idx < candles.count {
                let c = candles[idx]
                HStack(spacing: 10) {
                    Text(c.time).foregroundColor(Theme.textSecondary)
                    label("开", c.open)
                    label("高", c.high)
                    label("低", c.low)
                    label("收", c.close, c.isUp ? Theme.up : Theme.down)
                }
                .font(.system(size: 10, design: .monospaced))
                .padding(.horizontal, 8).padding(.vertical, 4)
                .background(Theme.surfaceAlt.opacity(0.95))
                .clipShape(RoundedRectangle(cornerRadius: 6))
                .padding(6)
            }
        }
    }

    private func label(_ name: String, _ value: Double, _ color: Color = Theme.textPrimary) -> some View {
        HStack(spacing: 2) {
            Text(name).foregroundColor(Theme.textSecondary)
            Text(String(format: "%.2f", value)).foregroundColor(color)
        }
    }

    // MARK: - 手势

    private func dragGesture(plotWidth: CGFloat) -> some Gesture {
        DragGesture(minimumDistance: 2)
            .onChanged { value in
                let range = visibleRange(plotWidth: plotWidth)
                // 纵向拖动优先触发十字光标；横向拖动平移
                if abs(value.translation.height) > abs(value.translation.width) {
                    let localX = value.location.x
                    let idx = Int((localX / range.candleWidth + range.firstVisible).rounded())
                    crosshairIndex = max(0, min(candles.count - 1, idx))
                } else {
                    if dragAnchor == nil { dragAnchor = firstVisible }
                    let deltaCandles = Double(-value.translation.width / range.candleWidth)
                    let count = max(10, min(Double(candles.count), visibleCount))
                    firstVisible = max(0, min((dragAnchor ?? firstVisible) + deltaCandles,
                                              Double(candles.count) - count))
                }
            }
            .onEnded { _ in dragAnchor = nil }
    }

    private func magnifyGesture(plotWidth: CGFloat) -> some Gesture {
        MagnifyGesture()
            .onChanged { value in
                if zoomAnchor == nil { zoomAnchor = visibleCount }
                let base = zoomAnchor ?? visibleCount
                let center = firstVisible + base / 2
                let mag = max(0.2, value.magnification)
                let newCount = max(20, min(Double(candles.count), base / mag))
                visibleCount = newCount
                firstVisible = max(0, min(center - newCount / 2, Double(candles.count) - newCount))
            }
            .onEnded { _ in zoomAnchor = nil }
    }

    private func resetWindowIfNeeded() {
        let total = Double(candles.count)
        visibleCount = min(90, max(20, total))
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
