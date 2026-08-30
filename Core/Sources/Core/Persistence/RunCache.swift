import Foundation
import SwiftData

/// 缓存读写 actor（@ModelActor 生成 executor 隔离）。
/// 保留最近 50 条，超出按 startedAt 淘汰。
@ModelActor
public actor RunCache {
    /// ISO8601DateFormatter 非 Sendable，不做 static 共享——按调用创建，开销可忽略。
    static func parseISO(_ s: String) -> Date? {
        let frac = ISO8601DateFormatter()
        frac.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return frac.date(from: s) ?? ISO8601DateFormatter().date(from: s)
    }

    static func formatISO(_ d: Date) -> String {
        ISO8601DateFormatter().string(from: d)
    }

    /// 批量写入（同 runId 覆盖），然后裁剪到 50 条。
    public func upsert(_ summaries: [RunSummary]) throws {
        let context = modelContext
        let ids = summaries.map(\.runId)
        // predicate 内联数组 contains 不可靠（宏展开限制），数据量 ≤50 直接全量取
        let existing = try context.fetch(FetchDescriptor<CachedRun>())
        var byId: [String: CachedRun] = Dictionary(
            uniqueKeysWithValues: existing.filter { ids.contains($0.runId) }
                .map { ($0.runId, $0) })
        for s in summaries {
            let date = Self.parseISO(s.createdAt) ?? Date(timeIntervalSince1970: 0)
            if let row = byId[s.runId] {
                row.ticker = s.ticker
                row.tradeDate = s.tradeDate
                row.status = s.status.rawValue
                row.durationMs = s.durationMs
                row.verdictSignal = s.verdictSignal?.rawValue
                row.verdictConfidence = s.verdictConfidence
                row.turnsCount = s.turnsCount
                row.signalsCount = s.signalsCount
                row.startedAt = date
            } else {
                let row = CachedRun(
                    runId: s.runId, ticker: s.ticker, tradeDate: s.tradeDate,
                    status: s.status.rawValue, durationMs: s.durationMs,
                    verdictSignal: s.verdictSignal?.rawValue,
                    verdictConfidence: s.verdictConfidence,
                    turnsCount: s.turnsCount, signalsCount: s.signalsCount,
                    startedAt: date)
                context.insert(row)
                byId[s.runId] = row
            }
        }
        try context.save()
        try prune()
    }

    /// 按 ticker 过滤（大小写不敏感 contains，对齐远端过滤语义），startedAt 倒序。
    public func list(ticker: String?) throws -> [RunSummary] {
        let rows = try modelContext.fetch(FetchDescriptor<CachedRun>(
            sortBy: [SortDescriptor(\.startedAt, order: .reverse)]))
        let filtered: [CachedRun]
        if let t = ticker?.trimmingCharacters(in: .whitespaces).uppercased(), !t.isEmpty {
            filtered = rows.filter { $0.ticker.uppercased().contains(t) }
        } else {
            filtered = rows
        }
        return filtered.map { row in
            RunSummary(
                runId: row.runId, ticker: row.ticker, tradeDate: row.tradeDate,
                engine: "cached",
                status: RunRecordStatus(rawValue: row.status) ?? .completed,
                durationMs: row.durationMs,
                createdAt: Self.formatISO(row.startedAt),
                finishedAt: nil,
                verdictSignal: row.verdictSignal.flatMap(VerdictSignal.init(rawValue:)),
                verdictConfidence: row.verdictConfidence,
                turnsCount: row.turnsCount, signalsCount: row.signalsCount)
        }
    }

    /// 只保留最近 50 条。
    private func prune() throws {
        let all = try modelContext.fetch(FetchDescriptor<CachedRun>(
            sortBy: [SortDescriptor(\.startedAt, order: .reverse)]))
        guard all.count > 50 else { return }
        for row in all.dropFirst(50) {
            modelContext.delete(row)
        }
        try modelContext.save()
    }
}

/// 默认磁盘容器的工厂：失败（磁盘满/迁移冲突）返回 nil，App 降级为无缓存运行。
public enum RunCacheDefault {
    public static func make() -> RunCache? {
        guard let container = try? ModelContainer(for: CachedRun.self) else { return nil }
        return RunCache(modelContainer: container)
    }
}
