import SwiftUI

/// 五维图的几何与标签布局（纯函数，单测见 ios/Tests/QuantResearchTests.swift）。
///
/// 半径 = 板块百分位（0~100）；轴从正上方开始顺时针排布。标签放在各轴外侧：右侧的左对齐、
/// 左侧的右对齐、上下居中；先按较大的半径摆，只要有标签超出画布就缩小半径重摆，最后再把
/// 标签钳进画布——草图阶段出现过左侧「EPS 修正」被裁掉，这里从布局上杜绝。半径不低于 minRadius，
/// 窄屏放不下时标签向内平移（可能轻压图形边缘），也不把图缩到看不清。
struct FiveDimensionLayout {
    struct Label {
        let rect: CGRect
        let alignment: HorizontalAlignment
    }

    let center: CGPoint
    let radius: CGFloat
    let labels: [Label]

    static let labelGap: CGFloat = 10
    /// 半径下限：窄屏 + 长英文标签时不再为了标签继续缩图，改为把标签往画布内平移。
    static let minRadius: CGFloat = 72
    static let lineHeight: CGFloat = 16

    /// 按字符估算文字宽度：中日韩字符约 1 个字号宽，其余约 0.58 个字号宽。
    static func estimatedWidth(_ text: String, fontSize: CGFloat) -> CGFloat {
        text.unicodeScalars.reduce(0) { w, s in
            w + (s.value > 0x2E80 ? fontSize : fontSize * 0.58)
        }
    }

    static func direction(_ index: Int, count: Int) -> CGVector {
        let angle = -Double.pi / 2 + Double(index) * 2 * Double.pi / Double(count)
        return CGVector(dx: cos(angle), dy: sin(angle))
    }

    /// titles：每个轴的标签（第一行名称、第二行等级）。
    init(size: CGSize, titles: [(name: String, grade: String)], fontSize: CGFloat = 12.5) {
        let count = max(titles.count, 3)
        let c = CGPoint(x: size.width / 2, y: size.height / 2)
        let bounds = CGRect(origin: .zero, size: size)
        var r = min(size.width, size.height) / 2 - 20
        var placed: [Label] = []
        while true {
            placed = titles.enumerated().map { i, t in
                Self.place(title: t, dir: Self.direction(i, count: count), center: c, radius: r, fontSize: fontSize)
            }
            if placed.allSatisfy({ bounds.contains($0.rect) }) || r <= Self.minRadius { break }
            r -= 4
        }
        center = c
        radius = r
        labels = placed.map { l in
            var rect = l.rect
            rect.origin.x = min(max(rect.minX, 0), size.width - rect.width)
            rect.origin.y = min(max(rect.minY, 0), size.height - rect.height)
            return Label(rect: rect, alignment: l.alignment)
        }
    }

    private static func place(title: (name: String, grade: String), dir: CGVector, center: CGPoint,
                              radius: CGFloat, fontSize: CGFloat) -> Label {
        let width = max(estimatedWidth(title.name, fontSize: fontSize),
                        estimatedWidth(title.grade, fontSize: fontSize)) + 2
        let height = lineHeight * 2
        let anchor = CGPoint(x: center.x + dir.dx * (radius + labelGap), y: center.y + dir.dy * (radius + labelGap))
        let alignment: HorizontalAlignment
        var origin: CGPoint
        if dir.dx > 0.3 {
            alignment = .leading
            origin = CGPoint(x: anchor.x, y: anchor.y - height / 2)
        } else if dir.dx < -0.3 {
            alignment = .trailing
            origin = CGPoint(x: anchor.x - width, y: anchor.y - height / 2)
        } else {
            alignment = .center
            origin = CGPoint(x: anchor.x - width / 2, y: dir.dy < 0 ? anchor.y - height : anchor.y)
        }
        return Label(rect: CGRect(origin: origin, size: CGSize(width: width, height: height)), alignment: alignment)
    }

    func point(index: Int, count: Int, percentile: Double) -> CGPoint {
        let d = Self.direction(index, count: count)
        let r = radius * CGFloat(min(max(percentile, 0), 100) / 100)
        return CGPoint(x: center.x + d.dx * r, y: center.y + d.dy * r)
    }
}

/// 五维图：实线 = 本股各维度分，虚线 = 板块中位（50）；不可用维度画灰色虚轴并标「暂无」，
/// 本股多边形跳过它（直接连相邻的有数据维度）。
struct FiveDimensionChart: View {
    let dimensions: [QuantDimension]
    let symbol: String
    var onSelect: (QuantDimension) -> Void = { _ in }

