import Foundation

/// typed API 错误。401 全局处理（清 token 回登录），其余顶部 banner 展示 message。
public enum APIError: Error, Sendable, Equatable {
    case unauthorized       // 401
    case notFound           // 404
    case validation(String) // 422（如 inject 空 text）
    case server(Int, String)// 其他 4xx/5xx，附中文 detail
    case network            // 连接层（无网 / 超时 / TLS）
    case decoding           // 响应体解析失败

    /// 用户可读消息（对齐 web getApiErrorMessage 的角色）。
    public var message: String {
        switch self {
        case .unauthorized: "登录已过期，请重新登录"
        case .notFound: "资源不存在"
        case .validation(let m): m
        case .server(_, let m): m
        case .network: "网络不可用，请检查连接"
        case .decoding: "响应解析失败"
        }
    }

    /// 由 HTTP 状态码 + body（FastAPI {"detail": ...}）构造。
    static func from(status: Int, body: Data?) -> APIError {
        let message = Self.detailText(body: body) ?? defaultText(for: status)
        switch status {
        case 401: return .unauthorized
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
