import Foundation

/// 晨报接口封装：获取、历史日期、设备 token 注册（推送）。
enum MorningReportService {
    /// 拉取晨报。`date` 为 nil 时取当日（后端自动回退最近一期并标 stale）。
    static func report(market: String, date: String? = nil) async throws -> MorningReportResponse {
        var query = ["market": market]
        if let date { query["report_date"] = date }
        return try await APIClient.shared.get("/morning-report", query: query)
    }

    /// 历史可用日期（倒序，YYYY-MM-DD）。
    static func dates(market: String) async throws -> ReportDatesResponse {
        try await APIClient.shared.get("/morning-report/dates", query: ["market": market])
    }

    /// 注册/刷新 APNs 设备 token；登录后与切换语言后调用。
    static func registerDeviceToken(_ token: String, locale: String) async throws {
        struct Body: Encodable { let token: String; let locale: String }
        let ack: AckResponse = try await APIClient.shared.postJSON(
            "/morning-report/device-token",
            body: Body(token: token, locale: locale))
        guard ack.ok else { throw APIError(message: "注册失败", statusCode: nil) }
    }
}
