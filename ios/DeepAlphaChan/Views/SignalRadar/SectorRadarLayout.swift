import Foundation

/// 扇区雷达的纯布局计算（不依赖 SwiftUI，可用 swiftc 单测，见 ios/Tests/SectorRadarLayoutTests.swift）。
///
/// 编码只用事实，不打分：
/// - 角度 = 行业。行业按当天相对大盘强弱排好序后，第 1 名在正上方，第 2、3 名分居右上 / 左上，依次往下，
///   越靠上越强；
/// - 半径 = 时间。当天新出现的离中心最近，越早越靠外（与旧版雷达同一条时间轴，最多 5 个交易日）；
/// - 全图最多画 `maxTotal` 个气泡，按各行业的信号数分名额（`quotas`，每个行业至少 1 个、取最新的），
///   其余在行业标签上显示「+N」，点开行业面板看全部。
enum SectorRadarLayout {
    /// 没有行业标签的信号归入的扇区。
    static let otherKey = "_other"  // 与 RadarDay.otherSectorKey 同值（模型层不依赖布局）
    /// 全图气泡总数上限（行业数更多时每个行业仍至少 1 个）。标普 500 实测每天 36~98 个在场信号、约 10 个行业。
    static let maxTotal = 36
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

    /// 各扇区的名额（与 counts 一一对应）：先每个行业 1 个，剩下的名额按信号数成比例分（最高平均数法：
    /// 每次给「信号数 ÷ (已有名额 + 1)」最大的行业，并列给排在前面、即更强的行业），直到用完 maxTotal、
    /// 或都画全 / 到 maxPerWedge。名额跟着信号数走——画面上的疏密就是事实上的疏密。
    static func quotas(counts: [Int]) -> [Int] {
        var q = counts.map { min($0, 1) }
        let caps = counts.map { min($0, maxPerWedge) }
        var left = maxTotal - q.reduce(0, +)
        while left > 0 {
            var best: Int?
            var bestScore = 0.0
            for i in counts.indices where q[i] < caps[i] {
                let score = Double(counts[i]) / Double(q[i] + 1)
                if best == nil || score > bestScore { best = i; bestScore = score }
            }
            guard let i = best else { break }
            q[i] += 1
            left -= 1
        }
        return q
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
        let quota = quotas(counts: keys.map { members[$0]?.count ?? 0 })
        var wedges: [Wedge] = []
        var slots: [Slot] = []
        for (rank, key) in keys.enumerated() {
            let all = members[key] ?? []
            let picked = Array(all.prefix(quota[rank]))
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

    // MARK: - 在扇区内摆放

    /// 两个气泡允许重叠「较小直径 × 此比例」。适度叠一点（0.25 时压住的一侧离被盖气泡的中心仍有约 0.5 个半径，
    /// 代码 / 名称读得到），换来大小、远近、颜色深浅都能一起摆下，不至于大气泡被挤小、放不下的被折叠。
    static let overlapRatio = 0.25
    /// 相邻气泡之间留的空隙（pt），让每个气泡轮廓清楚。
    static let bubbleGap = 3.0
    /// 气泡离禁区（扇区标签、指数切换器）至少再留这么多（pt）：角上的「新 / 共振」角标会伸出圆外。
    static let obstacleMargin = 8.0
    /// 扇区内候选位置的最内圈（占场半径比例）：各扇区在圆心汇成一点，再往里谁都放不下。
    static let packInnerRadius = 0.16

    struct Rect: Equatable {
        var x: Double
        var y: Double
        var width: Double
        var height: Double
    }

    struct Placement: Equatable {
        let index: Int
        let wedgeKey: String
        let x: Double
        let y: Double
        let diameter: Double
    }

    /// 把 plan 里每个扇区的气泡直接摆进自己的扇区（圆心落在扇区角度内），不再「按时间摆好再推开」——
    /// 实测一天的信号大多是当日 / 前一日的，按时间半径会全挤在圆心，推开后就跑出了自己的扇区。
    ///
    /// - 每个扇区在 [packInnerRadius, 1] 之间按气泡大小铺一张候选网格，从里往外、同一圈从中线往两边；
    /// - 各扇区轮流放（第 1 个、第 2 个……），保证每个行业都先拿到靠里的位置；同一扇区里按 plan 的顺序
    ///   （最新的在前），所以扇区里越靠里越新；
    /// - 候选位置要在画布内、不压到禁区（扇区标签、指数切换器）、与已放的气泡重叠不超过 overlapRatio；
    ///   一个扇区找不到位置就停，余下的计入「+N」。
    /// - radiusRange 只在这段归一化半径里摆；existing 是之前已摆好的气泡（只避让、不在返回值里）。
    static func pack(
        plan: (wedges: [Wedge], slots: [Slot]), diameters: [Double], width w: Double, height h: Double,
        hRad: Double, vRad: Double, edge: Double, obstacles: [Rect], outwardOnly: Bool = true,
        radiusRange: ClosedRange<Double>? = nil, existing: [Placement] = []
    ) -> (wedges: [Wedge], placements: [Placement]) {
        let meanRadius = ((hRad * hRad + vRad * vRad) / 2).squareRoot()
        guard meanRadius > 0 else { return (plan.wedges.map { $0.with(shown: 0) }, []) }
        var queues: [String: [Int]] = [:]
        for slot in plan.slots { queues[slot.wedgeKey, default: []].append(slot.index) }

        // 每个扇区的候选网格（按该扇区气泡的最大直径定间距）
        var candidates: [String: [(angle: Double, radius: Double)]] = [:]
        for wedge in plan.wedges {
            let ds = (queues[wedge.key] ?? []).map { diameters[$0] }
            // 网格比气泡密（径向 0.4 个、横向 0.6 个直径一格），能不能放由 fits 逐个判断，空隙利用得更满
            let size = max(ds.max() ?? 44, 1) / meanRadius
            let step = size * 0.4
            var list: [(angle: Double, radius: Double)] = []
            // radiusRange：只在这一圈带里摆（同心环按时间分带：当日 / 3 天内 / 7 天内）
            var r = radiusRange?.lowerBound ?? packInnerRadius
            while r <= (radiusRange?.upperBound ?? 1.0) + 1e-9 {
                let usable = wedge.halfWidth * 0.92
                let across = Int((2 * usable * r) / (size * 0.6))
                if across <= 0 {
                    list.append((wedge.center, r))
                } else {
                    var row: [Double] = []
                    for k in 0...across { row.append(-usable + 2 * usable * Double(k) / Double(across)) }
                    for off in row.sorted(by: { abs($0) < abs($1) }) { list.append((wedge.center + off, r)) }
                }
                r += step
            }
            candidates[wedge.key] = list
        }

        func fits(_ x: Double, _ y: Double, _ d: Double, _ placed: [Placement]) -> Bool {
            let rr = d / 2 + edge
            guard x >= rr - 1e-9, x <= w - rr + 1e-9, y >= rr - 1e-9, y <= h - rr + 1e-9 else { return false }
            for o in obstacles {
                let nx = min(max(x, o.x), o.x + o.width), ny = min(max(y, o.y), o.y + o.height)
                if hypot(x - nx, y - ny) < d / 2 + obstacleMargin { return false }
            }
            // existing：之前几圈带已摆好的气泡，同样不能压
            for p in existing + placed {
                let need = (d + p.diameter) / 2 + bubbleGap - overlapRatio * min(d, p.diameter)
                if hypot(x - p.x, y - p.y) < need { return false }
            }
            return true
        }

        // 第一轮先放可用位置最少的扇区（窄扇区、贴着标签的扇区），保证每个行业都尽量至少画一个；
        // 之后各轮按强弱顺序。
        func freeSpots(_ wedge: Wedge) -> Int {
            guard let first = queues[wedge.key]?.first else { return 0 }
            return (candidates[wedge.key] ?? []).filter { c in
                let p = point(angle: c.angle, radius: c.radius, width: w, height: h, hRad: hRad, vRad: vRad)
                return fits(p.x, p.y, diameters[first], [])
            }.count
        }
        let firstRound = plan.wedges.enumerated()
            .map { (rank: $0.offset, wedge: $0.element, free: freeSpots($0.element)) }
            .sorted { ($0.free, $0.rank) < ($1.free, $1.rank) }
            .map(\.wedge)

        var placed: [Placement] = []
        var shown: [String: Int] = [:]
        var closed: Set<String> = []
        var round = 0
        var progressed = true
        while progressed {
            progressed = false
            for wedge in (round == 0 ? firstRound : plan.wedges) where !closed.contains(wedge.key) {
                let queue = queues[wedge.key] ?? []
                guard round < queue.count else { continue }
                let index = queue[round]
                let d = diameters[index]
                var spots = candidates[wedge.key] ?? []
                // 只往外找：同一扇区里后放的（更早的信号）不会比先放的更靠里。
                // outwardOnly=false（整圆一个扇区）时允许填空隙：否则一个气泡落到外圈后，其余只能更往外，很快就放不下
                let floor = !outwardOnly ? 0 : placed.last(where: { $0.wedgeKey == wedge.key }).map {
                    hypot(($0.x - w / 2) / hRad, ($0.y - h / 2) / vRad)
                } ?? 0
                var found: Int?
                for (k, c) in spots.enumerated() where c.radius >= floor - 1e-9 {
                    let p = point(angle: c.angle, radius: c.radius, width: w, height: h, hRad: hRad, vRad: vRad)
                    if fits(p.x, p.y, d, placed) {
                        found = k
                        placed.append(Placement(index: index, wedgeKey: wedge.key, x: p.x, y: p.y, diameter: d))
                        break
                    }
                }
                if let k = found {
                    spots.remove(at: k)
                    candidates[wedge.key] = spots
                    shown[wedge.key, default: 0] += 1
                    progressed = true
                } else {
                    closed.insert(wedge.key)
                }
            }
            round += 1
        }
        return (plan.wedges.map { $0.with(shown: shown[$0.key] ?? 0) }, placed)
    }
}

extension SectorRadarLayout.Wedge {
    /// 实际画出的个数（其余计入「+N」）。
    func with(shown: Int) -> SectorRadarLayout.Wedge {
        SectorRadarLayout.Wedge(key: key, center: center, halfWidth: halfWidth, total: total, shown: shown)
    }
}
