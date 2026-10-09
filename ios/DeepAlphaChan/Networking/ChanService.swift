import Foundation

/// 缠论相关接口封装。
enum ChanService {
    /// 拉取完整缠论分析。
    static func analysis(symbol: String, startDate: String, endDate: String,
                         freq: String = "daily", warmupDays: Int? = nil) async throws -> ChanAnalysis {
        var query = [
            "symbol": symbol.uppercased(),
            "start_date": startDate,
            "end_date": endDate,
            "freq": freq,
            // 让后端按当前界面语言返回分析正文（趋势/形态解读/依据/买卖点描述）
            "lang": Localized.language() == .english ? "en" : "zh",
            // 买卖点口径（App 固定宽松），见 SignalMode
            "mode": SignalMode.current(),
        ]
        // 兼容旧后端保留；现后端忽略该参数、始终预热 180 天（与雷达取数区间一致）。
        if let warmupDays { query["warmup_days"] = String(warmupDays) }
        return try await APIClient.shared.get("/chan/analysis", query: query)
    }

    /// 按名称 / 代码联想搜股票（A 股、港股、美股中文名都能搜）。
    static func searchSymbols(query: String, market: StockMarket, limit: Int = 8) async throws -> [SymbolHit] {
        try await APIClient.shared.get("/chan/symbol-search", query: [
            "q": query, "market": market.rawValue, "limit": String(limit),
        ])
    }

    /// 次级别确认：大级别（与分析详情页同一窗口）定方向 × 次级别近期买卖点。
    /// 日线配 30 分钟近两日、周线配日线近两周；次级别取不到时后端仍返回 200，verdict 为 unavailable。
    static func subLevel(symbol: String, startDate: String, endDate: String,
                         parentFreq: String = "daily",
                         warmupDays: Int? = nil) async throws -> SubLevel {
        var query = [
            "symbol": symbol.uppercased(),
            "start_date": startDate,
            "end_date": endDate,
            "parent_freq": parentFreq,
            "lang": Localized.language() == .english ? "en" : "zh",
            "mode": SignalMode.current(),
        ]
        if let warmupDays { query["warmup_days"] = String(warmupDays) }
        return try await APIClient.shared.get("/chan/sub-level", query: query)
    }

    /// 提交结构 GAP 异步任务，返回 job_id。
    static func submitGap(symbol: String, startDate: String, endDate: String,
                          industryView: String, freq: String = "daily") async throws -> GapJobStatus {
        struct Body: Encodable {
            let symbol: String
            let start_date: String
            let end_date: String
            let industry_view: String
            let freq: String
        }
        return try await APIClient.shared.postJSON("/chan/gap", body: Body(
            symbol: symbol.uppercased(), start_date: startDate, end_date: endDate,
            industry_view: industryView, freq: freq))
    }

    /// 轮询 GAP 任务状态。
    static func gapStatus(jobId: String) async throws -> GapJobStatus {
        try await APIClient.shared.get("/chan/gap/\(jobId)")
    }
}
