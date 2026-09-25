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
    /// 时间 → 归一化半径，对应「今天 / 3 天 / 1 周」三个等距环（1/3、2/3、1）：
    /// 今天在最内环以内（圆心），1～3 天前在第一、二环之间，4～7 天前在第二、三环之间，
    /// 各区间内按天均匀分布；后端信号本身最多只保留 7 天（见 _MAX_SIGNAL_AGE_DAYS），
    /// 7 天封顶只是兜底，正常不会有更早的信号传进来。
    static func timeRadius(daysAgo: Int) -> Double {
        let d = max(0, daysAgo)
        if d == 0 { return 0 }
        if d <= 3 { return (1.0 + Double(d - 1) / 2.0) / 3.0 }
        return (2.0 + min(1.0, Double(d - 3) / 4.0)) / 3.0
    }

    /// 时间 → 气泡尺寸系数：越远越小，按天连续递减（当天 1.0，7 天及更早 0.55），
    /// horizon 与后端信号保留上限（7 天）对齐。与强弱对应的直径相乘。
    static func timeSizeFactor(daysAgo: Int, horizon: Int = 7, minFactor: Double = 0.55) -> Double {
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
