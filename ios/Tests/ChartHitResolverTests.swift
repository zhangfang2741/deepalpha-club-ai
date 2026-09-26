import CoreGraphics
import Foundation

@main
struct ChartHitResolverTests {
    static func main() {
        let size = CGSize(width: 30, height: 16)
        // 1. 徽标位置：买点在价格下方（间距 7 + 三角 4 + 半高 8 = 19）
        let c = ChartHitResolver.badgeCenter(anchor: CGPoint(x: 100, y: 100), isBuy: true,
                                             plotWidth: 300, height: 240, badgeSize: size)
        assert(abs(c.y - 119) < 0.01 && c.x == 100, "买点徽标在价格下方 19pt")
        // 2. 靠近底边时徽标被夹回可视区（与绘制一致）
        let low = ChartHitResolver.badgeCenter(anchor: CGPoint(x: 100, y: 235), isBuy: true,
                                               plotWidth: 300, height: 240, badgeSize: size)
        assert(low.y <= 240 - 27 + 0.01, "底部徽标夹在可视区内")
        // 3. 靠近右边时水平也夹住
        let right = ChartHitResolver.badgeCenter(anchor: CGPoint(x: 298, y: 100), isBuy: false,
                                                 plotWidth: 300, height: 240, badgeSize: size)
        assert(right.x == 285, "右侧徽标水平夹住")
        // 4. 点在分型圆点略下方（手指常落点）：离分型更近 → 选分型，而不是买点
        let dot = CGPoint(x: 100, y: 100)
        let badge = ChartHitResolver.badgeCenter(anchor: dot, isBuy: true, plotWidth: 300, height: 240, badgeSize: size)
        let tap = CGPoint(x: 101, y: 109)
        let pick = ChartHitResolver.nearest([("signal", hypot(tap.x - badge.x, tap.y - badge.y)),
                                             ("fractal", hypot(tap.x - dot.x, tap.y - dot.y))])
        assert(pick == "fractal", "点分型略下方应出分型说明")
        // 5. 点在徽标上 → 买点
        let tap2 = CGPoint(x: 104, y: 120)
        let pick2 = ChartHitResolver.nearest([("signal", hypot(tap2.x - badge.x, tap2.y - badge.y)),
                                              ("fractal", hypot(tap2.x - dot.x, tap2.y - dot.y))])
        assert(pick2 == "signal", "点徽标应出买点说明")
        assert(ChartHitResolver.nearest([(String, CGFloat)]()) == nil)
        print("ChartHitResolver 测试通过")
    }
}
