import CoreGraphics

/// 图表点按命中的纯几何部分（不依赖 SwiftUI，可用 swiftc 单独测试，见 ios/Tests/ChartHitResolverTests.swift）。
///
/// 以前点击判定写死「买卖点优先」，且徽标位置按固定 19pt 估算：底分型圆点的命中半径与
/// 下方买点徽标的命中区重叠，手指落在圆点略下方就弹出买点说明；可视区边缘徽标被夹回
/// 画面内后，判定位置与画出来的位置也对不上。现在徽标位置由绘制与判定共用同一个函数，
/// 多个候选同时命中时选视觉中心离手指最近的那个。
enum ChartHitResolver {
    /// 价格点 → 指向它的小三角的间距；三角高度。与 drawSignals 的版面一致。
    static let badgeGap: CGFloat = 7
    static let badgeTriangle: CGFloat = 4
    /// 点击判定时不知道文字实际宽度，按常见徽标尺寸估算（「一买」「买3」约 26–30pt 宽）。
    static let typicalBadgeSize = CGSize(width: 30, height: 16)

    /// 买卖点徽标中心：买点画在价格下方、卖点在上方（价格 → 间距 → 三角 → 徽标），
    /// 上下左右都夹在可视区内。绘制与点击判定都用它，两边永远对齐。
    static func badgeCenter(anchor: CGPoint, isBuy: Bool, plotWidth: CGFloat, height: CGFloat,
                            badgeSize: CGSize) -> CGPoint {
        let dir: CGFloat = isBuy ? 1 : -1
        let span = badgeGap + badgeTriangle + badgeSize.height
        let y = min(max(anchor.y + dir * (badgeGap + badgeTriangle + badgeSize.height / 2), span), height - span)
        let x = min(max(anchor.x, badgeSize.width / 2), plotWidth - badgeSize.width / 2)
        return CGPoint(x: x, y: y)
    }

    /// 多个候选同时命中时取距离最小的；空则 nil。距离相等时保留先出现的（调用方按优先级排序）。
    static func nearest<T>(_ candidates: [(T, CGFloat)]) -> T? {
        var best: (T, CGFloat)?
        for c in candidates where c.1 < (best?.1 ?? .infinity) { best = c }
        return best?.0
    }
}
