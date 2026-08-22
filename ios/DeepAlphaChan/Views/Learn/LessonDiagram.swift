import SwiftUI

// 教程示意图。
//
// 刻意复用 ChanChartView 的视觉语言：涨绿跌红的蜡烛、Theme.stroke 画笔、
// Theme.segment 画线段、Theme.pivotFill 填中枢。教程里看到的样子和分析页上
// 看到的必须是同一套，否则学完了对不上图，白学。
//
// 用 Canvas 矢量绘制而不是切图：省掉一整套图片资源，深色模式天然一致，
// 而且改一个主题色两边一起变。

/// 一根示意蜡烛。价格用 0…1 归一化——示意图不需要真实价格，只要相对形状。
struct DiagramCandle {
    let open: Double
    let high: Double
    let low: Double
    let close: Double

    var isUp: Bool { close >= open }
}

/// 示意图的声明式描述。
struct DiagramSpec {
    let candles: [DiagramCandle]
    var strokes: [Conn] = []
    var segments: [Conn] = []
    var pivots: [Box] = []
    var fractals: [Dot] = []
    var labels: [Mark] = []
    /// 强调框，用来圈出「这两根是包含关系」这类局部。
    var emphases: [Box] = []

    struct Conn {
        let from: Int
        let to: Int
        /// 连线端点取蜡烛的哪个价位。笔连的是分型的极值，不是收盘价。
        var fromEdge: Edge = .close
        var toEdge: Edge = .close
        var dashed = false

        enum Edge { case high, low, close }
    }

    struct Box {
        let from: Int
        let to: Int
        let top: Double
        let bottom: Double
        var color: Color = Theme.pivotFill
        var alpha: Double = 0.20
    }

    struct Dot {
        let at: Int
        let isTop: Bool
    }

    struct Mark {
        let at: Int
        /// 锚点。用 .value 时 y 是价格；用 .high/.low 时贴着那根蜡烛的极值，
        /// 与分型圆点共用同一套坐标——第一版文字锚固定价位、圆点锚蜡烛极值，
        /// 两套坐标一撞就糊在一起。
        var anchor: Anchor = .value(0)
        let text: String
        var color: Color = Theme.textSecondary
        var above = true
        /// 额外让开的距离，用来给圆点腾位置
        var extraOffset: CGFloat = 0

        enum Anchor {
            case value(Double)
            case high
            case low
        }
    }

    /// 由收盘价路径推导蜡烛。大部分示意图不关心单根的 OHLC 细节，用这个够了；
    /// 需要精确控制形状的（比如包含关系）直接给 candles。
    static func fromPath(
        _ path: [Double],
        strokes: [Conn] = [],
        segments: [Conn] = [],
        pivots: [Box] = [],
        fractals: [Dot] = [],
        labels: [Mark] = [],
        emphases: [Box] = []
    ) -> DiagramSpec {
        let candles = path.indices.map { i -> DiagramCandle in
            let close = path[i]
            let open = i == 0 ? close - 0.06 : path[i - 1]
            let wick = max(0.03, abs(close - open) * 0.5)
            return DiagramCandle(open: open,
                                 high: max(open, close) + wick,
                                 low: min(open, close) - wick,
                                 close: close)
        }
        return DiagramSpec(candles: candles, strokes: strokes, segments: segments,
                           pivots: pivots, fractals: fractals, labels: labels,
                           emphases: emphases)
    }
}

/// 按 DiagramSpec 绘制的示意图。
struct LessonDiagram: View {
    let spec: DiagramSpec
    var height: CGFloat = 160

