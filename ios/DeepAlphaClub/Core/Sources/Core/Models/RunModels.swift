import Foundation

/// 历史列表一条 run 的状态（也用于流式 state 的 RunStatus。
/// 后端 run.finished 的 status 是其中后四个值）。
public enum RunRecordStatus: String, Codable, Sendable, Equatable {
    case running, completed, cancelled, failed, interrupted
}

public struct RunSummary: Codable, Sendable, Equatable, Identifiable {
    public var runId: String
    public var ticker: String
    public var tradeDate: String
    public var engine: String
    public var status: RunRecordStatus
    public var durationMs: Int
    /// ISO 8601 字符串（后端序列化成字符串）
    public var createdAt: String
    public var finishedAt: String?
    public var verdictSignal: VerdictSignal?
    public var verdictConfidence: Double?
    public var turnsCount: Int
    public var signalsCount: Int

    public var id: String { runId }
    enum CodingKeys: String, CodingKey {
        case ticker, engine, status
        case runId = "run_id"
        case tradeDate = "trade_date"
        case durationMs = "duration_ms"
        case createdAt = "created_at"
        case finishedAt = "finished_at"
        case verdictSignal = "verdict_signal"
        case verdictConfidence = "verdict_confidence"
        case turnsCount = "turns_count"
        case signalsCount = "signals_count"
    }
}

public struct RunListResponse: Codable, Sendable, Equatable {
    public var runs: [RunSummary]
}

/// 回放页一条 turn 的持久化记录（RunDetailResponse.turns 元素）。
public struct TurnRecord: Codable, Sendable, Equatable, Identifiable {
    public var turnId: String
    public var stageId: String
    public var name: String
    public var role: String
    public var avatar: String
    public var text: String
    public var toolCalls: [String]
    public var debate: DebateInfo?
    public var id: String { turnId }
    enum CodingKeys: String, CodingKey {
        case name, role, avatar, text, debate
        case turnId = "turn_id"
        case stageId = "stage_id"
        case toolCalls = "tool_calls"
    }
}

/// 辩论元数据（流式 DebateTurnData 与回放 TurnRecord.debate 共用形状）。
public struct DebateInfo: Codable, Sendable, Equatable {
    public var debateId: String
    public var side: String
    public var sideLabel: String
    public var polarity: Polarity
    public var round: Int

    public init(debateId: String, side: String, sideLabel: String,
                polarity: Polarity, round: Int) {
        self.debateId = debateId
        self.side = side
        self.sideLabel = sideLabel
        self.polarity = polarity
        self.round = round
    }

    enum CodingKeys: String, CodingKey {
        case side, polarity, round
        case debateId = "debate_id"
        case sideLabel = "side_label"
    }
}

public struct SignalRecord: Codable, Sendable, Equatable {
    public var stageId: String
    public var name: String
    public var dir: Polarity
    public var conf: Int
    public var turnId: String?
    public var extracted: Bool
    enum CodingKeys: String, CodingKey {
        case name, dir, conf, extracted
        case stageId = "stage_id"
        case turnId = "turn_id"
    }
}

public struct RunDetailResponse: Codable, Sendable, Equatable {
    public var runId: String
    public var ticker: String
    public var tradeDate: String
    public var engine: String
    public var status: RunRecordStatus
    public var durationMs: Int
    public var createdAt: String
    public var finishedAt: String?
    public var verdict: VerdictData?
    public var signals: [SignalRecord]
    public var turns: [TurnRecord]
    enum CodingKeys: String, CodingKey {
        case ticker, engine, status, verdict, signals, turns
        case runId = "run_id"
        case tradeDate = "trade_date"
        case durationMs = "duration_ms"
        case createdAt = "created_at"
        case finishedAt = "finished_at"
    }
}
