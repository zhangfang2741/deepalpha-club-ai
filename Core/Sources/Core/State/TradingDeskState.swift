import Foundation

public enum RunStatus: String, Sendable, Equatable {
    case idle, running, paused, completed, cancelled, failed, interrupted
}

public enum StageStatus: String, Sendable, Equatable {
    case pending, active, done
}

public struct StageSignal: Sendable, Equatable {
    public var dir: Polarity
    public var conf: Int
    public init(dir: Polarity, conf: Int) {
        self.dir = dir
        self.conf = conf
    }
}

public struct TurnSignal: Sendable, Equatable {
    public var dir: Polarity
    public var conf: Int
    public var extracted: Bool
    public init(dir: Polarity, conf: Int, extracted: Bool) {
        self.dir = dir
        self.conf = conf
        self.extracted = extracted
    }
}

/// 一张发言卡（agent / 人工意见 / 辩论发言共用）。
public struct Turn: Identifiable, Sendable, Equatable {
    public var turnId: String
    public var stageId: String
    public var name: String
    public var role: String
    public var avatar: String
    public var text: String
    /// Anthropic extended thinking 推理链（折叠展示）
    public var thinking: String?
    public var tools: [String]
    public var done: Bool
    /// 人工意见卡片，与 agent 卡片区分渲染
    public var human: Bool
    public var debate: DebateInfo?
    public var signal: TurnSignal?
    public var id: String { turnId }

    public init(turnId: String, stageId: String, name: String, role: String,
                avatar: String, text: String, thinking: String? = nil, tools: [String],
                done: Bool, human: Bool, debate: DebateInfo?, signal: TurnSignal?) {
        self.turnId = turnId
        self.stageId = stageId
        self.name = name
        self.role = role
        self.avatar = avatar
        self.text = text
        self.thinking = thinking
        self.tools = tools
        self.done = done
        self.human = human
        self.debate = debate
        self.signal = signal
    }
}

public struct SignalRow: Sendable, Equatable, Identifiable {
    public var name: String
    public var dir: Polarity
    public var conf: Int
    public var extracted: Bool
    public var id: String { "\(name)-\(dir)-\(conf)" }
    public init(name: String, dir: Polarity, conf: Int, extracted: Bool) {
        self.name = name
        self.dir = dir
        self.conf = conf
        self.extracted = extracted
    }
}

public struct AuditEntry: Sendable, Equatable {
    public var who: String
    public var human: Bool
    public var excerpt: String
}

/// UI 全量状态（值类型，reducer 产出新副本，VM 持有）。
public struct TradingDeskState: Sendable, Equatable {
    public var runId: String?
    public var status: RunStatus = .idle
    public var ticker: String = ""
    public var engine: String = ""
    public var capabilities = EngineCapabilities()
    public var stages: [StageDescriptor] = []
    public var stageStatus: [String: StageStatus] = [:]
    public var stageSignal: [String: StageSignal] = [:]
    public var turns: [Turn] = []
    public var signals: [SignalRow] = []
    public var consensus: ConsensusData?
    public var verdict: VerdictData?
    /// 断线续读游标（SSE id）
    public var lastEventId: String?
    /// 去重游标（事件 seq）
    public var lastSeq: Int = 0
    public var error: String?
    public var durationMs: Int?

    public init() {}
}
