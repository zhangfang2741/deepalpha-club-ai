import Foundation
import Testing
import SwiftData
@testable import DeepAlphaBaZiCore

func sampleChart() -> BaziChartResponse {
    BaziChartResponse(
        requestId: "x", hourKnown: true, solarDate: "1990-05-15",
        lunarDate: "一九九〇年四月廿一", trueSolarTime: "1990-05-15T14:16:00",
        trueSolarTimeApplied: true,
        yearPillar: Pillar(gan: "庚", zhi: "午", naYin: "路旁土", shiShenGan: "比肩", shiShenZhi: ["正官"]),
        monthPillar: Pillar(gan: "辛", zhi: "巳", naYin: "白蜡金", shiShenGan: "劫财", shiShenZhi: ["七杀"]),
        dayPillar: Pillar(gan: "庚", zhi: "辰", naYin: "白蜡金", shiShenGan: "元男", shiShenZhi: ["偏印"]),
        timePillar: Pillar(gan: "癸", zhi: "未", naYin: "杨柳木", shiShenGan: "伤官", shiShenZhi: ["正印"]),
        wuXingDistribution: ["jin": 3, "mu": 0, "shui": 1, "huo": 2, "tu": 2],
        daYun: [DaYunStep(ganZhi: "壬午", startAge: 8, endAge: 17)],
        liuNianGanZhi: "甲辰")
}

@Suite("BaziLocalStore")
struct BaziLocalStoreTests {
    func makeStore() throws -> BaziLocalStore {
        let config = ModelConfiguration(isStoredInMemoryOnly: true)
        let container = try ModelContainer(for: BirthProfile.self, DailyFortuneCache.self,
                                           configurations: config)
        return BaziLocalStore(modelContainer: container)
    }

    @Test("没有档案时 loadProfile 返回 nil")
    func loadProfileEmpty() async throws {
        let store = try makeStore()
        let profile = try await store.loadProfile()
        #expect(profile == nil)
    }

    @Test("saveProfile 后 loadProfile 能读回同一条记录")
    func saveAndLoadProfile() async throws {
        let store = try makeStore()
        try await store.saveProfile(
            birthDate: "1990-05-15", birthTime: "14:30:00", birthCity: "北京",
            gender: "male", chart: sampleChart())

        let profile = try await store.loadProfile()
        #expect(profile?.birthDate == "1990-05-15")
        #expect(profile?.birthCity == "北京")
        #expect(profile?.chart.yearPillar.gan == "庚")
    }

    @Test("重复 saveProfile 覆盖而不是新增一条")
    func saveProfileOverwrites() async throws {
        let store = try makeStore()
        try await store.saveProfile(
            birthDate: "1990-05-15", birthTime: "14:30:00", birthCity: "北京",
            gender: "male", chart: sampleChart())
        try await store.saveProfile(
            birthDate: "1991-06-20", birthTime: nil, birthCity: "上海",
            gender: "female", chart: sampleChart())

        let profile = try await store.loadProfile()
        #expect(profile?.birthDate == "1991-06-20")
        #expect(profile?.birthCity == "上海")
    }

    @Test("今日运势缓存：没有对应日期时返回 nil")
    func loadFortuneMiss() async throws {
        let store = try makeStore()
        let text = try await store.loadFortune(dateKey: "2026-09-05")
        #expect(text == nil)
    }

    @Test("今日运势缓存：写入后按日期能读回；不同日期互不影响")
    func saveAndLoadFortune() async throws {
        let store = try makeStore()
        try await store.saveTodayFortune(dateKey: "2026-09-05", text: "今日宜签约")
        try await store.saveTodayFortune(dateKey: "2026-09-06", text: "今日宜远行")

        #expect(try await store.loadFortune(dateKey: "2026-09-05") == "今日宜签约")
        #expect(try await store.loadFortune(dateKey: "2026-09-06") == "今日宜远行")
    }

    @Test("同日期重复写入今日运势会覆盖而不是新增")
    func saveFortuneOverwritesSameDay() async throws {
        let store = try makeStore()
        try await store.saveTodayFortune(dateKey: "2026-09-05", text: "第一次")
        try await store.saveTodayFortune(dateKey: "2026-09-05", text: "第二次")
        #expect(try await store.loadFortune(dateKey: "2026-09-05") == "第二次")
    }
}
