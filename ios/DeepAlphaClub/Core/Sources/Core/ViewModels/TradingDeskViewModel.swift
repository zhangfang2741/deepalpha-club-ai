import Foundation
import Observation

/// 交易台主 VM：持有 state，负责 startRun / control / SSE 消费循环 / 前后台切换。
@MainActor @Observable
public final class TradingDeskViewModel {
    public var state = TradingDeskState()
    /// 控制类请求进行中（禁用按钮），对齐 web 版 busy
    public private(set) var busy = false
    /// 页面级错误（createRun/control 失败等，顶部 banner）
    public private(set) var pageError: String?
    /// 最近一次 401（App 层观察它清 token 回登录）
    public private(set) var lastAuthError: APIError?

    let service: any TradingDeskServicing
    /// 重连退避的 sleep（测试注入零等待 / 记录时长）。
    var sleeper: @Sendable (Duration) async throws -> Void = { try await Task.sleep(for: $0) }
    private var consumeTask: Task<Void, Never>?

    public init(service: any TradingDeskServicing) {
        self.service = service
    }

    public var live: Bool { state.status == .running || state.status == .paused }

    // MARK: - 启动 / 控制

    public func startRun(ticker raw: String, market: Market) async {
        let symbol = TickerResolver.resolve(raw: raw, market: market)
        guard !symbol.isEmpty else { return }
        pageError = nil
        busy = true
        defer { busy = false }
        do {
            let runId = try await service.createRun(ticker: symbol)
            state = TradingDeskState()          // 重置
            state.runId = runId
            state.ticker = symbol
            state.status = .running
            consume(runId: runId)
        } catch let e as APIError {
            if e.isUnauthorized { lastAuthError = e }
            pageError = e.message
        } catch {
            pageError = "启动失败：\(error.localizedDescription)"
        }
    }

    public func control(_ action: ControlAction, text: String? = nil) async {
        guard let runId = state.runId else { return }
        busy = true
        defer { busy = false }
        do {
            try await service.control(runId: runId, action: action, text: text)
        } catch let e as APIError {
            if e.isUnauthorized { lastAuthError = e }
            pageError = e.message
        } catch {
            pageError = error.localizedDescription
        }
    }

    // MARK: - SSE 消费（无限重连，移植 web consume）

    func consume(runId: String) {
        consumeTask?.cancel()
        consumeTask = Task { [weak self] in
            await self?.runLoop(runId: runId)
        }
    }

    private func runLoop(runId: String) async {
        var backoff: Duration = .milliseconds(800)
        while !Task.isCancelled {
            do {
                let lastId = state.lastEventId
                for try await frame in service.stream(runId: runId, lastEventId: lastId) {
                    apply(frame)
                }
                return   // 流正常结束：服务端关流，不重连（对齐 web）
            } catch {
                if Task.isCancelled { return }
                // 只有还活着才重连；终态（completed/failed/...）直接退出
                guard live else { return }
                try? await sleeper(backoff)
                if Task.isCancelled { return }
                backoff = min(backoff * 2, .seconds(30))
            }
        }
    }

    /// 单帧应用：seq 去重（重连重放）→ reduce → 更新 lastEventId 游标。
    func apply(_ frame: SseFrame) {
        guard frame.event.seq > state.lastSeq else { return }
        state = TradingDeskReducer.reduce(state, frame.event)
        state.lastEventId = frame.id ?? state.lastEventId
        state.lastSeq = frame.event.seq
    }

    // MARK: - 前后台切换

    /// 进后台：断开 SSE（iOS 后台网络保活不可靠），游标已在 state。
    public func appDidEnterBackground() {
        consumeTask?.cancel()
        consumeTask = nil
    }

    /// 回前台：仍 live 则用 lastEventId 续订（不丢不重）。
    public func appDidBecomeActive() async {
        guard live, let runId = state.runId, consumeTask == nil else { return }
        consume(runId: runId)
        // 给 runLoop 一点启动时间，让测试可观测；生产无副作用
        try? await Task.sleep(for: .milliseconds(10))
    }

    public func clearPageError() { pageError = nil }
}
