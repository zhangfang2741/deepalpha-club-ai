import Foundation
import Testing
import SwiftData
@testable import Core

func summary(_ runId: String, ticker: String = "NVDA", date: Date = .distantPast,
             signal: VerdictSignal? = nil) -> RunSummary {
    RunSummary(runId: runId, ticker: ticker, tradeDate: "2026-08-30", engine: "tradingagents",
               status: .completed, durationMs: 60000,
               createdAt: ISO8601DateFormatter().string(from: date),
               finishedAt: nil, verdictSignal: signal, verdictConfidence: signal == nil ? nil : 0.7,
               turnsCount: 3, signalsCount: 1)
}

@Suite("RunCache")
struct RunCacheTests {
    func makeCache() throws -> RunCache {
        let config = ModelConfiguration(isStoredInMemoryOnly: true)
        let container = try ModelContainer(for: CachedRun.self, configurations: config)
        return RunCache(modelContainer: container)
    }

    @Test("upsert 后可 list，按时间倒序")
    func upsertAndList() async throws {
        let cache = try makeCache()
        let base = Date(timeIntervalSince1970: 1_750_000_000)
        try await cache.upsert([
            summary("a", date: base),
            summary("b", date: base.addingTimeInterval(60)),
            summary("c", date: base.addingTimeInterval(-60)),
        ])
        let runs = try await cache.list(ticker: nil)
        #expect(runs.map(\.runId) == ["b", "a", "c"])
    }

    @Test("同 runId upsert 覆盖不重复")
    func upsertOverwrites() async throws {
        let cache = try makeCache()
        try await cache.upsert([summary("a", signal: .buy)])
        var changed = summary("a", signal: .sell)
        changed.status = .failed
        try await cache.upsert([changed])
        let runs = try await cache.list(ticker: nil)
        #expect(runs.count == 1)
        #expect(runs[0].verdictSignal == .sell)
        #expect(runs[0].status == .failed)
    }

    @Test("ticker 过滤（前缀大写匹配）")
    func tickerFilter() async throws {
        let cache = try makeCache()
        let base = Date(timeIntervalSince1970: 1_750_000_000)
        try await cache.upsert([
            summary("a", ticker: "NVDA", date: base),
            summary("b", ticker: "700.HK", date: base.addingTimeInterval(10)),
            summary("c", ticker: "NVDA", date: base.addingTimeInterval(20)),
        ])
        let nvda = try await cache.list(ticker: "nvda")
        #expect(nvda.map(\.runId) == ["c", "a"])
    }

    @Test("超过 50 条淘汰最旧")
    func pruneTo50() async throws {
        let cache = try makeCache()
        let base = Date(timeIntervalSince1970: 1_750_000_000)
        let many = (0..<60).map { i in
            summary("run-\(i)", date: base.addingTimeInterval(Double(i)))
        }
        try await cache.upsert(many)
        let runs = try await cache.list(ticker: nil)
        #expect(runs.count == 50)
        #expect(runs.first?.runId == "run-59")          // 最新保留
        #expect(!runs.contains { $0.runId == "run-0" }) // 最旧被淘汰
    }
}
