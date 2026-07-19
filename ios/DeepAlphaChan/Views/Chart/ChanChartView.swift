import SwiftUI

/// 缠论主图表：K 线 + 缠论结构叠加 + MACD 副图。
///
/// 采用原生 Canvas 逐帧绘制，固定窗口显示最新数据。
struct ChanChartView: View {
    let analysis: ChanAnalysis
    @ObservedObject var vm: ChanViewModel

    // 可见窗口：起始下标（可为小数）与可见根数。
    @State private var firstVisible: Double = 0
    @State private var visibleCount: Double = 80

    // 拖动手势的基准值
    @State private var dragAnchor: Double? = nil

    // 光标：选中的 K 线索引（nil = 不显示）
    @State private var cursorIndex: Int? = nil
    @State private var cursorDragging: Bool = false

    // 双指缩放基准值
    @State private var zoomAnchor: Double? = nil

    private let priceHeight: CGFloat = 300
    private let macdHeight: CGFloat = 110
    private let timeAxisHeight: CGFloat = 22
    private let rightAxisWidth: CGFloat = 52

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
                    // 十字光标
                    if let ci = cursorIndex, ci >= range.start, ci < range.end {
                        drawCursor(ctx, plotWidth: plotW, height: size.height,
                                   range: range, bounds: priceBounds, index: ci)
                    }
                }
            }
            .contentShape(Rectangle())
            .gesture(chartGesture(plotWidth: plotWidth))
            .gesture(magnificationGesture(plotWidth: plotWidth))
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

    // MARK: - 手势

    /// 复合手势：水平拖动 < 8pt 视为点击（显示光标），否则平移图表。
    private func chartGesture(plotWidth: CGFloat) -> some Gesture {
        DragGesture(minimumDistance: 0)
            .onChanged { value in
                let translation = value.translation
                if abs(translation.width) < 8 && abs(translation.height) < 8 && !cursorDragging {
                    // 点击：定位到最近的 K 线
                    let range = visibleRange(plotWidth: plotWidth)
                    let tapX = value.location.x
                    let rel = Double(tapX / range.candleWidth) + range.firstVisible
                    let idx = max(0, min(candles.count - 1, Int(rel.rounded())))
                    cursorIndex = idx
                } else {
                    // 拖动平移
                    cursorDragging = true
                    let range = visibleRange(plotWidth: plotWidth)
                    if dragAnchor == nil { dragAnchor = firstVisible }
                    let deltaCandles = Double(-translation.width / range.candleWidth)
                    let count = max(10, min(Double(candles.count), visibleCount))
                    firstVisible = max(0, min((dragAnchor ?? firstVisible) + deltaCandles,
                                              Double(candles.count) - count))
                }
            }
            .onEnded { _ in
                dragAnchor = nil
                cursorDragging = false
            }
    }

    /// 将光标移动到指定 zindex 并保留。
    private func moveCursor(to index: Int) {
        cursorIndex = max(0, min(candles.count - 1, index))
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

        // 价格标签（右侧轴上）
        let labelText = Text(String(format: "%.2f", c.close))
            .font(.system(size: 10, weight: .semibold))
            .foregroundColor(.white)
        let labelW: CGFloat = 48
        let labelH: CGFloat = 14
        let labelRect = CGRect(x: plotWidth + 2, y: cy - labelH / 2, width: labelW, height: labelH)
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
                infoText("开", String(format: "%.2f", c.open))
                infoText("高", String(format: "%.2f", c.high))
                infoText("低", String(format: "%.2f", c.low))
                infoText("收", String(format: "%.2f", c.close))
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
