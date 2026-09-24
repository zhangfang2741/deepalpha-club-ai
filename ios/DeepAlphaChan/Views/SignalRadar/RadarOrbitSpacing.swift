import Foundation

/// 沿椭圆周长等距取点，避免宽高不同时等角分布产生视觉上的疏密差异。
enum RadarOrbitSpacing {
    static func angles(
        count: Int, horizontalRadius: Double, verticalRadius: Double, offset: Double
    ) -> [Double] {
        guard count > 0 else { return [] }
        let samples = 720
        let step = 2 * Double.pi / Double(samples)
        let rx = max(horizontalRadius, 1)
        let ry = max(verticalRadius, 1)
        var lengths = [0.0]
        for index in 1...samples {
            let angle = (Double(index) - 0.5) * step
            let dx = rx * sin(angle)
            let dy = ry * cos(angle)
            lengths.append(lengths[index - 1] + hypot(dx, dy) * step)
        }
        let perimeter = lengths[samples]
        return (0..<count).map { index in
            let fraction = (Double(index) / Double(count) + offset).truncatingRemainder(dividingBy: 1)
            let target = (fraction < 0 ? fraction + 1 : fraction) * perimeter
            var lower = 0
            var upper = samples
            while upper - lower > 1 {
                let middle = (lower + upper) / 2
                if lengths[middle] <= target {
                    lower = middle
                } else {
                    upper = middle
                }
            }
            let t = (target - lengths[lower]) / (lengths[upper] - lengths[lower])
            return (Double(lower) + t) * step
        }
    }
}

// MARK: - 轨道规划：按时间档由内向外排轨道

extension RadarOrbitSpacing {
    /// 一个时间档（环带）的输入：气泡数、最大直径（点）、环带归一化范围（占半轴比例 0~1）。
    struct BandInput {
        let count: Int
        let maxDiameter: Double
        let bandMin: Double
        let bandMax: Double
    }

    /// 一条轨道：所属环带、归一化半径（0 = 圆心）、放几个气泡。
    struct Orbit: Equatable {
        let band: Int
        let radius: Double
        let count: Int
    }

    /// 保持原始气泡大小规划轨道；放不下时仅在所属时间环带内压缩间距，允许重叠。
    static func planOrbits(
        bands: [BandInput], hRad: Double, vRad: Double, gap: Double = 6
    ) -> (scale: Double, orbits: [Orbit], compressed: Bool) {
        let minAxis = max(min(hRad, vRad), 1)
        let scale = 1.0
        let (orbits, fits) = layout(bands: bands, scale: scale, hRad: hRad, vRad: vRad,
                                   minAxis: minAxis, gap: gap)
        if fits { return (scale, orbits, false) }
        // 各环带独立压缩，不能全场等比缩放，否则旧信号会落入更新的时间档。
        let bounded = orbits.map { orbit in
            let band = bands[orbit.band]
            let edge = max(band.bandMin, 1 - (band.maxDiameter * scale / 2 + 4) / minAxis)
            let upper = min(band.bandMax, edge)
            let sameBand = orbits.filter { $0.band == orbit.band }
            let first = sameBand.map(\.radius).min() ?? band.bandMin
            let last = sameBand.map(\.radius).max() ?? band.bandMax
            let lower = min(max(first, band.bandMin), upper)
            let radius: Double
            if last > upper, last > first {
                radius = lower + (orbit.radius - first) / (last - first) * (upper - lower)
            } else {
                radius = min(max(orbit.radius, band.bandMin), upper)
            }
            return Orbit(band: orbit.band, radius: radius, count: orbit.count)
        }
        return (scale, bounded, true)
    }

    /// 椭圆轨道（归一化半径 r）能等距放下的气泡数。
    static func capacity(radius r: Double, pitch: Double, hRad: Double, vRad: Double) -> Int {
        if r < 1e-9 { return 1 }
        let a = r * hRad, b = r * vRad
        let h = pow(a - b, 2) / pow(a + b, 2)
        // Ramanujan 椭圆周长近似
        let perimeter = Double.pi * (a + b) * (1 + 3 * h / (10 + (4 - 3 * h).squareRoot()))
        return max(1, Int(perimeter / pitch))
    }

