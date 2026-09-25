import Foundation

/// 用 swiftc 与 RadarOrbitSpacing.swift 一起编译运行，无需启动模拟器。
@main
struct RadarOrbitSpacingTests {
    static func main() {
        testRelax()
        testCrowdScale()
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

    /// 半径按交易日：严格递增，1 天在「今天」环、3 天在「3天内」环、5 天（一周）起在最外圈。
    static func testTimeRadius() {
        let r = (0...20).map { RadarOrbitSpacing.timeRadius(daysAgo: $0) }
        assert(r[0] == 0, "今天在圆心")
        assert(abs(r[1] - 1.0 / 3) < 1e-9 && abs(r[3] - 2.0 / 3) < 1e-9, "1 天在「今天」环、3 天在「3天」环")
        assert(abs(r[5] - 1) < 1e-9 && r[20] == 1, "5 个交易日在「一周内」环，更早封顶")
        for d in 1...5 { assert(r[d] > r[d - 1], "越新越靠中心") }
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

    /// 越远越小：按交易日严格递减，当天 1.0、5 天起封底 0.55。
    static func testTimeSizeFactor() {
        let f = (0...20).map { RadarOrbitSpacing.timeSizeFactor(daysAgo: $0) }
        assert(f[0] == 1, "当天原尺寸")
        for d in 1...5 { assert(f[d] < f[d - 1], "5 天内每往前一天都更小") }
        assert(abs(f[5] - 0.55) < 1e-9 && f[20] == f[5], "5 天起封底")
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

    static func testRelax() {
        typealias P = RadarOrbitSpacing.Placed
        let w = 400.0, h = 320.0, inset = 12.0, gap = 4.0
        func overlaps(_ ps: [P]) -> Bool {
            for i in 0..<ps.count { for j in (i + 1)..<ps.count {
                let need = (ps[i].diameter + ps[j].diameter) / 2 + gap
                if hypot(ps[i].x - ps[j].x, ps[i].y - ps[j].y) < need - 0.5 { return true }
            } }
            return false
        }
        func inBounds(_ ps: [P]) -> Bool {
            ps.allSatisfy { p in
                let r = p.diameter / 2 + inset
                return p.x >= r - 1e-6 && p.x <= w - r + 1e-6 && p.y >= r - 1e-6 && p.y <= h - r + 1e-6
            }
        }
        // 1. 挤在中心附近的一堆气泡：推开后两两不重叠、都在画布内
        let crowded = [P(x: 200, y: 160, diameter: 100), P(x: 215, y: 150, diameter: 90),
                       P(x: 185, y: 175, diameter: 90), P(x: 205, y: 180, diameter: 70),
                       P(x: 240, y: 160, diameter: 88), P(x: 170, y: 150, diameter: 70)]
        let relaxed = RadarOrbitSpacing.relax(crowded, width: w, height: h, inset: inset, gap: gap)
        assert(relaxed.count == crowded.count)
        assert(!overlaps(relaxed), "推开后不再互相压住")
        assert(inBounds(relaxed), "推开后不越出画布")
        // 2. 本来不重叠：位置不动
        let apart = [P(x: 100, y: 100, diameter: 60), P(x: 300, y: 220, diameter: 60)]
        let same = RadarOrbitSpacing.relax(apart, width: w, height: h, inset: inset, gap: gap)
        assert(zip(apart, same).allSatisfy { abs($0.x - $1.x) < 1e-9 && abs($0.y - $1.y) < 1e-9 }, "不重叠的不动")
        // 3. 原本最靠中心的，推开后仍最靠中心（越新越靠中心的顺序大致保留）
        func dist(_ p: P) -> Double { hypot(p.x - w / 2, p.y - h / 2) }
        assert(dist(relaxed[0]) == relaxed.map(dist).min()!, "最靠中心的仍在最中心")
        // 4. 画布放不下：不越界、能结束
        let tooMany = (0..<30).map { i in P(x: 200 + Double(i % 5), y: 160 + Double(i / 5), diameter: 100) }
        let packed = RadarOrbitSpacing.relax(tooMany, width: w, height: h, inset: inset, gap: gap)
        assert(inBounds(packed), "放不下时也不越界")
        // 5. 禁区（如左上角的指数切换按钮）：压在里面的气泡被推出来，且不与禁区相交
        let chip = RadarOrbitSpacing.Obstacle(x: 0, y: 0, width: 150, height: 50)
        let underChip = [P(x: 70, y: 60, diameter: 90), P(x: 300, y: 200, diameter: 60)]
        let out = RadarOrbitSpacing.relax(underChip, width: w, height: h, inset: inset, gap: gap, obstacles: [chip])
        let b = out[0], r = b.diameter / 2
        let nx = min(max(b.x, chip.x), chip.x + chip.width), ny = min(max(b.y, chip.y), chip.y + chip.height)
        assert(hypot(b.x - nx, b.y - ny) >= r - 0.5, "推出禁区")
        assert(inBounds(out), "推出禁区后仍在画布内")
        print("RadarOrbitSpacing relax 测试通过")
    }

    static func testCrowdScale() {
        // 稀疏：不缩
        assert(RadarOrbitSpacing.crowdScale(diameters: [60, 80], width: 400, height: 320) == 1, "不拥挤不缩")
        // 拥挤：缩放后总面积恰好等于上限比例
        let ds = Array(repeating: 110.0, count: 12)
        let k = RadarOrbitSpacing.crowdScale(diameters: ds, width: 400, height: 320, maxFill: 0.5)
        assert(k < 1, "拥挤时缩小")
        let fill = ds.map { Double.pi * pow($0 * k, 2) / 4 }.reduce(0, +) / (400 * 320)
        assert(abs(fill - 0.5) < 1e-9, "缩到上限比例")
        assert(RadarOrbitSpacing.crowdScale(diameters: [], width: 0, height: 0) == 1, "空画布不崩")
        print("RadarOrbitSpacing crowdScale 测试通过")
    }
}
