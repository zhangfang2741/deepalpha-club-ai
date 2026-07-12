import Foundation

/// 缠论相关接口封装。
enum ChanService {
    /// 拉取完整缠论分析。
    static func analysis(symbol: String, startDate: String, endDate: String,
                         freq: String = "daily") async throws -> ChanAnalysis {
        try await APIClient.shared.get("/chan/analysis", query: [
            "symbol": symbol.uppercased(),
            "start_date": startDate,
            "end_date": endDate,
            "freq": freq,
        ])
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

/// 认证接口封装。
enum AuthService {
    /// 登录：form-urlencoded，字段名为 email。
    static func login(email: String, password: String) async throws -> LoginResponse {
        try await APIClient.shared.postForm("/auth/login", fields: [
            "email": email,
            "password": password,
            "grant_type": "password",
        ])
    }

    /// 获取当前用户资料。
    static func me() async throws -> UserProfile {
        try await APIClient.shared.get("/auth/me")
    }

    /// 删除当前账号（不可恢复）。App Store 5.1.1(v) 要求。
    @discardableResult
    static func deleteAccount() async throws -> MessageResponse {
        try await APIClient.shared.delete("/auth/me")
    }
}

/// 通用 `{"message": "..."}` 响应。
struct MessageResponse: Codable {
    let message: String
}