    private static func layout(
        bands: [BandInput], scale: Double, hRad: Double, vRad: Double, minAxis: Double, gap: Double
    ) -> ([Orbit], Bool) {
        var orbits: [Orbit] = []
        var cursor = 0.0            // 下一条轨道允许的最小归一化半径
        var outerLimit = 0.0        // 各轨道所需的最外边界（含气泡半径）
        for (index, band) in bands.enumerated() where band.count > 0 {
            let d = band.maxDiameter * scale
            let pitch = d + gap
            let step = pitch / minAxis
            var radii: [Double]
            if orbits.isEmpty && band.bandMin == 0 && (2...4).contains(band.count) {
                // 最内档只有 2~4 个：不占圆心，围成一圈（半径取刚好不重叠的弦长）
                let r = pitch / (2 * sin(.pi / Double(band.count))) / minAxis
                radii = [max(r, cursor)]
            } else {
                // 起点：圆心（仅最内档）或环带内沿再让出半个间距
                let start = orbits.isEmpty && band.bandMin == 0
                    ? 0 : max(cursor, band.bandMin + step / 2)
                var total = 0
                radii = []
                var r = start
                while total < band.count {
                    radii.append(r)
                    total += capacity(radius: r, pitch: pitch, hRad: hRad, vRad: vRad)
                    r += step
                }
                // 环带内有富余：把轨道均匀铺到环带外沿（留半个间距给下一档）
                let hi = band.bandMax - (index < bands.count - 1 ? step / 2 : 0)
                if radii.count > 1, let last = radii.last, last < hi {
                    let lo = radii[0]
                    radii = (0..<radii.count).map { lo + (hi - lo) * Double($0) / Double(radii.count - 1) }
                } else if radii.count == 1, radii[0] > 0, radii[0] < band.bandMin + (hi - band.bandMin) / 2 {
                    radii[0] = max(radii[0], (band.bandMin + hi) / 2)
                }
            }
            // 按容量比例分配气泡数（内圈先满足，余数给外圈）
            let caps = radii.map { capacity(radius: $0, pitch: pitch, hRad: hRad, vRad: vRad) }
            let counts = distribute(band.count, capacities: caps)
            for (r, c) in zip(radii, counts) where c > 0 {
                orbits.append(Orbit(band: index, radius: r, count: c))
            }
            let last = radii.last ?? cursor
            cursor = last + step
            outerLimit = max(outerLimit, last + (d / 2 + 4) / minAxis)
        }
        let staysInBands = orbits.allSatisfy { orbit in
            let band = bands[orbit.band]
            return orbit.radius >= band.bandMin - 1e-9 && orbit.radius <= band.bandMax + 1e-9
        }
        return (orbits, staysInBands && outerLimit <= 1 + 1e-9)
    }

    /// 把 total 个名额按容量比例分到各轨道，每条不超过自身容量（超出时溢出到最外圈）。
    static func distribute(_ total: Int, capacities: [Int]) -> [Int] {
        guard !capacities.isEmpty else { return [] }
        let sum = capacities.reduce(0, +)
        if sum <= total {
            var counts = capacities
            counts[counts.count - 1] += total - sum
            return counts
        }
        var counts = capacities.map { Int(Double(total) * Double($0) / Double(sum)) }
        var remaining = total - counts.reduce(0, +)
        var index = 0
        while remaining > 0 {
            if counts[index] < capacities[index] {
                counts[index] += 1
                remaining -= 1
            }
            index = (index + 1) % counts.count
        }
        return counts
    }
}

// MARK: - 面积缩放 + 碰撞松弛

