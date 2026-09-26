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

// MARK: - 时间轨道（正圆）

extension RadarOrbitSpacing {
    /// 时间（交易日）→ 归一化半径，对应「今天 / 3 天 / 一周」三个等距环（1/3、2/3、1）：
    /// 今天在最内环以内（圆心），1～3 个交易日前在第一、二环之间，4～5 个交易日前在第二、三环
    /// 之间，各区间内按天均匀分布；后端信号本身最多只保留 5 个交易日（见 _MAX_SIGNAL_AGE_DAYS），
    /// 封顶只是兜底，正常不会有更早的信号传进来。
    static func timeRadius(daysAgo: Int) -> Double {
        let d = max(0, daysAgo)
        if d == 0 { return 0 }
        if d <= 3 { return (1.0 + Double(d - 1) / 2.0) / 3.0 }
        return (2.0 + min(1.0, Double(d - 3) / 2.0)) / 3.0
    }

    /// 时间 → 气泡尺寸系数：越远越小，按交易日连续递减（当天 1.0，5 天及更早 0.55），
    /// horizon 与后端信号保留上限（5 个交易日）对齐。与一二三类对应的直径相乘。
    static func timeSizeFactor(daysAgo: Int, horizon: Int = 5, minFactor: Double = 0.55) -> Double {
        let t = min(1, Double(max(0, daysAgo)) / Double(max(1, horizon)))
        return 1 - (1 - minFactor) * t
    }

    /// 同一天气泡所在圆轨道的归一化半径（占场半径比例）。
    ///
    /// 远近严格由时间决定：默认就是时间半径。只有当这条圆轨道周长放不下同一天的全部
    /// 气泡时（当天与前一两天半径很小，几个气泡会叠在一起），才外扩到刚好能排开的半径，
    /// 且不越过所在时间档的外沿 cap。
    static func orbitRadius(
        timeRadius: Double, diameters: [Double], fieldRadius: Double, cap: Double, gap: Double = 4
    ) -> Double {
        guard diameters.count > 1, fieldRadius > 0 else { return timeRadius }
        let need = diameters.reduce(0, +) + gap * Double(diameters.count)
        let fit = need / (2 * Double.pi * fieldRadius)
        return min(max(timeRadius, fit), max(timeRadius, cap))
    }

