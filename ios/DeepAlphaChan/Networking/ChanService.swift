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
        ]
        // 信号雷达点进详情时传 0：不额外加 warmup，取数区间与雷达完全一致。
        if let warmupDays { query["warmup_days"] = String(warmupDays) }
        return try await APIClient.shared.get("/chan/analysis", query: query)
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
