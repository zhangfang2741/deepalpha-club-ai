import Foundation
import Testing
import SwiftData
@testable import DeepAlphaBaZiCore

final class MockBaziService: BaziServicing, @unchecked Sendable {
    var chartResult: BaziChartResponse?
    var chartError: Error?
    var interpretationResult: InterpretationResponse?
    var interpretationError: Error?
    private(set) var interpretationCallCount = 0

    func getChart(_ request: BaziChartRequest) async throws -> BaziChartResponse {
        if let chartError { throw chartError }
        return chartResult ?? sampleChart()
    }

    func getInterpretation(_ request: InterpretationRequest) async throws -> InterpretationResponse {
        interpretationCallCount += 1
        if let interpretationError { throw interpretationError }
        return interpretationResult ?? InterpretationResponse(requestId: "x", text: "默认今日运势")
    }
}

@MainActor
@Suite("BaziViewModel")
struct BaziViewModelTests {
    func makeStore() throws -> BaziLocalStore {
        let config = ModelConfiguration(isStoredInMemoryOnly: true)
        let container = try ModelContainer(for: BirthProfile.self, DailyFortuneCache.self,
                                           configurations: config)
        return BaziLocalStore(modelContainer: container)
    }

    @Test("没有本地档案时，loadLocalProfile 后 profile 仍是 nil（新用户态）")
    func loadLocalProfileEmpty() async throws {
        let store = try makeStore()
        let vm = BaziViewModel(service: MockBaziService(), store: store)
        await vm.loadLocalProfile()
        #expect(vm.profile == nil)
    }

    @Test("submitBirthInfo 成功：写入本地档案，profile 变为已排盘态")
    func submitBirthInfoSuccess() async throws {
        let store = try makeStore()
        let service = MockBaziService()
        let vm = BaziViewModel(service: service, store: store)

        await vm.submitBirthInfo(
            birthDate: "1990-05-15", birthTime: "14:30:00", birthCity: "北京", gender: "male")

        #expect(vm.formError == nil)
        #expect(vm.profile?.birthDate == "1990-05-15")
        #expect(vm.profile?.chart.yearPillar.gan == "庚")

        let reloaded = try await store.loadProfile()
        #expect(reloaded?.birthCity == "北京")
    }

    @Test("submitBirthInfo 失败：不写入本地，formError 展示后端消息")
    func submitBirthInfoFailure() async throws {
        let store = try makeStore()
        let service = MockBaziService()
        service.chartError = APIError.validation("出生日期不能晚于今天")
        let vm = BaziViewModel(service: service, store: store)

        await vm.submitBirthInfo(
            birthDate: "2999-01-01", birthTime: nil, birthCity: "北京", gender: "male")

        #expect(vm.formError == "出生日期不能晚于今天")
        #expect(vm.profile == nil)
        let reloaded = try await store.loadProfile()
        #expect(reloaded == nil)
    }

    @Test("loadDailyFortuneIfNeeded：本地无缓存时调用接口并写入缓存")
    func loadDailyFortuneFetchesAndCaches() async throws {
        let store = try makeStore()
        let service = MockBaziService()
        service.interpretationResult = InterpretationResponse(requestId: "x", text: "今日宜签约")
        let vm = BaziViewModel(service: service, store: store, todayKeyProvider: { "2026-09-05" })

        await vm.submitBirthInfo(
            birthDate: "1990-05-15", birthTime: "14:30:00", birthCity: "北京", gender: "male")
        await vm.loadDailyFortuneIfNeeded()

        #expect(vm.dailyFortuneText == "今日宜签约")
        #expect(service.interpretationCallCount == 1)
        #expect(try await store.loadFortune(dateKey: "2026-09-05") == "今日宜签约")
    }

    @Test("loadDailyFortuneIfNeeded：本地已有当天缓存时不重复调用接口")
    func loadDailyFortuneUsesCacheWithoutCallingAPI() async throws {
        let store = try makeStore()
        try await store.saveTodayFortune(dateKey: "2026-09-05", text: "缓存的运势")
        let service = MockBaziService()
        let vm = BaziViewModel(service: service, store: store, todayKeyProvider: { "2026-09-05" })

        await vm.submitBirthInfo(
            birthDate: "1990-05-15", birthTime: "14:30:00", birthCity: "北京", gender: "male")
        await vm.loadDailyFortuneIfNeeded()

        #expect(vm.dailyFortuneText == "缓存的运势")
        #expect(service.interpretationCallCount == 0)
    }

    @Test("loadDailyFortuneIfNeeded：还没有 profile 时直接返回，不调用接口")
    func loadDailyFortuneNoProfileNoop() async throws {
        let store = try makeStore()
        let service = MockBaziService()
        let vm = BaziViewModel(service: service, store: store)

        await vm.loadDailyFortuneIfNeeded()

        #expect(vm.dailyFortuneText == nil)
        #expect(service.interpretationCallCount == 0)
    }
}
