import Foundation

/// 用 swiftc 与 RadarOrbitSpacing.swift 一起编译运行，无需启动模拟器。
@main
struct RadarOrbitSpacingTests {
    static func main() {
        assert(RadarOrbitSpacing.angles(count: 0, horizontalRadius: 100, verticalRadius: 100, offset: 0).isEmpty)
        for (rx, ry) in [(160.0, 160.0), (280.0, 140.0), (140.0, 280.0)] {
            for count in [1, 2, 5, 10] {
                for offset in [0.0, 0.381966, -0.2] {
                    let angles = RadarOrbitSpacing.angles(
                        count: count, horizontalRadius: rx, verticalRadius: ry, offset: offset
                    ).sorted()
                    assert(angles.count == count)
                    var arcs: [Double] = []
                    for index in angles.indices {
                        let end = index + 1 < count ? angles[index + 1] : angles[0] + 2 * .pi
                        let step = (end - angles[index]) / 1000
                        // 用独立的高精度积分验证实际弧长，包括首尾跨零度的间隔。
                        let length = (0..<1000).reduce(0.0) { sum, sample in
                            let angle = angles[index] + (Double(sample) + 0.5) * step
                            return sum + hypot(rx * sin(angle), ry * cos(angle)) * step
                        }
                        arcs.append(length)
                    }
                    guard let longest = arcs.max(), let shortest = arcs.min() else {
                        preconditionFailure("非空轨道必须有弧长")
                    }
                    assert(shortest > 0 && longest / shortest < 1.001, "各气泡之间的椭圆弧长应均匀")
                }
            }
        }
        testOrbitRadius()
        testBestAngle()
        testTimeSizeFactor()
        testTimeRadius()
        testEllipseHorizontalPreference()
    }

    /// 时间轨道半径：单个气泡保持时间半径（当天居中）；同一天多个时外扩到能排开，但不越过时间档外沿。
    static func testOrbitRadius() {
        let R = 160.0
        assert(RadarOrbitSpacing.orbitRadius(timeRadius: 0, diameters: [76], fieldRadius: R, cap: 0.5) == 0,
               "当天只有一个气泡：放圆心")
        let today3 = RadarOrbitSpacing.orbitRadius(timeRadius: 0, diameters: [76, 60, 92], fieldRadius: R, cap: 0.5)
        assert(today3 > 0 && 2 * Double.pi * today3 * R >= 76 + 60 + 92 + 12 - 0.01, "当天多个：外扩到周长排得开")
        assert(RadarOrbitSpacing.orbitRadius(timeRadius: 0.7, diameters: [60, 60], fieldRadius: R, cap: 0.8) == 0.7,
               "时间半径已经排得开：不动")
        assert(RadarOrbitSpacing.orbitRadius(timeRadius: 0.1, diameters: Array(repeating: 92, count: 12),
                                             fieldRadius: R, cap: 0.5) == 0.5, "排不开时最多外扩到时间档外沿")
    }

    /// 半径按天数平方根：严格递增、最近几天间距更大、7 天起在最外圈。
    static func testTimeRadius() {
        let r = (0...20).map { RadarOrbitSpacing.timeRadius(daysAgo: $0) }
        assert(r[0] == 0, "今天在圆心")
        assert(abs(r[1] - 1.0 / 3) < 1e-9 && abs(r[3] - 2.0 / 3) < 1e-9, "1 天在「今天」环、3 天在「3天」环")
        assert(abs(r[7] - 1) < 1e-9 && r[20] == 1, "7 天在「1周」环，更早封顶")
        for d in 1...7 { assert(r[d] > r[d - 1], "越新越靠中心") }
    }

    /// 椭圆轨道：没有遮挡时放在左右；左边已占，下一个去右边而不是上下。
    static func testEllipseHorizontalPreference() {
        let c = (x: 200.0, y: 150.0), rx = 150.0, ry = 100.0
        let a1 = RadarOrbitSpacing.bestAngle(radiusX: rx, radiusY: ry, diameter: 60, center: c, placed: [], preferred: .pi)
        assert(abs(sin(a1)) < 0.2, "无遮挡时放左右")
        let p1 = RadarOrbitSpacing.Placed(x: c.x + rx * cos(a1), y: c.y + ry * sin(a1), diameter: 60)
        let a2 = RadarOrbitSpacing.bestAngle(radiusX: rx, radiusY: ry, diameter: 60, center: c, placed: [p1], preferred: .pi)
        assert(abs(sin(a2)) < 0.2 && cos(a2) * cos(a1) < 0, "一侧已占时去另一侧，仍在横向")
    }

    /// 越远越小：按天严格递减，当天 1.0、7 天起封底 0.55。
    static func testTimeSizeFactor() {
        let f = (0...20).map { RadarOrbitSpacing.timeSizeFactor(daysAgo: $0) }
        assert(f[0] == 1, "当天原尺寸")
        for d in 1...7 { assert(f[d] < f[d - 1], "7 天内每往前一天都更小") }
        assert(abs(f[7] - 0.55) < 1e-9 && f[20] == f[7], "7 天起封底")
    }

    /// 选方向：半径固定，避开已摆的气泡；同轨道两个气泡能放下时互不重叠。
    static func testBestAngle() {
        let c = (x: 200.0, y: 200.0), r = 100.0
        let first = RadarOrbitSpacing.bestAngle(radius: r, diameter: 60, center: c, placed: [])
        let p1 = RadarOrbitSpacing.Placed(x: c.x + r * cos(first), y: c.y + r * sin(first), diameter: 60)
        let second = RadarOrbitSpacing.bestAngle(radius: r, diameter: 60, center: c, placed: [p1])
        let x2 = c.x + r * cos(second), y2 = c.y + r * sin(second)
        assert(abs(hypot(x2 - c.x, y2 - c.y) - r) < 1e-6, "半径不变")
        assert(hypot(x2 - p1.x, y2 - p1.y) >= 60 - 1e-6, "同轨道第二个气泡避开第一个")
        // 内圈挡住一个方向：外圈气泡自动换方向
        let inner = RadarOrbitSpacing.Placed(x: c.x, y: c.y - 100, diameter: 90)
        let a = RadarOrbitSpacing.bestAngle(radius: r, diameter: 60, center: c, placed: [inner])
        let pa = (x: c.x + r * cos(a), y: c.y + r * sin(a))
        assert(hypot(pa.x - inner.x, pa.y - inner.y) >= 75 - 1e-6, "换方向避开别的轨道上的气泡")
    }
}
