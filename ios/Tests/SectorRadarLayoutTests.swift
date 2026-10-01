import Foundation

/// 用 swiftc 与 SectorRadarLayout.swift 一起编译运行，无需启动模拟器（见 run-sector-radar-tests.sh）。
@main
struct SectorRadarLayoutTests {
    static func near(_ a: Double, _ b: Double) -> Bool { abs(a - b) < 1e-9 }

    static func main() {
        testWedgeCentersTopFirstThenRightLeft()
        testCapShrinksWithMoreSectors()
        testPlanKeepsNewestAndCountsHidden()
        testOrderAndOtherBucket()
        testRadiusFollowsTime()
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

    static func testCapShrinksWithMoreSectors() {
        assert(SectorRadarLayout.cap(wedgeCount: 0) == 0)
        assert(SectorRadarLayout.cap(wedgeCount: 1) == 6)
        assert(SectorRadarLayout.cap(wedgeCount: 6) == 3)
        assert(SectorRadarLayout.cap(wedgeCount: 12) == 1)
        assert(SectorRadarLayout.cap(wedgeCount: 30) == 1, "行业再多每个也至少画一个")
    }

    static func testPlanKeepsNewestAndCountsHidden() {
        // 6 个行业，每个 3 名额；semis 有 5 个（输入已按时间从新到旧）
        let keys = ["semis", "semis", "semis", "semis", "semis", "a", "b", "c", "d", "e"]
        let ages = [0, 0, 1, 2, 4, 0, 0, 0, 0, 0]
        let (wedges, slots) = SectorRadarLayout.plan(
            sectors: keys, ages: ages, order: ["semis", "a", "b", "c", "d", "e"])
        assert(wedges.count == 6)
        let semis = wedges[0]
        assert(semis.key == "semis" && semis.total == 5 && semis.shown == 3 && semis.hidden == 2)
        assert(near(semis.center, 0), "最强行业在正上方")
        let semiSlots = slots.filter { $0.wedgeKey == "semis" }.map(\.index)
        assert(semiSlots == [0, 1, 2], "取最新的三个：\(semiSlots)")
        assert(slots.count == 8)
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
}
