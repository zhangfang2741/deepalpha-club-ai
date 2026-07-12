import Foundation

/// 网络错误，携带对用户友好的中文信息（尽量透传后端 `detail`）。
struct APIError: LocalizedError {
    let message: String
    let statusCode: Int?
    var errorDescription: String? { message }

    /// 是否为「未认证」错误（触发登出跳登录页）。
    var isUnauthorized: Bool { statusCode == 401 }
}

/// 统一的 HTTP 客户端：自动带 Bearer token、解析 JSON、透传后端错误 detail。
actor APIClient {
    static let shared = APIClient()

    private let session: URLSession
    private let decoder = JSONDecoder()

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = AppConfig.requestTimeout
        config.waitsForConnectivity = true
        self.session = URLSession(configuration: config)
    }

    // MARK: - 公开方法

    func get<T: Decodable>(_ path: String, query: [String: String] = [:]) async throws -> T {
        var comps = URLComponents(url: AppConfig.baseURL.appendingPathComponent(AppConfig.apiPrefix + path),
                                  resolvingAgainstBaseURL: false)!
        if !query.isEmpty {
            comps.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        var req = URLRequest(url: comps.url!)
        req.httpMethod = "GET"
        return try await send(req)
    }

    func postJSON<T: Decodable>(_ path: String, body: Encodable) async throws -> T {
        var req = request(path: path, method: "POST")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(AnyEncodable(body))
        return try await send(req)
    }

    func delete<T: Decodable>(_ path: String) async throws -> T {
        let req = request(path: path, method: "DELETE")
        return try await send(req)
    }

    func postForm<T: Decodable>(_ path: String, fields: [String: String]) async throws -> T {
        var req = request(path: path, method: "POST")
        req.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        let encoded = fields.map { key, value in
            let k = key.addingPercentEncoding(withAllowedCharacters: .urlQueryValueAllowed) ?? key
            let v = value.addingPercentEncoding(withAllowedCharacters: .urlQueryValueAllowed) ?? value
            return "\(k)=\(v)"
        }.joined(separator: "&")
        req.httpBody = encoded.data(using: .utf8)
        return try await send(req)
    }

    // MARK: - 内部

    private func request(path: String, method: String) -> URLRequest {
        let url = AppConfig.baseURL.appendingPathComponent(AppConfig.apiPrefix + path)
        var req = URLRequest(url: url)
        req.httpMethod = method
        return req
    }

    private func send<T: Decodable>(_ request: URLRequest) async throws -> T {
        var req = request
        if let token = KeychainStore.loadToken() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: req)
        } catch {
            throw APIError(message: "网络连接失败，请检查网络后重试", statusCode: nil)
        }

        guard let http = response as? HTTPURLResponse else {
            throw APIError(message: "服务器响应异常", statusCode: nil)
        }

        guard (200..<300).contains(http.statusCode) else {
            throw APIError(message: Self.detail(from: data) ?? "请求失败（\(http.statusCode)）",
                           statusCode: http.statusCode)
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError(message: "数据解析失败，请稍后再试", statusCode: http.statusCode)
        }
    }

    /// 从 FastAPI 错误体里提取 `detail` 字段（可能是字符串或对象数组）。
    private static func detail(from data: Data) -> String? {
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        if let s = obj["detail"] as? String { return s }
        if let arr = obj["detail"] as? [[String: Any]],
           let first = arr.first, let msg = first["msg"] as? String {
            return msg
        }
        return nil
    }
}

/// 让任意 Encodable 能被泛型编码（用于 postJSON）。
private struct AnyEncodable: Encodable {
    private let encodeFunc: (Encoder) throws -> Void
    init(_ wrapped: Encodable) {
        self.encodeFunc = wrapped.encode
    }
    func encode(to encoder: Encoder) throws {
        try encodeFunc(encoder)
    }
}

private extension CharacterSet {
    /// 表单编码用：空格等需转义，`+` 也要转义避免被当成空格。
    static let urlQueryValueAllowed: CharacterSet = {
        var set = CharacterSet.alphanumerics
        set.insert(charactersIn: "-._~")
        return set
    }()
}
