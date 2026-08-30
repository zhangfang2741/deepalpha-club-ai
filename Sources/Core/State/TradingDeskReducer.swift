import Foundation

/// 事件 → 状态纯函数（移植 web reduceEvent，frontend/lib/store/trading_desk.ts:111）。
/// 返回新状态（值语义），不碰任何 UI 框架——测试直接覆盖。
public enum TradingDeskReducer {
    public static func reduce(_ state: TradingDeskState,
                              _ event: TradingDeskEvent) -> TradingDeskState {
        var s = state
        switch event.type {
        case .runStarted:
            guard let d = event.data?.decode(as: RunStartedData.self) else { return s }
            s.ticker = d.ticker
            s.engine = d.engine
            s.capabilities = d.capabilities
            s.stages = d.stages
            s.stageStatus = Dictionary(uniqueKeysWithValues: d.stages.map { ($0.id, .pending) })
            s.status = .running

        case .stageActive:
            if let id = event.data?["stage_id"]?.string { s.stageStatus[id] = .active }

        case .stageDone:
            if let id = event.data?["stage_id"]?.string { s.stageStatus[id] = .done }

        case .turnStarted:
            guard let d = event.data?.decode(as: TurnStartedData.self) else { return s }
            s.turns.append(Turn(
                turnId: d.turnId, stageId: d.stageId, name: d.name, role: d.role,
                avatar: d.avatar, text: "", tools: [], done: false, human: false,
                debate: nil, signal: nil))

        case .debateTurn:
            guard let d = event.data?.decode(as: DebateTurnData.self) else { return s }
            s.turns.update(d.turnId) { $0.debate = DebateInfo(
                debateId: d.debateId, side: d.side, sideLabel: d.sideLabel,
                polarity: d.polarity, round: d.round) }

        case .agentToolCall:
            if let turnId = event.data?["turn_id"]?.string,
               let tool = event.data?["tool"]?.string {
                s.turns.update(turnId) { $0.tools.append(tool) }
            }

        case .agentToken:
            if let turnId = event.data?["turn_id"]?.string,
               let text = event.data?["text"]?.string {
                s.turns.update(turnId) { $0.text += text }
            }

        case .agentThink:
            if let turnId = event.data?["turn_id"]?.string,
               let text = event.data?["text"]?.string {
                s.turns.update(turnId) { $0.thinking = ($0.thinking ?? "") + text }
            }

        case .turnDone:
            if let turnId = event.data?["turn_id"]?.string {
                s.turns.update(turnId) { $0.done = true }
            }

        case .agentSignal:
            guard let d = event.data?.decode(as: SignalData.self) else { return s }
            s.signals.append(SignalRow(name: d.name, dir: d.dir, conf: d.conf,
                                       extracted: d.extracted))
            s.stageSignal[d.stageId] = StageSignal(dir: d.dir, conf: d.conf)
            if let turnId = d.turnId {
                s.turns.update(turnId) {
                    $0.signal = TurnSignal(dir: d.dir, conf: d.conf, extracted: d.extracted)
                }
            }

        case .humanNote:
            if let text = event.data?["text"]?.string {
                s.turns.append(Turn(
                    turnId: "human-\(event.seq)", stageId: "", name: "你", role: "人工意见",
                    avatar: "你", text: text, tools: [], done: true, human: true,
                    debate: nil, signal: nil))
            }

        case .consensusUpdate:
            if let c = event.data?.decode(as: ConsensusData.self) { s.consensus = c }

        case .runPaused:
            s.status = .paused

        case .runResumed:
            s.status = .running

        case .verdict:
            if let v = event.data?.decode(as: VerdictData.self) { s.verdict = v }

        case .runFinished:
            if let d = event.data?.decode(as: RunFinishedData.self),
               let st = RunStatus(rawValue: d.status) {
                s.status = st
            } else {
                s.status = .failed
            }
            s.durationMs = event.data?["duration_ms"]?.int

        case .error:
            s.error = event.data?["message"]?.string
        }
        return s
    }

    /// 审计链由 turn 序列派生（非独立事件）。人工意见显式标注，人为干预可追溯。
    public static func buildAuditChain(_ turns: [Turn]) -> [AuditEntry] {
        turns.filter { !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
            .map { t in
                let who: String
                if t.human { who = "你" }
                else if let debate = t.debate { who = "\(t.name)（第 \(debate.round) 轮）" }
                else { who = t.name }
                let trimmed = t.text
                let excerpt = trimmed.count > 40
                    ? String(trimmed.prefix(40)) + "…" : trimmed
                return AuditEntry(who: who, human: t.human, excerpt: excerpt)
            }
    }
}

/// turn.started 的 payload（reducer 专用，放这里避免模型文件膨胀）。
struct TurnStartedData: Codable, Sendable {
    var turnId: String
    var stageId: String
    var name: String
    var role: String
    var avatar: String
    enum CodingKeys: String, CodingKey {
        case name, role, avatar
        case turnId = "turn_id"
        case stageId = "stage_id"
    }
}

extension Array where Element == Turn {
    /// 按 turnId 就地改一张卡（token 累加/辩论回填等）。
    mutating func update(_ turnId: String, _ transform: (inout Turn) -> Void) {
        guard let idx = firstIndex(where: { $0.turnId == turnId }) else { return }
        transform(&self[idx])
    }
}
