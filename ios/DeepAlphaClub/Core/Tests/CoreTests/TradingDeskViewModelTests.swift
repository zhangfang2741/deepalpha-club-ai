import Foundation
import os
import Testing
@testable import DeepAlphaCore

// MARK: - 测试基建

/// mock service：createRun/control 可编程，stream 按调用次数走脚本。
/// NSLock 在 async 上下文被 Swift 6 禁用，用 OSAllocatedUnfairLock。
final class MockDeskService: TradingDeskServicing, @unchecked Sendable {
    var createRunResult: String = "run-1"
    var createRunError: Error?
    var controlError: Error?
    var listRunsResult: RunListResponse?
    var listRunsError: Error?
    var getRunResult: RunDetailResponse?
    var getRunError: Error?

    private struct Store {
        var controls: [(ControlAction, String?)] = []
        var createRunCalls = 0
        var streamCalls = 0
    }
    private let store = OSAllocatedUnfairLock(initialState: Store())

    var controls: [(ControlAction, String?)] { store.withLock(\.controls) }
    var createRunCalls: Int { store.withLock(\.createRunCalls) }
    var streamCallCount: Int { store.withLock(\.streamCalls) }

    /// 每次 stream 调用返回的流工厂（数组按次序消费，越界用最后一个）。
    var streamScripts: [@Sendable (Int) -> AsyncThrowingStream<SseFrame, Error>] = []

    func createRun(ticker: String) async throws -> String {
        if let e = createRunError { throw e }
        store.withLock { $0.createRunCalls += 1 }
        return createRunResult
    }
    func control(runId: String, action: ControlAction, text: String?) async throws {
        if let e = controlError { throw e }
        store.withLock { $0.controls.append((action, text)) }
    }
    func listRuns(ticker: String?, limit: Int, offset: Int) async throws -> RunListResponse {
        if let e = listRunsError { throw e }
        return listRunsResult ?? RunListResponse(runs: [])
    }
    func getRun(runId: String) async throws -> RunDetailResponse {
        if let e = getRunError { throw e }
        if let r = getRunResult { return r }
        throw APIError.notFound
    }
    func stream(runId: String, lastEventId: String?) -> AsyncThrowingStream<SseFrame, Error> {
        let scripts = streamScripts
        let (n, factory) = store.withLock { s -> (Int, @Sendable (Int) -> AsyncThrowingStream<SseFrame, Error>) in
            let n = s.streamCalls
            s.streamCalls += 1
            return (n, scripts[min(n, scripts.count - 1)])
        }
        return factory(n)
    }
}

func frames(_ events: [TradingDeskEvent]) -> AsyncThrowingStream<SseFrame, Error> {
    AsyncThrowingStream { cont in
        for e in events { cont.yield(SseFrame(id: "id-\(e.seq)", event: e)) }
        cont.finish()
    }
}

func failingStream() -> AsyncThrowingStream<SseFrame, Error> {
    AsyncThrowingStream { $0.finish(throwing: URLError(.networkConnectionLost)) }
}

/// run.started 事件的常用载荷。
func startedEvent(_ seq: Int, ticker: String = "NVDA") -> TradingDeskEvent {
    ev(.runStarted, seq: seq, data: [
        "ticker": JSONValue.string(ticker), "trade_date": "2026-08-30", "engine": "e",
        "capabilities": [:], "stages": []])
}

/// 测试端：等待直到条件满足或超时（重连循环是后台 Task，无法直接 await）。
@MainActor
func waitUntil(_ condition: @MainActor () -> Bool,
               timeout: Duration = .seconds(2)) async -> Bool {
    let start = ContinuousClock.now
    while ContinuousClock.now - start < timeout {
        if condition() { return true }
        try? await Task.sleep(for: .milliseconds(10))
    }
    return condition()
}

// MARK: - 测试

@MainActor
@Suite("TradingDeskViewModel")
struct TradingDeskViewModelTests {
    func makeVM(_ service: MockDeskService) -> TradingDeskViewModel {
        let vm = TradingDeskViewModel(service: service)
        vm.sleeper = { _ in }   // 重连零等待
        return vm
    }

    @Test("startRun：resolveTicker → createRun → 事件折叠到终态")
    func startRunFoldsEvents() async throws {
        let service = MockDeskService()
        let events = [
            startedEvent(1, ticker: "700.HK"),
            ev(.turnStarted, seq: 2, data: [
                "turn_id": "t1", "stage_id": "s1", "name": "分析师",
                "role": "", "avatar": "析"]),
            ev(.agentToken, seq: 3, data: ["turn_id": "t1", "text": "结论"]),
            ev(.runFinished, seq: 4, data: ["status": "completed", "duration_ms": 1000]),
        ]
        service.streamScripts = [{ _ in frames(events) }]
        let vm = makeVM(service)

        await vm.startRun(ticker: "0700", market: .HK)
        #expect(await waitUntil { vm.state.status == .completed })
        #expect(service.createRunCalls == 1)
        #expect(vm.state.runId == "run-1")
        #expect(vm.state.turns.first?.text == "结论")
        #expect(vm.state.lastEventId == "id-4")
        #expect(vm.state.ticker == "700.HK")
    }

    @Test("seq 去重：断线重连重放的旧事件被丢弃")
    func seqDedup() async throws {
        let service = MockDeskService()
        service.streamScripts = [
            { _ in failingStream() },
            { _ in frames([
                startedEvent(1),
                ev(.turnStarted, seq: 2, data: [
                    "turn_id": "t1", "stage_id": "", "name": "n", "role": "", "avatar": ""]),
                ev(.turnStarted, seq: 2, data: [   // 重放，必须被丢弃
                    "turn_id": "t1", "stage_id": "", "name": "n", "role": "", "avatar": ""]),
                ev(.agentToken, seq: 3, data: ["turn_id": "t1", "text": "x"]),
                ev(.runFinished, seq: 4, data: ["status": "completed", "duration_ms": 0]),
            ]) },
        ]
        let vm = makeVM(service)
        await vm.startRun(ticker: "NVDA", market: .US)
        #expect(await waitUntil { vm.state.status == .completed })
        #expect(vm.state.turns.count == 1)          // 重放的 turn.started 没建第二张卡
        #expect(service.streamCallCount == 2)       // 断线重连了一次
    }

