import Testing
@testable import DeepAlphaCore

@Test("标准帧：id + data 各一行")
func standard() throws {
    let raw = "id: 1753900000000-0\ndata: {\"type\":\"run.started\",\"run_id\":\"r1\",\"seq\":1,\"ts\":1,\"data\":{}}"
    let frame = try #require(SSEFrameParser.parse(raw))
    #expect(frame.id == "1753900000000-0")
    #expect(frame.event.type == .runStarted)
    #expect(frame.event.runId == "r1")
}

@Test("无 id 帧也能解析（id 为 nil）")
func noId() throws {
    let raw = "data: {\"type\":\"run.paused\",\"run_id\":\"r1\",\"seq\":2,\"ts\":1,\"data\":{}}"
    let frame = try #require(SSEFrameParser.parse(raw))
    #expect(frame.id == nil)
    #expect(frame.event.type == .runPaused)
}

@Test("多行 data 拼接（JSON 被分行发送的兼容）")
func multiLineData() throws {
    let raw = "data: {\"type\":\"agent.token\",\"run_id\":\"r\",\"seq\":1,\"ts\":1,\ndata: \"data\":{\"text\":\"a\\nb\"}}"
    let frame = try #require(SSEFrameParser.parse(raw))
    #expect(frame.event.data?["text"]?.string == "a\nb")
}

@Test("只有 id 没有 data 返回 nil")
func idOnly() {
    #expect(SSEFrameParser.parse("id: 123") == nil)
}

@Test("data 非法 JSON 丢弃（不掐断整条流）")
func badJson() {
    #expect(SSEFrameParser.parse("data: {not-json") == nil)
}

@Test("注释行（心跳）不在帧内——由 client 层跳过，但防御性支持")
func commentLine() throws {
    let raw = ":\ndata: {\"type\":\"run.resumed\",\"run_id\":\"r\",\"seq\":3,\"ts\":1,\"data\":{}}"
    let frame = try #require(SSEFrameParser.parse(raw))
    #expect(frame.event.type == .runResumed)
}
