import Foundation

/// 用 swiftc 与 SectorRadarLayout.swift 一起编译运行，无需启动模拟器（见 run-sector-radar-tests.sh）。
@main
struct SectorRadarLayoutTests {
    static func near(_ a: Double, _ b: Double) -> Bool { abs(a - b) < 1e-9 }

    static func main() {
        testWedgeCentersTopFirstThenRightLeft()
        testQuotasFollowSignalCounts()
        testPlanKeepsNewestAndCountsHidden()
        testOrderAndOtherBucket()
        testRadiusFollowsTime()
        testPackKeepsBubblesInTheirWedgeWithoutOverlap()
        testPackHidesWhatDoesNotFitAndAvoidsObstacles()
        print("SectorRadarLayoutTests: all passed")
    }

    static func testWedgeCentersTopFirstThenRightLeft() {
        assert(SectorRadarLayout.wedgeCenters(count: 0).isEmpty)
        assert(SectorRadarLayout.wedgeCenters(count: 1) == [0])
        let six = SectorRadarLayout.wedgeCenters(count: 6)
        let step = Double.pi / 3
        // 第 1 名正上方；第 2、3 名右上 / 左上；第 4、5 名右下 / 左下；第 6 名正下方
        let expected = [0, step, 5 * step, 2 * step, 4 * step, 3 * step]
        assert(six.count == 6)
        for (a, b) in zip(six, expected) { assert(near(a, b), "六个扇区的名次位置不对：\(six)") }
        let four = SectorRadarLayout.wedgeCenters(count: 4)
        assert(near(four[0], 0) && near(four[1], .pi / 2) && near(four[2], 3 * .pi / 2) && near(four[3], .pi))
    }

    static func testQuotasFollowSignalCounts() {
        assert(SectorRadarLayout.quotas(counts: []).isEmpty)
        assert(SectorRadarLayout.quotas(counts: [3]) == [3], "信号少于名额就全画")
        assert(SectorRadarLayout.quotas(counts: [40]) == [SectorRadarLayout.maxPerWedge])
        // 2026-09-30 标普 500 实测：10 个行业 98 个信号。总名额用满，每个行业至少 1 个，多的行业多画
        let real = [25, 17, 14, 10, 7, 6, 6, 6, 5, 2]
        let q = SectorRadarLayout.quotas(counts: real)
        assert(q.reduce(0, +) == SectorRadarLayout.maxTotal, "\(q)")
        assert(q.allSatisfy { $0 >= 1 } && zip(q, real).allSatisfy { $0 <= $1 })
        assert(q[0] >= 4 && q[0] >= q[3] && q[3] >= q[9], "按信号多少分名额：\(q)")
        // 成比例（36 × 信号数 / 98，单个行业封顶 6）：10 个信号的行业不能只画 1 个
        assert(q == [6, 6, 6, 5, 3, 3, 2, 2, 2, 1], "名额要按比例分，不能都给最大的几个：\(q)")
        assert(q.allSatisfy { $0 <= SectorRadarLayout.maxPerWedge })
        // 行业比名额还多：每个行业 1 个
        assert(SectorRadarLayout.quotas(counts: Array(repeating: 3, count: 40)) == Array(repeating: 1, count: 40))
    }

    static func testPlanKeepsNewestAndCountsHidden() {
        // semis 有 maxPerWedge + 2 个（输入已按时间从新到旧），其余 5 个行业各 1 个
        let extra = SectorRadarLayout.maxPerWedge + 2
        let keys = Array(repeating: "semis", count: extra) + ["a", "b", "c", "d", "e"]
        let ages = Array(0..<extra) + [0, 0, 0, 0, 0]
        let (wedges, slots) = SectorRadarLayout.plan(
            sectors: keys, ages: ages, order: ["semis", "a", "b", "c", "d", "e"])
        assert(wedges.count == 6)
        let semis = wedges[0]
        assert(semis.key == "semis" && semis.total == extra && semis.shown == SectorRadarLayout.maxPerWedge
               && semis.hidden == 2)
        assert(near(semis.center, 0), "最强行业在正上方")
        let semiSlots = slots.filter { $0.wedgeKey == "semis" }.map(\.index)
        assert(semiSlots == Array(0..<SectorRadarLayout.maxPerWedge), "取最新的几个：\(semiSlots)")
        assert(slots.count == SectorRadarLayout.maxPerWedge + 5)
        for s in slots {
            let w = wedges.first { $0.key == s.wedgeKey }!
            assert(abs(s.angle - w.center) <= w.halfWidth + 1e-9, "气泡初始角度落在自己的扇区内")
        }
    }

    static func testOrderAndOtherBucket() {
        // 强弱表里没有的行业排在已知行业之后，没有行业标签的归入「其它」且永远最后
        let (wedges, _) = SectorRadarLayout.plan(
            sectors: [nil, "x", "b", "a"], ages: [0, 0, 0, 0], order: ["a", "b"])
        assert(wedges.map(\.key) == ["a", "b", "x", SectorRadarLayout.otherKey], "\(wedges.map(\.key))")
        let (none, noSlots) = SectorRadarLayout.plan(sectors: [], ages: [], order: ["a"])
        assert(none.isEmpty && noSlots.isEmpty)
    }