extension RadarOrbitSpacing {
    /// 气泡总面积占场（椭圆）面积的上限：超过就按面积等比缩小全部气泡。
    /// 带时间环带约束的圆堆积，实测 40% 出头还能不重叠地摆开，再多必然互相压住。
    static let maxAreaFill = 0.42
    /// 缩放下限：再小文字就读不清，宁可允许少量重叠。
    static let minScale = 0.6

    /// 让全部气泡放得下的统一缩放比例（1 = 不缩）。等比缩小保留一/二/三类的相对大小。
    static func areaScale(diameters: [Double], hRad: Double, vRad: Double) -> Double {
        let bubbles = diameters.reduce(0) { $0 + Double.pi * $1 * $1 / 4 }
        let field = Double.pi * hRad * vRad
        guard bubbles > 0, field > 0 else { return 1 }
        let budget = field * maxAreaFill
        if bubbles <= budget { return 1 }
        return max(minScale, (budget / bubbles).squareRoot())
    }

    /// 参与松弛的气泡：中心坐标、直径、按时间应在的归一化半径（占半轴比例 0~1）。
    struct Body: Equatable {
        var x: Double
        var y: Double
        var diameter: Double
        var targetRadius: Double
    }

    /// 碰撞松弛：反复把两两重叠的气泡沿连线推开，同时用弱回复力把每个气泡拉回
    /// 它按时间应在的椭圆半径上（保留「越靠中心越新」），并夹在画布内。
    /// 纯函数、确定性（固定迭代次数、固定顺序），同样输入永远得到同样布局，不会闪动。
    static func relax(
        _ bodies: [Body], width w: Double, height h: Double, hRad: Double, vRad: Double,
        gap: Double = 4, iterations: Int = 240
    ) -> [Body] {
        var b = bodies
        let cx = w / 2, cy = h / 2
        let n = b.count
        guard n > 1 else { return b.map { clamp($0, w, h) } }
        for step in 0..<iterations {
            // 回复力随迭代衰减：前期让气泡回到各自时间环，后期让位给去重叠
            let pull = 0.08 * (1 - Double(step) / Double(iterations))
            for i in 0..<n {
                let dx = (b[i].x - cx) / max(hRad, 1), dy = (b[i].y - cy) / max(vRad, 1)
                let r = (dx * dx + dy * dy).squareRoot()
                if r > 1e-6 {
                    let k = (b[i].targetRadius / r - 1) * pull
                    b[i].x += (b[i].x - cx) * k
                    b[i].y += (b[i].y - cy) * k
                }
            }
            var moved = false
            for i in 0..<n {
                for j in (i + 1)..<n {
                    var dx = b[j].x - b[i].x, dy = b[j].y - b[i].y
                    var dist = (dx * dx + dy * dy).squareRoot()
                    let need = (b[i].diameter + b[j].diameter) / 2 + gap
                    guard dist < need else { continue }
                    if dist < 1e-6 {
                        // 完全重合：按下标给个确定的方向分开
                        let angle = Double(i * 7 + j * 13)
                        dx = cos(angle); dy = sin(angle); dist = 1
                    }
                    // 大气泡挪得少、小气泡挪得多（按面积反比分配位移）
                    let ai = b[i].diameter * b[i].diameter, aj = b[j].diameter * b[j].diameter
                    let push = need - dist
                    let ui = push * aj / (ai + aj), uj = push * ai / (ai + aj)
                    b[i].x -= dx / dist * ui; b[i].y -= dy / dist * ui
                    b[j].x += dx / dist * uj; b[j].y += dy / dist * uj
                    moved = true
                }
            }
            for i in 0..<n { b[i] = clamp(b[i], w, h) }
            if !moved && pull < 1e-3 { break }
        }
        return b
    }

    private static func clamp(_ body: Body, _ w: Double, _ h: Double) -> Body {
        var c = body
        let r = c.diameter / 2 + 2
        c.x = min(max(c.x, r), w - r)
        c.y = min(max(c.y, r), h - r)
        return c
    }
}
