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