    @Test("终态不再重连：run.finished 后流断也不重试")
    func noReconnectAfterTerminal() async throws {
        let service = MockDeskService()
        service.streamScripts = [
            { _ in frames([
                startedEvent(1),
                ev(.runFinished, seq: 2, data: ["status": "completed", "duration_ms": 0]),
            ]) },
            { _ in failingStream() },   // 若错误重连会走这里（不应被调用）
        ]
        let vm = makeVM(service)
        await vm.startRun(ticker: "NVDA", market: .US)
        #expect(await waitUntil { vm.state.status == .completed })
        try await Task.sleep(for: .milliseconds(100))
        #expect(service.streamCallCount == 1)
    }

    @Test("流正常结束不重连（后端 run.finished 后关流）")
    func normalEndNoReconnect() async throws {
        let service = MockDeskService()
        service.streamScripts = [
            { _ in frames([
                startedEvent(1),
                // 没有 run.finished：流正常结束也应停止（对齐 web 行为）
            ]) },
        ]
        let vm = makeVM(service)
        await vm.startRun(ticker: "NVDA", market: .US)
        try await Task.sleep(for: .milliseconds(150))
        #expect(service.streamCallCount == 1)
        #expect(vm.state.status == .running)
    }

    @Test("control：注入/暂停转发；失败 → pageError")
    func controlActions() async throws {
        let service = MockDeskService()
        service.streamScripts = [{ _ in frames([
            ev(.runStarted, seq: 1, data: [
                "ticker": "NVDA", "trade_date": "d", "engine": "e",
                "capabilities": ["supports_pause": true, "supports_inject": true,
                                  "supports_resume_after_restart": false],
                "stages": []]),
        ]) }]
        let vm = makeVM(service)
        await vm.startRun(ticker: "NVDA", market: .US)
        #expect(await waitUntil { vm.state.status == .running })

        await vm.control(.inject, text: "关注关税")
        await vm.control(.pause)
        #expect(service.controls.count == 2)
        #expect(service.controls[0].0 == .inject && service.controls[0].1 == "关注关税")
        #expect(service.controls[1].0 == .pause && service.controls[1].1 == nil)

        service.controlError = APIError.validation("注入意见时 text 不能为空")
        await vm.control(.inject, text: "")
        #expect(vm.pageError == "注入意见时 text 不能为空")
    }

    @Test("createRun 失败 → pageError + 状态回 idle")
    func createRunFails() async throws {
        let service = MockDeskService()
        service.createRunError = APIError.server(500, "LLM 全线熔断")
        let vm = makeVM(service)
        await vm.startRun(ticker: "NVDA", market: .US)
        #expect(vm.pageError == "LLM 全线熔断")
        #expect(vm.state.status == .idle)
    }

    @Test("后台挂起 → 断流；回前台 → 若仍 live 则续订")
    func scenePhaseHandling() async throws {
        let service = MockDeskService()
        service.streamScripts = [
            { _ in frames([startedEvent(1)]) },
            { _ in frames([ev(.runFinished, seq: 9, data: [
                "status": "completed", "duration_ms": 0])]) },
        ]
        let vm = makeVM(service)
        await vm.startRun(ticker: "NVDA", market: .US)
        #expect(await waitUntil { service.streamCallCount == 1 })

        vm.appDidEnterBackground()
        try await Task.sleep(for: .milliseconds(50))
        #expect(vm.state.status == .running)   // 本地状态保留

        await vm.appDidBecomeActive()
        #expect(await waitUntil { vm.state.status == .completed })
        #expect(service.streamCallCount == 2)
    }

    @Test("401 → lastAuthError 置位（App 层据此清 token）")
    func unauthorizedSurfaces() async throws {
        let service = MockDeskService()
        service.createRunError = APIError.unauthorized(nil)
        let vm = makeVM(service)
        await vm.startRun(ticker: "NVDA", market: .US)
        #expect(vm.lastAuthError?.isUnauthorized == true)
    }

    @Test("重连退避倍增：800ms → 1.6s（sleeper 收到递增时长）")
    func backoffDoubles() async throws {
        let service = MockDeskService()
        let recorded = LockedDurations()
        service.streamScripts = [
            { _ in failingStream() },
            { _ in failingStream() },
            { _ in frames([startedEvent(1),
                            ev(.runFinished, seq: 2, data: ["status": "completed",
                                                              "duration_ms": 0])]) },
        ]
        let vm = TradingDeskViewModel(service: service)
        vm.sleeper = { d in recorded.append(d) }   // 记录但不真睡
        await vm.startRun(ticker: "NVDA", market: .US)
        #expect(await waitUntil { vm.state.status == .completed })
        #expect(recorded.all.count == 2)
        #expect(recorded.all[0] == .milliseconds(800))
        #expect(recorded.all[1] == .milliseconds(1600))
    }
}

/// 跨闭包记录 sleeper 时长的线程安全盒子（async 上下文安全锁）。
final class LockedDurations: @unchecked Sendable {
    private let items = OSAllocatedUnfairLock(initialState: [Duration]())
    var all: [Duration] { items.withLock { $0 } }
    func append(_ d: Duration) { items.withLock { $0.append(d) } }
}