    /// 碰撞松弛：先按时间摆好后，把压得太多的气泡沿中心连线推开，直到达标或达到迭代上限。
    ///
    /// 推开时离画布中心更远的一方多挪、更近的一方少挪，越新（越靠中心）的气泡仍留在中间。
    /// 每一步都夹回画布内；本来不冲突的气泡位置不变。
    ///
    /// - overlapRatio：允许两个气泡边缘重叠「较小直径 × 此比例」。0 = 必须完全分开并留 gap
    ///   （旧行为）。完全不许重叠时，10 个气泡在手机画布里只能被挤成一整圈铺满，离中心的
    ///   远近就不再代表时间；允许边缘少量重叠（文字在气泡中间，盖不到），时间感才留得住。
    /// - anchors：每个气泡所属时间环的椭圆半轴（圆心在画布中心）。给了就每轮把气泡沿当前
    ///   方向往自己的环上拉一点，拉力随迭代线性衰减到 0，最后一段只做碰撞收尾，保证结束时
    ///   重叠不超过上限。nil = 不回拉（旧行为）。
    static func relax(
        _ input: [Placed], width: Double, height: Double, inset: Double,
        gap: Double = 4, iterations: Int = 300, obstacles: [Obstacle] = [],
        overlapRatio: Double = 0, anchors: [Anchor]? = nil, anchorStrength: Double = 0.12
    ) -> [Placed] {
        var ps = input
        let anchors = anchors.flatMap { $0.count == ps.count ? $0 : nil }
        guard ps.count > 1 || !obstacles.isEmpty || anchors != nil else { return ps }
        let cx = width / 2, cy = height / 2
        func clamp(_ p: inout Placed) {
            let r = p.diameter / 2 + inset
            p.x = min(max(p.x, r), max(r, width - r))
            p.y = min(max(p.y, r), max(r, height - r))
        }
        // 回拉只在前 70% 的迭代里生效，剩下的纯做碰撞收尾
        let pullIterations = anchors == nil ? 0 : Int(Double(iterations) * 0.7)
        for k in 0..<iterations {
            var moved = false
            if let anchors, k < pullIterations {
                let strength = anchorStrength * (1 - Double(k) / Double(pullIterations))
                for i in ps.indices {
                    let a = anchors[i]
                    var tx = cx, ty = cy
                    if a.rx > 1e-6, a.ry > 1e-6 {
                        let dx = ps[i].x - cx, dy = ps[i].y - cy
                        // 按椭圆参数角取环上同方向的点；正好在圆心时给一个确定的方向（水平向右）
                        let t = (abs(dx) < 1e-9 && abs(dy) < 1e-9) ? 0 : atan2(dy / a.ry, dx / a.rx)
                        tx = cx + a.rx * cos(t)
                        ty = cy + a.ry * sin(t)
                    }
                    let mx = (tx - ps[i].x) * strength, my = (ty - ps[i].y) * strength
                    if abs(mx) > 1e-3 || abs(my) > 1e-3 {
                        ps[i].x += mx
                        ps[i].y += my
                        clamp(&ps[i])
                        moved = true
                    }
                }
            }
            for i in 0..<ps.count {
                for j in (i + 1)..<ps.count {
                    var dx = ps[j].x - ps[i].x, dy = ps[j].y - ps[i].y
                    var d = hypot(dx, dy)
                    let slack = overlapRatio > 0
                        ? -overlapRatio * min(ps[i].diameter, ps[j].diameter) : gap
                    let need = (ps[i].diameter + ps[j].diameter) / 2 + slack
                    guard d < need else { continue }
                    if d < 1e-6 {
                        // 完全重合：用黄金角给一个确定性的推开方向
                        let a = Double(j) * 2.399963229728653
                        dx = cos(a); dy = sin(a); d = 1
                    }
                    let ux = dx / d, uy = dy / d
                    let overlap = need - d + 0.01
                    let di = hypot(ps[i].x - cx, ps[i].y - cy)
                    let dj = hypot(ps[j].x - cx, ps[j].y - cy)
                    let wi = di <= dj ? 0.2 : 0.8
                    ps[i].x -= ux * overlap * wi
                    ps[i].y -= uy * overlap * wi
                    ps[j].x += ux * overlap * (1 - wi)
                    ps[j].y += uy * overlap * (1 - wi)
                    clamp(&ps[i]); clamp(&ps[j])
                    moved = true
                }
            }
            // 禁区（画布上叠着的按钮等）：气泡与矩形相交就沿「矩形最近点 → 圆心」推出去
            for i in ps.indices {
                for o in obstacles {
                    let r = ps[i].diameter / 2 + gap
                    let nx = min(max(ps[i].x, o.x), o.x + o.width)
                    let ny = min(max(ps[i].y, o.y), o.y + o.height)
                    let dx = ps[i].x - nx, dy = ps[i].y - ny
                    let d = hypot(dx, dy)
                    guard d < r else { continue }
                    if d < 1e-6 {
                        // 圆心落在矩形内：往下推出（禁区都贴在画布顶边）
                        ps[i].y = o.y + o.height + r
                    } else {
                        ps[i].x += dx / d * (r - d + 0.01)
                        ps[i].y += dy / d * (r - d + 0.01)
                    }
                    clamp(&ps[i])
                    moved = true
                }
            }
            if !moved && k >= pullIterations { break }
        }
        return ps
    }

    /// 气泡所属时间环的椭圆半轴（圆心 = 画布中心）；0 表示「今天」落在圆心。
    struct Anchor: Equatable {
        var rx: Double
        var ry: Double
    }

    /// 拥挤缩放：气泡总面积超过画布面积的 maxFill 时，返回让总面积恰好等于上限的统一缩放系数，
    /// 否则 1。统一缩放不改变一二三类之间的大小关系，只在当天信号特别集中时生效。
    ///
    /// 上榜固定取前 10 名（见 SignalRadarView 算法说明），几乎每天都接近这个数，导致旧上限
    /// 0.5（气泡总面积占画布一半）几乎天天顶格生效——气泡感觉总是偏大。收紧到 0.32，10 个
    /// 气泡的常见场景下线性尺寸约缩小 20%（sqrt(0.32/0.5)），留出更多空白，同一二三类的
    /// 相对大小关系不变。
    static func crowdScale(diameters: [Double], width: Double, height: Double, maxFill: Double = 0.32) -> Double {
        let canvas = width * height
        guard canvas > 0 else { return 1 }
        let fill = diameters.map { Double.pi * $0 * $0 / 4 }.reduce(0, +) / canvas
        return fill > maxFill ? (maxFill / fill).squareRoot() : 1
    }

