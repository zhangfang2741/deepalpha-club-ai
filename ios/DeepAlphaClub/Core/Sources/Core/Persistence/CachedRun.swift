import Foundation
import SwiftData

/// 历史 run 的本地缓存行（SwiftData）。进 App 立即可读，后台再拉远端 diff。
@Model
public final class CachedRun {
    @Attribute(.unique) public var runId: String
    public var ticker: String
    public var tradeDate: String
    public var status: String
    public var durationMs: Int
    public var verdictSignal: String?
    public var verdictConfidence: Double?
    public var turnsCount: Int
    public var signalsCount: Int
    /// 用 created_at（ISO）转的 Date，作排序与淘汰键
    public var startedAt: Date

    public init(runId: String, ticker: String, tradeDate: String, status: String,
                durationMs: Int, verdictSignal: String?, verdictConfidence: Double?,
                turnsCount: Int, signalsCount: Int, startedAt: Date) {
        self.runId = runId
        self.ticker = ticker
        self.tradeDate = tradeDate
        self.status = status
        self.durationMs = durationMs
        self.verdictSignal = verdictSignal
        self.verdictConfidence = verdictConfidence
        self.turnsCount = turnsCount
        self.signalsCount = signalsCount
        self.startedAt = startedAt
    }
}
