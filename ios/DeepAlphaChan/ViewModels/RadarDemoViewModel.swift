import Foundation

/// 免费预览：拉「上个月 1 号」这一天的真实雷达快照（GET /signal-radar/demo），
/// 是未订阅高级版用户唯一能点开的一天。轮询逻辑是 SignalRadarViewModel.load 的
/// 简化版——没有 universe 切换/日期选择这些高级版专属的复杂度，只跟着市场切换重拉。
@MainActor
final class RadarDemoViewModel: ObservableObject {
    @Published private(set) var day: RadarDay?
    @Published private(set) var isLoading = false
    @Published var errorMessage: String?
    /// 轮询用尽但后端仍在算（这个月第一次有人打开、冷启动时会遇到）。
    @Published private(set) var isComputingInBackground = false

    private let maxPolls = 8
    private let pollInterval: UInt64 = 2_000_000_000       // 起始 2s
    private let maxPollInterval: UInt64 = 6_000_000_000    // 封顶 6s

    /// 由 `.task(id: market)` 驱动调用：市场变化时 SwiftUI 自动取消上一次未完成的
    /// load、重新调用一次，不需要自己再判断"要不要重拉"。
    func load(market: StockMarket) async {
        isLoading = true
        errorMessage = nil
        isComputingInBackground = false
        day = nil
        do {
            var resp = try await SignalRadarService.demo(market: market.rawValue)
            var tries = 0
            var delay = pollInterval
            while resp.isGenerating && tries < maxPolls {
                try Task.checkCancellation()
                try await Task.sleep(nanoseconds: delay)
                resp = try await SignalRadarService.demo(market: market.rawValue)
                tries += 1
                delay = min(delay + 1_000_000_000, maxPollInterval)
            }
            try Task.checkCancellation()
            if resp.isGenerating {
                isComputingInBackground = true
            } else {
                day = resp.days.first
            }
        } catch is CancellationError {
            return
        } catch let e as APIError {
            errorMessage = e.message
        } catch {
            errorMessage = "加载失败，请稍后再试"
        }
        isLoading = false
    }
}