    /// 画布上不能被气泡覆盖的矩形区域（左上角坐标 + 宽高），如叠在雷达上的指数切换按钮。
    struct Obstacle: Equatable {
        var x: Double
        var y: Double
        var width: Double
        var height: Double
    }

    /// 已摆好的气泡（中心 + 直径），供选方向时计算重叠。
    struct Placed: Equatable {
        var x: Double
        var y: Double
        var diameter: Double
    }

    /// 在半径固定的圆轨道上为一个气泡选方向（椭圆轨道 rx = ry 的特例，不加横向偏好）。
    static func bestAngle(
        radius: Double, diameter: Double, center: (x: Double, y: Double),
        placed: [Placed], preferred: Double = -Double.pi / 2, samples: Int = 72
    ) -> Double {
        guard radius > 0, !placed.isEmpty else { return preferred }
        return bestAngle(radiusX: radius, radiusY: radius, diameter: diameter, center: center,
                         placed: placed, preferred: preferred, horizontalBias: 0, samples: samples)
    }

    /// 在椭圆轨道（相对半径固定 = 时间）上为一个气泡选方向：采样一圈角度，取「与已摆气泡的
    /// 重叠 + 偏离水平方向的惩罚」最小的一个。
    ///
    /// horizontalBias：越偏上下扣分越多（按 sin² 计，单位与重叠平方一致），左右放得下就
    /// 优先左右，挤了才往上下放。并列时取离 preferred 最近的角度，保证确定性。
    static func bestAngle(
        radiusX: Double, radiusY: Double, diameter: Double, center: (x: Double, y: Double),
        placed: [Placed], preferred: Double = 0, horizontalBias: Double = 0.15, samples: Int = 72
    ) -> Double {
        guard radiusX > 0 || radiusY > 0 else { return preferred }
        let r = diameter / 2
        var best = preferred
        var bestScore = Double.infinity
        var bestDelta = Double.infinity
        for k in 0..<samples {
            let angle = preferred + 2 * Double.pi * Double(k) / Double(samples)
            let x = center.x + radiusX * cos(angle), y = center.y + radiusY * sin(angle)
            var score = horizontalBias * r * r * sin(angle) * sin(angle)
            for p in placed {
                let overlap = max(0, (diameter + p.diameter) / 2 - hypot(x - p.x, y - p.y))
                score += overlap * overlap
            }
            let delta = min(Double(k), Double(samples - k))
            if score < bestScore - 1e-9 || (abs(score - bestScore) <= 1e-9 && delta < bestDelta) {
                best = angle
                bestScore = score
                bestDelta = delta
            }
        }
        return best
    }
}

// MARK: - 参考环日期

extension RadarOrbitSpacing {
    private static let isoDay: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "UTC")
        return f
    }()

    /// 参考环上标的具体日期（yyyy.MM.dd）：查看日往前数 tradingDaysBack 个交易日。
    ///
    /// calendar 是已知交易日（最新在前，如雷达滚动窗口的各日），能覆盖的部分按它数，
    /// 节假日休市也数得准；查看日不在日历里（如示例日）或日历不够长时，从能定位到的
    /// 最早一天接着按工作日（跳过周六日）往前推。日期解析失败原样返回。
    static func ringDates(day: String, tradingDaysBack: [Int], calendar: [String]) -> [String] {
        func dotted(_ s: String) -> String { s.replacingOccurrences(of: "-", with: ".") }
        return tradingDaysBack.map { n in
            var remaining = n
            var current = day
            if let i = calendar.firstIndex(of: day) {
                let j = min(i + n, calendar.count - 1)
                current = calendar[j]
                remaining = n - (j - i)
            }
            guard remaining > 0 else { return dotted(current) }
            guard var date = isoDay.date(from: current) else { return dotted(current) }
            var cal = Calendar(identifier: .gregorian)
            cal.timeZone = TimeZone(identifier: "UTC")!
            while remaining > 0 {
                date = cal.date(byAdding: .day, value: -1, to: date)!
                let weekday = cal.component(.weekday, from: date)
                if weekday != 1 && weekday != 7 { remaining -= 1 }
            }
            return dotted(isoDay.string(from: date))
        }
    }
}
