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
        testOrbitPlanning()
    }

    /// 轨道规划：由内向外、间距不重叠、容量不超、各档数量守恒、单个气泡居中。
    static func testOrbitPlanning() {
        typealias B = RadarOrbitSpacing.BandInput
        // 单个气泡：放圆心
        let single = RadarOrbitSpacing.planOrbits(
            bands: [B(count: 1, maxDiameter: 92, bandMin: 0, bandMax: 0.5)], hRad: 170, vRad: 175)
        assert(single.orbits == [RadarOrbitSpacing.Orbit(band: 0, radius: 0, count: 1)])

        // 手机实际尺寸（半轴约 170pt）与宽画布，一周内 8 / 两周内 4 / 一月内 3（5:3:2 环带）
        for (h, v) in [(170.0, 175.0), (260.0, 200.0), (120.0, 130.0)] {
            let bands = [B(count: 8, maxDiameter: 92, bandMin: 0, bandMax: 0.5),
                         B(count: 4, maxDiameter: 78, bandMin: 0.5, bandMax: 0.8),
                         B(count: 3, maxDiameter: 64, bandMin: 0.8, bandMax: 1.0)]
            let plan = RadarOrbitSpacing.planOrbits(bands: bands, hRad: h, vRad: v)
            let minAxis = min(h, v)
            for (i, band) in bands.enumerated() {
                let placed = plan.orbits.filter { $0.band == i }.reduce(0) { $0 + $1.count }
                assert(placed == band.count, "每档气泡数守恒")
                assert(plan.orbits.filter { $0.band == i }.allSatisfy {
                    $0.radius >= band.bandMin - 1e-9 && $0.radius <= band.bandMax + 1e-9
                }, "拥挤压缩时也不能越出自己的时间环带")
            }
            let radii = plan.orbits.map(\.radius)
            assert(radii == radii.sorted(), "轨道由内向外")
            assert(plan.orbits.map(\.band) == plan.orbits.map(\.band).sorted(), "时间档由内向外")
            assert(plan.scale == 1, "拥挤时必须保持气泡原始大小")
            if !plan.compressed {
                for (a, b) in zip(plan.orbits, plan.orbits.dropFirst()) {
                    let step = (min(bands[a.band].maxDiameter, bands[b.band].maxDiameter) * plan.scale + 6) / minAxis
                    assert(b.radius - a.radius >= step - 1e-9, "相邻轨道不重叠")
                }
                for o in plan.orbits {
                    let pitch = bands[o.band].maxDiameter * plan.scale + 6
                    assert(o.count <= RadarOrbitSpacing.capacity(radius: o.radius, pitch: pitch, hRad: h, vRad: v),
                           "每条轨道不超过容量")
                }
            }
            assert((radii.last ?? 0) <= 1, "轨道不越出场")
        }

        // 画布充裕时最内档不外溢：一周内的轨道都在 5:3:2 的第一档内
        let roomy = RadarOrbitSpacing.planOrbits(
            bands: [B(count: 3, maxDiameter: 60, bandMin: 0, bandMax: 0.5),
                    B(count: 2, maxDiameter: 60, bandMin: 0.5, bandMax: 0.8)], hRad: 400, vRad: 400)
        assert(roomy.scale == 1)
        assert(roomy.orbits.filter { $0.band == 0 }.allSatisfy { $0.radius <= 0.5 })
        assert(roomy.orbits.filter { $0.band == 1 }.allSatisfy { $0.radius >= 0.5 && $0.radius <= 0.8 })

        // 名额分配：总数守恒、不超容量（总容量够时）
        assert(RadarOrbitSpacing.distribute(8, capacities: [1, 6, 9]).reduce(0, +) == 8)
        assert(zip(RadarOrbitSpacing.distribute(8, capacities: [1, 6, 9]), [1, 6, 9]).allSatisfy { $0 <= $1 })
        assert(RadarOrbitSpacing.distribute(10, capacities: [1, 3]) == [1, 9])
    }
}
