import Foundation
import Observation

/// 单条 run 回放：getRun 拉详情，TurnRecord → Turn 全文直出（无流式动画）。
@MainActor @Observable
public final class RunReplayViewModel {
    public private(set) var detail: RunDetailResponse?
    public private(set) var turns: [Turn] = []
    public private(set) var signals: [SignalRow] = []
    public private(set) var loading = false
    public var error: String?

    let service: any TradingDeskServicing

    public init(service: any TradingDeskServicing) {
        self.service = service
    }

    public var verdict: VerdictData? { detail?.verdict }

    public func load(runId: String) async {
        self.error = nil
        loading = true
        defer { loading = false }
        do {
            let d = try await service.getRun(runId: runId)
            detail = d
            turns = d.turns.map(\.asTurn)
            signals = d.signals.map {
                SignalRow(name: $0.name, dir: $0.dir, conf: $0.conf, extracted: $0.extracted)
            }
        } catch let e as APIError {
            self.error = e.message
        } catch {
            self.error = "载入失败：\(error.localizedDescription)"
        }
    }
}

extension TurnRecord {
    /// 回放记录 → 渲染用 Turn（done=true 全文直出）。
    public var asTurn: Turn {
        Turn(turnId: turnId, stageId: stageId, name: name, role: role, avatar: avatar,
             text: text, tools: toolCalls, done: true, human: false, debate: debate,
             signal: nil)
    }
}