    static func testRadiusFollowsTime() {
        assert(near(SectorRadarLayout.radius(daysAgo: 0), SectorRadarLayout.innerRadius))
        assert(near(SectorRadarLayout.radius(daysAgo: 5), SectorRadarLayout.outerRadius))
        assert(near(SectorRadarLayout.radius(daysAgo: 9), SectorRadarLayout.outerRadius))
        assert(SectorRadarLayout.radius(daysAgo: 1) < SectorRadarLayout.radius(daysAgo: 3))
        let p = SectorRadarLayout.point(angle: 0, radius: 1, width: 200, height: 100, hRad: 80, vRad: 40)
        assert(near(p.x, 100) && near(p.y, 10), "角度 0 在正上方")
    }

    /// 2026-09-30 标普 500 实测分布（98 个信号、11 个行业，绝大多数是当日 / 前一日的）。
    static func realPlan() -> (sectors: [String?], ages: [Int], order: [String]) {
        let counts: [(String, Int)] = [("technology", 25), ("industrials", 17), ("healthcare", 14), ("discretionary", 10),
                                       ("financials", 7), ("utilities", 6), ("communication", 6),
                                       ("realestate", 6), ("staples", 5), ("materials", 2)]
        var sectors: [String?] = []
        var ages: [Int] = []
        for (key, n) in counts {
            for j in 0..<n { sectors.append(key); ages.append(j % 3 == 0 ? 1 : 0) }
        }
        let order = ["technology", "industrials", "communication", "healthcare", "financials",
                     "discretionary", "utilities", "materials", "realestate", "staples", "energy"]
        return (sectors, ages, order)
    }

    static func testPackKeepsBubblesInTheirWedgeWithoutOverlap() {
        let real = realPlan()
        let plan = SectorRadarLayout.plan(sectors: real.sectors, ages: real.ages, order: real.order)
        let d = Array(repeating: 44.0, count: real.sectors.count)
        let (w, h) = (366.0, 330.0)
        let (wedges, placed) = SectorRadarLayout.pack(plan: plan, diameters: d, width: w, height: h,
                                                      hRad: 165, vRad: 147, edge: 12, obstacles: [])
        assert(placed.count >= 14, "真实分布下至少要画得下十几个：\(placed.count)")
        assert(Set(placed.map(\.wedgeKey)).count == 11, "每个有信号的行业至少画一个")
        for p in placed {
            let wd = wedges.first { $0.key == p.wedgeKey }!
            // 气泡圆心落在自己的扇区里（角度按椭圆参数角算）
            var a = atan2((p.x - w / 2) / 165, -(p.y - h / 2) / 147) - wd.center
            while a > .pi { a -= 2 * .pi }
            while a < -.pi { a += 2 * .pi }
            assert(abs(a) <= wd.halfWidth + 1e-6, "\(p.wedgeKey) 的气泡跑出了自己的扇区")
            assert(p.x >= 22 + 12 - 1e-6 && p.x <= w - 22 - 12 + 1e-6 && p.y >= 22 + 12 - 1e-6 && p.y <= h - 22 - 12 + 1e-6)
        }
        for i in placed.indices {
            for j in placed.indices where j > i {
                let dist = hypot(placed[i].x - placed[j].x, placed[i].y - placed[j].y)
                assert(dist >= 44 * (1 - SectorRadarLayout.overlapRatio) - 1e-6, "气泡压得太多")
            }
        }
        // 同一行业里越新越靠里；扇区标签的「+N」与实际画出的个数一致
        for wd in wedges {
            let mine = placed.filter { $0.wedgeKey == wd.key }
            assert(mine.count == wd.shown && wd.shown + wd.hidden == wd.total)
            let r = mine.map { hypot(($0.x - w / 2) / 165, ($0.y - h / 2) / 147) }
            for k in r.indices.dropFirst() { assert(r[k] >= r[k - 1] - 1e-6, "\(wd.key) 里新的应在里面") }
        }
    }

    static func testPackHidesWhatDoesNotFitAndAvoidsObstacles() {
        let plan = SectorRadarLayout.plan(sectors: Array(repeating: "a", count: 6), ages: Array(repeating: 0, count: 6),
                                          order: ["a"])
        let block = SectorRadarLayout.Rect(x: 0, y: 0, width: 200, height: 60)
        let (wedges, placed) = SectorRadarLayout.pack(plan: plan, diameters: Array(repeating: 80, count: 6),
                                                      width: 200, height: 200, hRad: 82, vRad: 82, edge: 4,
                                                      obstacles: [block])
        assert(wedges[0].shown == placed.count && wedges[0].hidden == 6 - placed.count)
        assert(placed.count < 6, "放不下的进「+N」")
        for p in placed { assert(p.y - 40 >= 60 - 1e-6, "不压到禁区（标签 / 切换器）") }
    }
}