    var body: some View {
        Canvas { ctx, size in
            let geo = Geometry(size: size, count: spec.candles.count)
            drawGrid(ctx, size: size)
            drawBoxes(ctx, geo: geo, boxes: spec.pivots)
            drawBoxes(ctx, geo: geo, boxes: spec.emphases)
            drawCandles(ctx, geo: geo)
            drawConns(ctx, geo: geo, conns: spec.segments, color: Theme.segment, width: 2.4)
            drawConns(ctx, geo: geo, conns: spec.strokes, color: Theme.stroke, width: 1.4)
            drawFractals(ctx, geo: geo)
            drawLabels(ctx, geo: geo, size: size)
        }
        .frame(height: height)
        .background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    // MARK: - 坐标换算

    private struct Geometry {
        let size: CGSize
        let count: Int
        /// 上下留白给标注文字
        let padY: CGFloat = 26
        let padX: CGFloat = 26

        var step: CGFloat {
            count > 1 ? (size.width - padX * 2) / CGFloat(count - 1) : size.width
        }
        /// 上限 14pt：示意图只有几根 K 线，不设上限会变成一排大色块，
        /// 跟分析页上细密的真实 K 线完全不像。
        var bodyWidth: CGFloat { min(14, max(3, step * 0.55)) }

        func x(_ i: Int) -> CGFloat { padX + CGFloat(i) * step }
        func y(_ v: Double) -> CGFloat {
            let usable = size.height - padY * 2
            return padY + (1 - CGFloat(v)) * usable
        }
    }

    private func price(_ i: Int, _ edge: DiagramSpec.Conn.Edge) -> Double {
        let c = spec.candles[i]
        switch edge {
        case .high:  return c.high
        case .low:   return c.low
        case .close: return c.close
        }
    }

    // MARK: - 各图层

    private func drawGrid(_ ctx: GraphicsContext, size: CGSize) {
        for i in 1..<3 {
            let y = size.height * CGFloat(i) / 3
            var p = Path()
            p.move(to: CGPoint(x: 0, y: y))
            p.addLine(to: CGPoint(x: size.width, y: y))
            ctx.stroke(p, with: .color(Theme.border.opacity(0.35)), lineWidth: 0.5)
        }
    }

    private func drawCandles(_ ctx: GraphicsContext, geo: Geometry) {
        for i in spec.candles.indices {
            let c = spec.candles[i]
            // OHLC 全等的是占位蜡烛，只为在图里留出空隙，不画
            if c.open == c.close && c.high == c.low && c.open == c.high { continue }
            let color = c.isUp ? Theme.up : Theme.down

            var wick = Path()
            wick.move(to: CGPoint(x: geo.x(i), y: geo.y(c.high)))
            wick.addLine(to: CGPoint(x: geo.x(i), y: geo.y(c.low)))
            ctx.stroke(wick, with: .color(color), lineWidth: 1)

            let top = geo.y(max(c.open, c.close))
            let h = max(1.5, geo.y(min(c.open, c.close)) - top)
            let rect = CGRect(x: geo.x(i) - geo.bodyWidth / 2, y: top,
                              width: geo.bodyWidth, height: h)
            ctx.fill(Path(rect), with: .color(color))
        }
    }

    private func drawConns(_ ctx: GraphicsContext, geo: Geometry,
                           conns: [DiagramSpec.Conn], color: Color, width: CGFloat) {
        for c in conns {
            guard spec.candles.indices.contains(c.from),
                  spec.candles.indices.contains(c.to) else { continue }
            var p = Path()
            p.move(to: CGPoint(x: geo.x(c.from), y: geo.y(price(c.from, c.fromEdge))))
            p.addLine(to: CGPoint(x: geo.x(c.to), y: geo.y(price(c.to, c.toEdge))))
            ctx.stroke(p, with: .color(c.dashed ? color.opacity(0.7) : color),
                       style: StrokeStyle(lineWidth: width, lineCap: .round,
                                          dash: c.dashed ? [4, 4] : []))
        }
    }

    private func drawBoxes(_ ctx: GraphicsContext, geo: Geometry, boxes: [DiagramSpec.Box]) {
        for b in boxes {
            // 左右各扩半根蜡烛宽，否则框会从蜡烛中心切过去
            let x1 = geo.x(b.from) - geo.bodyWidth * 0.8
            let x2 = geo.x(b.to) + geo.bodyWidth * 0.8
            let rect = CGRect(x: x1, y: geo.y(b.top),
                              width: x2 - x1,
                              height: geo.y(b.bottom) - geo.y(b.top))
            let shape = Path(roundedRect: rect, cornerRadius: 3)
            ctx.fill(shape, with: .color(b.color.opacity(b.alpha)))
            ctx.stroke(shape, with: .color(b.color.opacity(0.6)), lineWidth: 1)
        }
    }

    private func drawFractals(_ ctx: GraphicsContext, geo: Geometry) {
        for f in spec.fractals {
            guard spec.candles.indices.contains(f.at) else { continue }
            let c = spec.candles[f.at]
            let color = f.isTop ? Theme.topFractal : Theme.bottomFractal
            let r: CGFloat = 3.5
            // 顶分型的点画在最高价上方、底分型画在最低价下方，各让开 7pt；
            // 文字再往外让 13pt，两者不能挤在一起（第一版就糊成一团）。
            let anchorY = f.isTop ? geo.y(c.high) - 7 : geo.y(c.low) + 7
            let center = CGPoint(x: geo.x(f.at), y: anchorY)
            ctx.fill(Path(ellipseIn: CGRect(x: center.x - r, y: center.y - r,
                                            width: r * 2, height: r * 2)),
                     with: .color(color))
        }
    }

    private func drawLabels(_ ctx: GraphicsContext, geo: Geometry, size: CGSize) {
        for m in spec.labels {
            let resolved = ctx.resolve(
                Text(m.text)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundColor(m.color)
            )
            let textSize = resolved.measure(in: size)
            // 夹在画布内，否则靠右的标注会被裁掉（第一版「合并后」就少了半个字）
            let halfW = textSize.width / 2
            let x = min(max(geo.x(m.at), halfW + 4), size.width - halfW - 4)
            let baseY: CGFloat
            switch m.anchor {
            case .value(let v): baseY = geo.y(v)
            case .high:         baseY = geo.y(spec.candles[m.at].high)
            case .low:          baseY = geo.y(spec.candles[m.at].low)
            }
            let dir: CGFloat = m.above ? -1 : 1
            let y = baseY + dir * (14 + m.extraOffset)
            ctx.draw(resolved, at: CGPoint(x: x, y: y), anchor: .center)
        }
    }
}
