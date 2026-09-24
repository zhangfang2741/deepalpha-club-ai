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
    }
}
