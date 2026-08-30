import Foundation
import Testing
import SwiftData
@testable import DeepAlphaCore

@MainActor
@Suite("HistoryListViewModel")
struct HistoryListViewModelTests {
    @Test("refresh：本地缓存先出 → 远端结果替换 → 回写缓存")
    func refreshFlow() async throws {
        let config = ModelConfiguration(isStoredInMemoryOnly: true)
        let container = try ModelContainer(for: CachedRun.self, configurations: config)
        let cache = RunCache(modelContainer: container)
        try await cache.upsert([summary("local-1", ticker: "NVDA",
                                         date: Date(timeIntervalSince1970: 100))])

        let remote = RunListResponse(runs: [
            summary("remote-1", ticker: "NVDA", date: Date(timeIntervalSince1970: 200)),
        ])
        let service = MockDeskService()
        service.listRunsResult = remote

        let vm = HistoryListViewModel(service: service, cache: cache)
        #expect(vm.runs.isEmpty)

        await vm.refresh(ticker: nil)
        // 先渲染了本地，后被远端替换
        #expect(vm.runs.map(\.runId) == ["remote-1"])
        #expect(!vm.loading)
        #expect(vm.error == nil)
        // 远端结果已回写缓存
        let cached = try await cache.list(ticker: nil)
        #expect(cached.map(\.runId) == ["remote-1", "local-1"])
    }

    @Test("refresh 失败：本地数据保留 + error 展示")
    func refreshFailure() async throws {
        let config = ModelConfiguration(isStoredInMemoryOnly: true)
        let container = try ModelContainer(for: CachedRun.self, configurations: config)
        let cache = RunCache(modelContainer: container)
        try await cache.upsert([summary("local-1", date: Date(timeIntervalSince1970: 100))])

        let service = MockDeskService()
        service.listRunsError = APIError.network

        let vm = HistoryListViewModel(service: service, cache: cache)
        await vm.refresh(ticker: nil)
        #expect(vm.runs.map(\.runId) == ["local-1"])
        #expect(vm.error == "网络不可用，请检查连接")
    }

    @Test("无缓存时 refresh 只走远端")
    func refreshNoCache() async throws {
        let service = MockDeskService()
        service.listRunsResult = RunListResponse(runs: [summary("r1")])
        let vm = HistoryListViewModel(service: service, cache: nil)
        await vm.refresh(ticker: nil)
        #expect(vm.runs.map(\.runId) == ["r1"])
    }
}

@MainActor
@Suite("RunReplayViewModel")
struct RunReplayViewModelTests {
    @Test("load：详情转 Turn 卡片数组 + signals/verdict 齐备")
    func loadDetail() async throws {
        let service = MockDeskService()
        service.getRunResult = RunDetailResponse(
            runId: "r1", ticker: "NVDA", tradeDate: "2026-08-30", engine: "e",
            status: .completed, durationMs: 5000,
            createdAt: "2026-08-30T10:00:00+00:00", finishedAt: nil,
            verdict: VerdictData(signal: .buy, confidence: 0.9, sizeFraction: 0.2,
                                  entryReferencePrice: 100, targetPrice: 120, stopLoss: 90,
                                  currency: "USD", timeHorizonDays: 30, rationale: "r",
                                  warningMessage: nil),
            signals: [SignalRecord(stageId: "s", name: "分析师", dir: .bull, conf: 80,
                                    turnId: nil, extracted: true)],
            turns: [TurnRecord(turnId: "t1", stageId: "s", name: "分析师", role: "r",
                                avatar: "析", text: "内容", toolCalls: [],
                                debate: nil)])

        let vm = RunReplayViewModel(service: service)
        await vm.load(runId: "r1")
        #expect(vm.detail?.verdict?.signal == .buy)
        #expect(vm.turns.count == 1)
        #expect(vm.turns[0].text == "内容")
        #expect(vm.turns[0].done)          // 回放卡片全部 done
        #expect(vm.signals.count == 1)
        #expect(vm.error == nil)
    }

    @Test("load 404：error 展示")
    func loadNotFound() async throws {
        let service = MockDeskService()
        service.getRunError = APIError.notFound
        let vm = RunReplayViewModel(service: service)
        await vm.load(runId: "gone")
        #expect(vm.error == "资源不存在")
        #expect(vm.turns.isEmpty)
    }
}