    private let height: CGFloat = 280

    var body: some View {
        GeometryReader { geo in
            let titles = dimensions.map { (name: $0.name, grade: $0.grade ?? L("暂无")) }
            let layout = FiveDimensionLayout(size: CGSize(width: geo.size.width, height: height), titles: titles)
            let n = dimensions.count
            ZStack(alignment: .topLeading) {
                Canvas { ctx, _ in
                    for ring in [25.0, 50.0, 75.0, 100.0] {
                        ctx.stroke(polygon(layout, n, Array(repeating: ring, count: n)),
                                   with: .color(Theme.border), lineWidth: 1)
                    }
                    for i in 0..<n {
                        var axis = Path()
                        axis.move(to: layout.center)
                        axis.addLine(to: layout.point(index: i, count: n, percentile: 100))
                        let ok = dimensions[i].isOK
                        ctx.stroke(axis, with: .color(ok ? Theme.border : Theme.textSecondary.opacity(0.5)),
                                   style: StrokeStyle(lineWidth: 1, dash: ok ? [] : [3, 3]))
                    }
                    ctx.stroke(polygon(layout, n, Array(repeating: 50, count: n)),
                               with: .color(Theme.textSecondary), style: StrokeStyle(lineWidth: 1.5, dash: [4, 3]))
                    // 本股多边形只连有数据的维度：暂无数据（如 EPS 修正积累中）不能画到圆心，
                    // 否则看起来像是这一项得了 0 分
                    let shape = stockPolygon(layout, n)
                    ctx.fill(shape, with: .color(Theme.up.opacity(0.22)))
                    ctx.stroke(shape, with: .color(Theme.up), lineWidth: 2)
                    for (i, d) in dimensions.enumerated() where d.isOK {
                        let p = layout.point(index: i, count: n, percentile: d.score ?? 0)
                        ctx.fill(Path(ellipseIn: CGRect(x: p.x - 3.5, y: p.y - 3.5, width: 7, height: 7)),
                                 with: .color(Theme.up))
                    }
                }
                .frame(height: height)

                ForEach(Array(dimensions.enumerated()), id: \.element.key) { i, d in
                    let label = layout.labels[i]
                    Button { onSelect(d) } label: {
                        VStack(alignment: label.alignment, spacing: 0) {
                            Text(d.name).foregroundStyle(Theme.textPrimary)
                            Text(d.grade ?? L("暂无"))
                                .fontWeight(.semibold)
                                .foregroundStyle(QuantGradeStyle.color(d.grade))
                        }
                        .font(.system(size: 12.5))
                        .frame(width: label.rect.width, height: label.rect.height,
                               alignment: Alignment(horizontal: label.alignment, vertical: .center))
                    }
                    .buttonStyle(.plain)
                    .offset(x: label.rect.minX, y: label.rect.minY)
                    .accessibilityLabel("\(d.name) \(d.grade ?? L("暂无"))")
                }
            }
        }
        .frame(height: height)
        .overlay(alignment: .bottom) { legend.offset(y: 18) }
        .padding(.bottom, 22)
    }

    private var legend: some View {
        HStack(spacing: 14) {
            HStack(spacing: 4) {
                Rectangle().fill(Theme.up).frame(width: 14, height: 2)
                Text(symbol)
            }
            HStack(spacing: 4) {
                Rectangle().stroke(Theme.textSecondary, style: StrokeStyle(lineWidth: 2, dash: [3, 2]))
                    .frame(width: 14, height: 1)
                Text(L("板块中位"))
            }
        }
        .font(.caption2)
        .foregroundStyle(Theme.textSecondary)
    }

    private func stockPolygon(_ layout: FiveDimensionLayout, _ n: Int) -> Path {
        var path = Path()
        let pts = dimensions.enumerated().compactMap { i, d in
            d.isOK ? layout.point(index: i, count: n, percentile: d.score ?? 0) : nil
        }
        guard let first = pts.first else { return path }
        path.move(to: first)
        pts.dropFirst().forEach { path.addLine(to: $0) }
        path.closeSubpath()
        return path
    }

    private func polygon(_ layout: FiveDimensionLayout, _ n: Int, _ values: [Double]) -> Path {
        var path = Path()
        for i in 0..<n {
            let p = layout.point(index: i, count: n, percentile: values[i])
            if i == 0 { path.move(to: p) } else { path.addLine(to: p) }
        }
        path.closeSubpath()
        return path
    }
}
