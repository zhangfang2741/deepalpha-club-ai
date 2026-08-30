import Testing
@testable import Core

/// 测试辅助：构造事件。
func ev(_ type: EventType, seq: Int, data: JSONValue? = .object([:])) -> TradingDeskEvent {
    TradingDeskEvent(type: type, runId: "r1", seq: seq, ts: 0, data: data)
}

@Suite("TradingDeskReducer")
struct TradingDeskReducerTests {
    @Test("run.started：初始化 stages 全 pending + 状态 running")
    func runStarted() {
        var s = TradingDeskState()
        s = TradingDeskReducer.reduce(s, ev(.runStarted, seq: 1, data: .object([
            "ticker": "NVDA", "trade_date": "2026-08-30", "engine": "tradingagents",
            "capabilities": ["supports_pause": true, "supports_inject": true,
                              "supports_resume_after_restart": false],
            "stages": [
                ["id": "a", "name": "分析师A", "role": "analyst", "group": "analyst"],
                ["id": "b", "name": "辩论", "role": "bull", "group": "debate"],
            ],
        ])))
        #expect(s.status == .running)
        #expect(s.ticker == "NVDA")
        #expect(s.capabilities.supportsPause)
        #expect(s.stages.count == 2)
        #expect(s.stageStatus == ["a": .pending, "b": .pending])
    }

    @Test("stage.active / stage.done 更新对应 stage")
    func stageLifecycle() {
        var s = TradingDeskState()
        s.stageStatus = ["a": .pending]
        s = TradingDeskReducer.reduce(s, ev(.stageActive, seq: 2, data: ["stage_id": "a"]))
        #expect(s.stageStatus["a"] == .active)
        s = TradingDeskReducer.reduce(s, ev(.stageDone, seq: 3, data: ["stage_id": "a"]))
        #expect(s.stageStatus["a"] == .done)
    }

    @Test("turn.started + agent.token 累加 + turn.done")
    func turnLifecycle() {
        var s = TradingDeskState()
        s = TradingDeskReducer.reduce(s, ev(.turnStarted, seq: 1, data: [
            "turn_id": "t1", "stage_id": "a", "name": "市场分析师",
            "role": "r", "avatar": "市"]))
        s = TradingDeskReducer.reduce(s, ev(.agentToken, seq: 2, data: ["turn_id": "t1", "text": "第一"]))
        s = TradingDeskReducer.reduce(s, ev(.agentToken, seq: 3, data: ["turn_id": "t1", "text": "段"]))
        #expect(s.turns.count == 1)
        #expect(s.turns[0].text == "第一段")
        #expect(!s.turns[0].done)
        s = TradingDeskReducer.reduce(s, ev(.turnDone, seq: 4, data: ["turn_id": "t1"]))
        #expect(s.turns[0].done)
    }

    @Test("agent.think 折叠到 thinking 字段")
    func thinkTokens() {
        var s = TradingDeskState()
        s = TradingDeskReducer.reduce(s, ev(.turnStarted, seq: 1, data: [
            "turn_id": "t1", "stage_id": "a", "name": "n", "role": "", "avatar": ""]))
        s = TradingDeskReducer.reduce(s, ev(.agentThink, seq: 2, data: ["turn_id": "t1", "text": "思考"]))
        s = TradingDeskReducer.reduce(s, ev(.agentThink, seq: 3, data: ["turn_id": "t1", "text": "…"]))
        #expect(s.turns[0].thinking == "思考…")
    }

    @Test("agent.tool_call 追加工具名")
    func toolCall() {
        var s = TradingDeskState()
        s = TradingDeskReducer.reduce(s, ev(.turnStarted, seq: 1, data: [
            "turn_id": "t1", "stage_id": "a", "name": "n", "role": "", "avatar": ""]))
        s = TradingDeskReducer.reduce(s, ev(.agentToolCall, seq: 2, data: [
            "turn_id": "t1", "tool": "lookup_ticker"]))
        s = TradingDeskReducer.reduce(s, ev(.agentToolCall, seq: 3, data: [
            "turn_id": "t1", "tool": "get_financials", "args": ["ticker": "NVDA"]]))
        #expect(s.turns[0].tools == ["lookup_ticker", "get_financials"])
    }

    @Test("agent.signal：signals 追加 + stageSignal + 回填 turn")
    func signal() {
        var s = TradingDeskState()
        s.turns = [Turn(turnId: "t1", stageId: "a", name: "n", role: "", avatar: "",
                        text: "", tools: [], done: false, human: false, debate: nil, signal: nil)]
        s = TradingDeskReducer.reduce(s, ev(.agentSignal, seq: 2, data: [
            "stage_id": "a", "name": "市场分析师", "dir": "bull", "conf": 78,
            "turn_id": "t1", "extracted": true]))
        #expect(s.signals.count == 1)
        #expect(s.signals[0] == SignalRow(name: "市场分析师", dir: .bull, conf: 78, extracted: true))
        #expect(s.stageSignal["a"] == StageSignal(dir: .bull, conf: 78))
        #expect(s.turns[0].signal?.conf == 78)
    }

