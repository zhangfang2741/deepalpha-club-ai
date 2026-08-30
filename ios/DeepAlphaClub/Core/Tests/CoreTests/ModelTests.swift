import Foundation
import Testing
@testable import DeepAlphaCore

/// 测试端便捷构造 JSONValue 字面量。
func jobj(_ dict: [String: JSONValue]) -> JSONValue { .object(dict) }

@Test("事件信封解析：snake_case run_id 映射 runId")
func eventDecoding() throws {
    let json = """
    {"type":"agent.token","run_id":"r1","seq":3,"ts":1750000000000,
     "data":{"turn_id":"t1","text":"看多"}}
    """
    let e = try JSONDecoder().decode(TradingDeskEvent.self, from: Data(json.utf8))
    #expect(e.type == .agentToken)
    #expect(e.runId == "r1")
    #expect(e.seq == 3)
    #expect(e.data?["turn_id"]?.string == "t1")
    #expect(e.data?["text"]?.string == "看多")
}

@Test("isTerminal：run.finished 或 fatal error")
func terminal() {
    let fin = TradingDeskEvent(type: .runFinished, runId: "r", seq: 1, ts: 0,
                               data: jobj(["status": "completed", "duration_ms": 10]))
    #expect(fin.isTerminal)
    let fatal = TradingDeskEvent(type: .error, runId: "r", seq: 2, ts: 0,
                                 data: jobj(["message": "x", "fatal": true]))
    #expect(fatal.isTerminal)
    let soft = TradingDeskEvent(type: .error, runId: "r", seq: 3, ts: 0,
                                data: jobj(["message": "x", "fatal": false]))
    #expect(!soft.isTerminal)
}

@Test("payload decode：run.started 的 capabilities/stages")
func runStartedPayload() throws {
    let d = jobj([
        "ticker": "NVDA", "trade_date": "2026-08-30", "engine": "tradingagents",
        "capabilities": ["supports_pause": true, "supports_inject": true,
                          "supports_resume_after_restart": false],
        "stages": [["id": "analyst_market", "name": "市场分析师", "role": "分析师",
                     "group": "analyst"]],
    ])
    let payload = try #require(d.decode(as: RunStartedData.self))
    #expect(payload.ticker == "NVDA")
    #expect(payload.capabilities.supportsPause)
    #expect(payload.stages.first?.group == .analyst)
}

@Test("payload decode：verdict 全字段含可空价格")
func verdictPayload() throws {
    let d = jobj([
        "signal": "BUY", "confidence": 0.72, "size_fraction": 0.25,
        "entry_reference_price": JSONValue.null, "target_price": 180.5,
        "stop_loss": 150, "currency": "USD", "time_horizon_days": 30,
        "rationale": "理由", "warning_message": JSONValue.null,
    ])
    let v = try #require(d.decode(as: VerdictData.self))
    #expect(v.signal == .buy)
    #expect(v.confidence == 0.72)
    #expect(v.entryReferencePrice == nil)
    #expect(v.targetPrice == 180.5)
    #expect(v.warningMessage == nil)
}

@Test("RunSummary 解析（历史列表条目）")
func runSummaryDecoding() throws {
    let json = """
    {"run_id":"abc","ticker":"NVDA","trade_date":"2026-08-30","engine":"tradingagents",
     "status":"completed","duration_ms":65000,"created_at":"2026-08-30T10:00:00+00:00",
     "finished_at":null,"verdict_signal":"BUY","verdict_confidence":0.72,
     "turns_count":12,"signals_count":4}
    """
    let s = try JSONDecoder().decode(RunSummary.self, from: Data(json.utf8))
    #expect(s.status == .completed)
    #expect(s.finishedAt == nil)
    #expect(s.verdictSignal == .buy)
    #expect(s.turnsCount == 12)
}

@Test("RunDetail 的 verdict 是 dict 也可直接反序列化为 VerdictData")
func runDetailVerdict() throws {
    let json = """
    {"run_id":"abc","ticker":"NVDA","trade_date":"2026-08-30","engine":"e",
     "status":"completed","duration_ms":1,"created_at":"2026-08-30T10:00:00+00:00",
     "verdict":{"signal":"HOLD","confidence":0.5,"size_fraction":0.0,
                "entry_reference_price":null,"target_price":null,"stop_loss":null,
                "currency":null,"time_horizon_days":null,"rationale":"r",
                "warning_message":null},
     "signals":[{"stage_id":"s","name":"n","dir":"bull","conf":80,
                  "turn_id":null,"extracted":true}],
     "turns":[{"turn_id":"t1","stage_id":"s","name":"风控","role":"r","avatar":"风",
                "text":"内容","tool_calls":["lookup"],"debate":null}]}
    """
    let d = try JSONDecoder().decode(RunDetailResponse.self, from: Data(json.utf8))
    #expect(d.verdict?.signal == .hold)
    #expect(d.signals.first?.dir == .bull)
    #expect(d.turns.first?.toolCalls == ["lookup"])
}
