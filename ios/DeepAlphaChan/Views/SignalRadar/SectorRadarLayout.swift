import Foundation

/// 扇区雷达的纯布局计算（不依赖 SwiftUI，可用 swiftc 单测，见 ios/Tests/SectorRadarLayoutTests.swift）。
///
/// 编码只用事实，不打分：
/// - 角度 = 行业。行业按当天相对大盘强弱排好序后，第 1 名在正上方，第 2、3 名分居右上 / 左上，依次往下，
///   越靠上越强；
/// - 半径 = 时间。当天新出现的离中心最近，越早越靠外（与旧版雷达同一条时间轴，最多 5 个交易日）；
/// - 每个行业最多画 `cap` 个气泡（取最新的），其余在行业标签上显示「+N」，点开行业面板看全部。
enum SectorRadarLayout {
    /// 没有行业标签的信号归入的扇区。
    static let otherKey = "_other"
    /// 全图气泡总数的大致上限：每个行业的名额 = 它 / 行业数（至少 1、至多 maxPerWedge）。
    static let maxTotal = 18
    static let maxPerWedge = 6
    /// 当天的气泡离中心的最小半径（占场半径比例）：扇区在中心汇成一点，太靠里会全挤在一起。
    static let innerRadius = 0.30
    static let outerRadius = 0.88
    /// 信号保留的最大交易日数（与后端 _MAX_SIGNAL_AGE_DAYS 一致）。
    static let horizonDays = 5

    struct Wedge: Equatable {
        let key: String
        /// 中线角（弧度）：0 = 正上方，顺时针为正。
        let center: Double
        let halfWidth: Double
        /// 该行业当天在场的信号总数 / 画出来的个数。
        let total: Int
        let shown: Int
        var hidden: Int { total - shown }
    }

    struct Slot: Equatable {
        /// 在输入数组里的下标。
        let index: Int
        let wedgeKey: String
        let angle: Double
        /// 归一化半径（占场半径比例，0~1）。
        let radius: Double
    }

    /// 每个扇区的名额。
    static func cap(wedgeCount n: Int) -> Int {
        guard n > 0 else { return 0 }
        return max(1, min(maxPerWedge, maxTotal / n))
    }

    /// 按名次给出扇区中线角：名次 0 在正上方，之后按「越靠上越先」排，同一高度先右后左。
    static func wedgeCenters(count n: Int) -> [Double] {
        guard n > 0 else { return [] }
        let step = 2 * Double.pi / Double(n)
        let slots = (0..<n).map { Double($0) * step }
        func rounded(_ v: Double) -> Double { (v * 1e9).rounded() / 1e9 }
        return slots.sorted { a, b in
            let ca = rounded(cos(a)), cb = rounded(cos(b))
            if ca != cb { return ca > cb }
            return rounded(sin(a)) > rounded(sin(b))
        }
    }

    /// 时间 → 归一化半径：当天 innerRadius，horizonDays 天及更早 outerRadius，中间线性。
    static func radius(daysAgo: Int) -> Double {
        let t = min(1, Double(max(0, daysAgo)) / Double(horizonDays))
        return innerRadius + (outerRadius - innerRadius) * t
    }

    /// 排出扇区与每个气泡的初始位置。
    ///
    /// - sectors: 每个信号的行业 key（nil = 没有行业标签，归入「其它」）；
    /// - ages: 每个信号距查看日的交易日数；
    /// - order: 行业从强到弱的 key（当天的行业强弱表）。不在表里的行业按出现先后排在后面，「其它」永远最后；
    /// - 输入信号应已按出现时间从新到旧排好（后端就是这个顺序），每个行业取前 cap 个即为最新的。
    static func plan(sectors: [String?], ages: [Int], order: [String]) -> (wedges: [Wedge], slots: [Slot]) {
        precondition(sectors.count == ages.count, "sectors 与 ages 一一对应")
        var members: [String: [Int]] = [:]
        var seen: [String] = []
        for (i, s) in sectors.enumerated() {
            let key = s ?? otherKey
            if members[key] == nil { seen.append(key) }
            members[key, default: []].append(i)
        }
        guard !seen.isEmpty else { return ([], []) }
        let known = order.filter { members[$0] != nil }
        let rest = seen.filter { !known.contains($0) && $0 != otherKey }
        let keys = known + rest + (members[otherKey] != nil ? [otherKey] : [])

        let centers = wedgeCenters(count: keys.count)
        let half = Double.pi / Double(keys.count)
        let perWedge = cap(wedgeCount: keys.count)
        var wedges: [Wedge] = []
        var slots: [Slot] = []
        for (rank, key) in keys.enumerated() {
            let all = members[key] ?? []
            let picked = Array(all.prefix(perWedge))
            wedges.append(Wedge(key: key, center: centers[rank], halfWidth: half, total: all.count, shown: picked.count))
            // 扇区内左右摊开：只有一个气泡时放中线；多个时在中线两侧 ±0.6 个半宽内均分
            let span = keys.count == 1 ? Double.pi * 0.9 : half * 0.6
            for (j, index) in picked.enumerated() {
                let offset = picked.count == 1 ? 0 : span * (Double(j) / Double(picked.count - 1) * 2 - 1)
                slots.append(Slot(index: index, wedgeKey: key, angle: centers[rank] + offset,
                                  radius: radius(daysAgo: ages[index])))
            }
        }
        return (wedges, slots)
    }

    /// 归一化极坐标 → 画布坐标（椭圆场：横半轴 hRad、纵半轴 vRad，圆心在画布中心）。
    static func point(angle: Double, radius: Double, width: Double, height: Double,
                      hRad: Double, vRad: Double) -> (x: Double, y: Double) {
        (width / 2 + radius * hRad * sin(angle), height / 2 - radius * vRad * cos(angle))
    }
}
