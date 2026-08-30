import Foundation

// ── 基础枚举（镜像 app/schemas/trading_desk.py）──────────────────

public enum Polarity: String, Codable, Sendable, Equatable {
    case bull, bear, neutral
}

public enum StageGroup: String, Codable, Sendable, Equatable {
    case analyst, system, debate, manager, trader
}

public enum EventType: String, Codable, Sendable, Equatable, CaseIterable {
    case runStarted = "run.started"
    case stageActive = "stage.active"
    case stageDone = "stage.done"
    case turnStarted = "turn.started"
    case agentToolCall = "agent.tool_call"
    case agentToken = "agent.token"
    case agentThink = "agent.think"
    case turnDone = "turn.done"
    case agentSignal = "agent.signal"
    case debateTurn = "debate.turn"
    case humanNote = "human.note"
    case consensusUpdate = "consensus.update"
    case runPaused = "run.paused"
    case runResumed = "run.resumed"
    case verdict = "verdict"
    case runFinished = "run.finished"
    case error = "error"
}

public enum ControlAction: String, Codable, Sendable, Equatable {
    case pause, resume, inject, cancel
}

public enum VerdictSignal: String, Codable, Sendable, Equatable {
    case buy = "BUY", sell = "SELL", hold = "HOLD"
}

// ── 描述性 struct ────────────────────────────────────────────

public struct EngineCapabilities: Codable, Sendable, Equatable {
    public var supportsPause: Bool
    public var supportsInject: Bool
    public var supportsResumeAfterRestart: Bool
    public init(supportsPause: Bool = false, supportsInject: Bool = false,
                supportsResumeAfterRestart: Bool = false) {
        self.supportsPause = supportsPause
        self.supportsInject = supportsInject
        self.supportsResumeAfterRestart = supportsResumeAfterRestart
    }
    enum CodingKeys: String, CodingKey {
        case supportsPause = "supports_pause"
        case supportsInject = "supports_inject"
        case supportsResumeAfterRestart = "supports_resume_after_restart"
    }
}

public struct StageDescriptor: Codable, Sendable, Equatable, Identifiable {
    public var id: String
    public var name: String
    public var role: String
    public var group: StageGroup
    public init(id: String, name: String, role: String = "", group: StageGroup = .analyst) {
        self.id = id; self.name = name; self.role = role; self.group = group
    }
}

// ── 事件信封 ─────────────────────────────────────────────────

/// SSE 事件信封。seq 单调递增用于去重；data 弱类型，按 type 窄化。
public struct TradingDeskEvent: Codable, Sendable, Equatable {
    public let type: EventType
    public let runId: String
    public let seq: Int
    public let ts: Int
    public let data: JSONValue?

    public init(type: EventType, runId: String, seq: Int, ts: Int, data: JSONValue? = nil) {
        self.type = type; self.runId = runId; self.seq = seq
        self.ts = ts; self.data = data
    }

    /// 是否终止事件（fatal error 或 run.finished）。
    public var isTerminal: Bool {
        type == .runFinished || (type == .error && (data?["fatal"]?.bool ?? false))
    }

    enum CodingKeys: String, CodingKey {
        case type, seq, ts, data
        case runId = "run_id"
    }
}

// ── 强类型 payload（从 event.data decode）──────────────────────

public struct RunStartedData: Codable, Sendable, Equatable {
    public var ticker: String
    public var tradeDate: String
    public var engine: String
    public var capabilities: EngineCapabilities
    public var stages: [StageDescriptor]
    enum CodingKeys: String, CodingKey {
        case ticker, engine, capabilities, stages
        case tradeDate = "trade_date"
    }
}

public struct SignalData: Codable, Sendable, Equatable {
    public var stageId: String
    public var name: String
    public var dir: Polarity
    public var conf: Int
    public var turnId: String?
    /// False=引擎原生产出；True=由报告文本抽取（UI 要标注「抽」）
    public var extracted: Bool
    enum CodingKeys: String, CodingKey {
        case name, dir, conf, extracted
        case stageId = "stage_id"
        case turnId = "turn_id"
    }
}

public struct DebateTurnData: Codable, Sendable, Equatable {
    public var stageId: String
    public var debateId: String
    public var side: String
    public var sideLabel: String
    public var polarity: Polarity
    public var round: Int
    public var turnId: String
    enum CodingKeys: String, CodingKey {
        case side, polarity, round
        case stageId = "stage_id"
        case debateId = "debate_id"
        case sideLabel = "side_label"
        case turnId = "turn_id"
    }
}

public struct ConsensusData: Codable, Sendable, Equatable {
    public var bull: Int
    public var neutral: Int
    public var bear: Int
    public var lean: String

    // 生产路径都是 JSON 解码来的，但 SwiftUI 预览和测试要能直接构造
    public init(bull: Int, neutral: Int, bear: Int, lean: String) {
        self.bull = bull
        self.neutral = neutral
        self.bear = bear
        self.lean = lean
    }
}

public struct VerdictData: Codable, Sendable, Equatable {
    public var signal: VerdictSignal
    public var confidence: Double
    public var sizeFraction: Double
    public var entryReferencePrice: Double?
    public var targetPrice: Double?
    public var stopLoss: Double?
    public var currency: String?
    public var timeHorizonDays: Int?
    public var rationale: String
    /// 引擎 JSON 解析失败走 fallback 时置位——UI 必须显式展示降级警告
    public var warningMessage: String?
    enum CodingKeys: String, CodingKey {
        case signal, confidence, currency, rationale
        case sizeFraction = "size_fraction"
        case entryReferencePrice = "entry_reference_price"
        case targetPrice = "target_price"
        case stopLoss = "stop_loss"
        case timeHorizonDays = "time_horizon_days"
        case warningMessage = "warning_message"
    }
}

public struct RunFinishedData: Codable, Sendable, Equatable {
    public var status: String
    public var durationMs: Int
    enum CodingKeys: String, CodingKey {
        case status
        case durationMs = "duration_ms"
    }
}