    @Test("debate.turn：回填辩论元数据")
    func debate() {
        var s = TradingDeskState()
        s.turns = [Turn(turnId: "t1", stageId: "a", name: "n", role: "", avatar: "",
                        text: "", tools: [], done: false, human: false, debate: nil, signal: nil)]
        s = TradingDeskReducer.reduce(s, ev(.debateTurn, seq: 2, data: [
            "stage_id": "a", "debate_id": "d1", "side": "bull", "side_label": "看多方",
            "polarity": "bull", "round": 2, "turn_id": "t1"]))
        #expect(s.turns[0].debate?.sideLabel == "看多方")
        #expect(s.turns[0].debate?.round == 2)
    }

    @Test("human.note：插入人工卡片（turnId 用 seq 保证唯一）")
    func humanNote() {
        var s = TradingDeskState()
        s = TradingDeskReducer.reduce(s, ev(.humanNote, seq: 7, data: ["text": "注意出口管制"]))
        #expect(s.turns.count == 1)
        #expect(s.turns[0].turnId == "human-7")
        #expect(s.turns[0].human)
        #expect(s.turns[0].text == "注意出口管制")
    }

    @Test("consensus.update / verdict / run.paused / run.resumed / run.finished / error")
    func miscEvents() {
        var s = TradingDeskState()
        s = TradingDeskReducer.reduce(s, ev(.consensusUpdate, seq: 1, data: [
            "bull": 3, "neutral": 1, "bear": 2, "lean": "偏多"]))
        #expect(s.consensus?.bull == 3)
        s = TradingDeskReducer.reduce(s, ev(.verdict, seq: 2, data: [
            "signal": "BUY", "confidence": 0.8, "size_fraction": 0.25,
            "entry_reference_price": nil, "target_price": 200, "stop_loss": 160,
            "currency": "USD", "time_horizon_days": 30, "rationale": "r", "warning_message": nil]))
        #expect(s.verdict?.signal == .buy)
        s = TradingDeskReducer.reduce(s, ev(.runPaused, seq: 3))
        #expect(s.status == .paused)
        s = TradingDeskReducer.reduce(s, ev(.runResumed, seq: 4))
        #expect(s.status == .running)
        s = TradingDeskReducer.reduce(s, ev(.runFinished, seq: 5, data: [
            "status": "completed", "duration_ms": 61000]))
        #expect(s.status == .completed)
        #expect(s.durationMs == 61000)
        s = TradingDeskReducer.reduce(s, ev(.error, seq: 6, data: [
            "message": "LLM 超时", "fatal": false]))
        #expect(s.error == "LLM 超时")
    }

    @Test("run.finished 的 status 字符串映射 RunStatus")
    func finishedStatusMapping() {
        var s = TradingDeskState()
        s.status = .running
        for (raw, expected) in [("cancelled", RunStatus.cancelled), ("failed", .failed),
                                 ("interrupted", .interrupted), ("completed", .completed)] {
            s = TradingDeskReducer.reduce(s, ev(.runFinished, seq: s.lastSeq + 1, data: [
                "status": JSONValue.string(raw), "duration_ms": 0]))
            #expect(s.status == expected)
        }
    }

    @Test("buildAuditChain：有文本的 turn 生成条目，human 标注，辩论带轮次")
    func auditChain() {
        let turns = [
            Turn(turnId: "t1", stageId: "a", name: "分析师", role: "", avatar: "",
                 text: "第一条内容", tools: [], done: true, human: false, debate: nil, signal: nil),
            Turn(turnId: "t2", stageId: "a", name: "", role: "", avatar: "",
                 text: "   ", tools: [], done: true, human: false, debate: nil, signal: nil),
            Turn(turnId: "t3", stageId: "a", name: "看多方", role: "", avatar: "",
                 text: "很长的一段话超过四十个字符的话就会被截断掉后面用省略号显示出来的所以这里要写足够长",
                 tools: [], done: true, human: false,
                 debate: DebateInfo(debateId: "d", side: "bull", sideLabel: "看多",
                                     polarity: .bull, round: 1), signal: nil),
            Turn(turnId: "h1", stageId: "", name: "你", role: "人工意见", avatar: "你",
                 text: "人工意见", tools: [], done: true, human: true, debate: nil, signal: nil),
        ]
        let chain = TradingDeskReducer.buildAuditChain(turns)
        #expect(chain.count == 3) // 空白文本的 t2 被过滤
        #expect(chain[0].who == "分析师")
        #expect(chain[1].who.contains("第 1 轮"))
        #expect(chain[1].excerpt.hasSuffix("…"))
        #expect(chain[2].human)
        #expect(chain[2].who == "你")
    }
}
