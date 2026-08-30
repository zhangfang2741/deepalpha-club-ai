import Foundation
import Observation

/// 历史列表：SwiftData 先渲染（秒开），远端刷新替换并回写缓存。
@MainActor @Observable
public final class HistoryListViewModel {
    public private(set) var runs: [RunSummary] = []
    public private(set) var loading = false
    public var error: String?

    let service: any TradingDeskServicing
    let cache: RunCache?

    public init(service: any TradingDeskServicing, cache: RunCache?) {
        self.service = service
        self.cache = cache
    }

    public func refresh(ticker: String?) async {
        self.error = nil
        loading = true
        defer { loading = false }
        // 1) 本地缓存先出（离线可用）
        if let cache {
            if let local = try? await cache.list(ticker: ticker) {
                runs = local
            }
        }
        // 2) 远端刷新
        do {
            let resp = try await service.listRuns(ticker: ticker, limit: 50, offset: 0)
            runs = resp.runs
            // 3) 回写缓存（失败不影响 UI）
            if let cache {
                try? await cache.upsert(resp.runs)
            }
        } catch let e as APIError {
            self.error = e.message
        } catch {
            self.error = "拉取失败：\(error.localizedDescription)"
        }
    }
}
