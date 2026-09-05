import Foundation

/// typed API 错误。401 全局处理（清 token 回登录），其余顶部 banner 展示 message。
public enum APIError: Error, Sendable, Equatable {
    /// 401。关联值是服务端 detail：登录接口返回的是「账号或密码错误」，
    /// 而 token 过期才是「登录已过期」——两者都走 401，固定文案会误导用户。
    case unauthorized(String?)
    case notFound           // 404
    case validation(String) // 422（如 inject 空 text）
    case server(Int, String)// 其他 4xx/5xx，附中文 detail
    case network            // 连接层（无网 / 超时 / TLS）
    case decoding           // 响应体解析失败

    /// 是否 401（调用方一般只关心「要不要清 token 回登录」，不关心文案）。
    public var isUnauthorized: Bool {
        if case .unauthorized = self { return true }
        return false
    }

    /// 重试是否可能成功。401 要换 token、404 的资源不存在、422 是入参不合法，
    /// 这三类重试多少次结果都一样，SSE 重连循环必须据此停手。
    public var isRetryable: Bool {
        switch self {
        case .unauthorized, .notFound, .validation: false
        case .server, .network, .decoding: true
        }
    }

    /// 用户可读消息（对齐 web getApiErrorMessage 的角色）。
    public var message: String {
        switch self {
        case .unauthorized(let m): m ?? "登录已过期，请重新登录"
        case .notFound: "资源不存在"
        case .validation(let m): m
        case .server(_, let m): m
        case .network: "网络不可用，请检查连接"
        case .decoding: "响应解析失败"
        }
    }

    /// 由 HTTP 状态码 + body（FastAPI {"detail": ...}）构造。
    static func from(status: Int, body: Data?) -> APIError {
        let detail = Self.detailText(body: body)
        let message = detail ?? defaultText(for: status)
        switch status {
        case 401: return .unauthorized(detail)
        case 404: return .notFound
        case 422: return .validation(message)
        default: return .server(status, message)
        }
    }

    /// 提取 FastAPI 错误 body 的 detail（可能是字符串，也可能是 {"message": ...} dict）。
    private static func detailText(body: Data?) -> String? {
        guard let data = body else { return nil }
        // {"detail": "msg"}
        if let obj = try? JSONDecoder().decode([String: String].self, from: data),
           let m = obj["detail"] { return m }
        // {"detail": {"message": "msg", ...}}
        if let obj = try? JSONDecoder().decode([String: [String: String]].self, from: data),
           let m = obj["detail"]?["message"] { return m }
        return nil
    }

    private static func defaultText(for status: Int) -> String {
        switch status {
        case 400..<500: "请求失败（HTTP \(status)）"
        default: "服务器错误（HTTP \(status)）"
        }
    }
}
