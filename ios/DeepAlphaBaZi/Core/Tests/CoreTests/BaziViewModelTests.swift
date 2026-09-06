import Foundation
import Testing
import SwiftData
@testable import DeepAlphaBaZiCore

/// 测试用的可控挂起点：让某次异步调用卡在半途，等测试确认了"重入调用已经被 guard 挡住"
/// 之后再放行，比用 Task.sleep 卡时间片更可靠（不依赖具体延时长短）。
actor Gate {
    private var isOpen = false
    private var continuation: CheckedContinuation<Void, Never>?

    func wait() async {
        if isOpen { return }
        await withCheckedContinuation { continuation = $0 }
    }

    func open() {
        isOpen = true
        continuation?.resume()
        continuation = nil
    }
}

final class MockBaziService: BaziServicing, @unchecked Sendable {
    var chartResult: BaziChartResponse?
    var chartError: Error?
    var interpretationResult: InterpretationResponse?
    var interpretationError: Error?
    private(set) var interpretationCallCount = 0
    private(set) var chartCallCount = 0
    var chartGate: Gate?
    var interpretationGate: Gate?

    func getChart(_ request: BaziChartRequest) async throws -> BaziChartResponse {
        chartCallCount += 1
        if let chartGate { await chartGate.wait() }
        if let chartError { throw chartError }
        return chartResult ?? sampleChart()
    }

    func getInterpretation(_ request: InterpretationRequest) async throws -> InterpretationResponse {
        interpretationCallCount += 1
        if let interpretationGate { await interpretationGate.wait() }
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

    @Test("submitBirthInfo 重入保护：提交中再次调用不会并发打两次 /chart")
    func submitBirthInfoReentrancyGuard() async throws {
        let store = try makeStore()
        let service = MockBaziService()
        let gate = Gate()
        service.chartGate = gate
        let vm = BaziViewModel(service: service, store: store)

        let firstTask = Task { await vm.submitBirthInfo(
            birthDate: "1990-05-15", birthTime: "14:30:00", birthCity: "北京", gender: "male") }
        while service.chartCallCount == 0 { await Task.yield() }
        #expect(vm.isSubmittingBirthInfo == true)

        // 重入：此时第一次调用还卡在 gate 里没返回，第二次调用应该被 guard 直接挡掉
        await vm.submitBirthInfo(
            birthDate: "1991-06-20", birthTime: nil, birthCity: "上海", gender: "female")
        #expect(service.chartCallCount == 1)

        await gate.open()
        await firstTask.value
        #expect(vm.profile?.birthCity == "北京")
    }

    @Test("loadDailyFortuneIfNeeded 重入保护：加载中再次调用不会并发打两次接口")
    func loadDailyFortuneReentrancyGuard() async throws {
        let store = try makeStore()
        let service = MockBaziService()
        let gate = Gate()
        service.interpretationGate = gate
        service.interpretationResult = InterpretationResponse(requestId: "x", text: "今日宜签约")
        let vm = BaziViewModel(service: service, store: store, todayKeyProvider: { "2026-09-05" })
        await vm.submitBirthInfo(
            birthDate: "1990-05-15", birthTime: "14:30:00", birthCity: "北京", gender: "male")

        let firstTask = Task { await vm.loadDailyFortuneIfNeeded() }
        while service.interpretationCallCount == 0 { await Task.yield() }
        #expect(vm.isLoadingFortune == true)

        // 重入：第一次调用还卡在 gate 里，第二次调用应该被 guard 直接挡掉，不再打接口
        await vm.loadDailyFortuneIfNeeded()
        #expect(service.interpretationCallCount == 1)

        await gate.open()
        await firstTask.value
        #expect(vm.dailyFortuneText == "今日宜签约")
    }

    @Test("loadDailyFortuneIfNeeded：缓存命中时会清掉上一次遗留的 fortuneError")
    func loadDailyFortuneClearsStaleErrorOnCacheHit() async throws {
        let store = try makeStore()
        let service = MockBaziService()
        let vm = BaziViewModel(service: service, store: store, todayKeyProvider: { "2026-09-05" })
        await vm.submitBirthInfo(
            birthDate: "1990-05-15", birthTime: "14:30:00", birthCity: "北京", gender: "male")

        // 第一次：无缓存，接口失败，留下一条 fortuneError
        service.interpretationError = APIError.network
        await vm.loadDailyFortuneIfNeeded()
        #expect(vm.fortuneError != nil)

        // 第二次：缓存已经命中（模拟另一路径写入了缓存），不应该还残留上一次的错误
        try await store.saveTodayFortune(dateKey: "2026-09-05", text: "今日宜远行")
        await vm.loadDailyFortuneIfNeeded()
        #expect(vm.fortuneError == nil)
        #expect(vm.dailyFortuneText == "今日宜远行")
    }
}
