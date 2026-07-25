import Foundation

/// 网络错误，携带对用户友好的中文信息（尽量透传后端 detail）。
struct APIError: LocalizedError {
    let message: String
    let statusCode: Int?
    var errorDescription: String? { message }

    /// 是否为「未认证」错误（触发登出跳登录页）。
    var isUnauthorized: Bool { statusCode == 401 }
}

extension Notification.Name {
    /// 带 token 的请求收到 401 时广播，AuthViewModel 监听后自动登出、跳回登录页。
    static let apiUnauthorized = Notification.Name("apiUnauthorized")
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

    /// 上传图片（multipart/form-data，图片字段名固定为 "image"，匹配后端
    /// `UploadFile = File(...)` 的参数名）。
    ///
    /// - Parameter textFields: 附带的文本表单字段（名称, 值），可重复同名（如把
    ///   OCR 候选词逐个作为同名 `ocr_words` 字段发出，后端按 `list[str]` 接收）。
    func postMultipartImage<T: Decodable>(
        _ path: String,
        imageData: Data,
        filename: String = "photo.jpg",
        textFields: [(name: String, value: String)] = []
    ) async throws -> T {
        var req = request(path: path, method: "POST")
        let boundary = "Boundary-\(UUID().uuidString)"
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = AppConfig.recognizeTimeout

        var body = Data()
        for field in textFields {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"\(field.name)\"\r\n\r\n".data(using: .utf8)!)
            body.append(field.value.data(using: .utf8)!)
            body.append("\r\n".data(using: .utf8)!)
        }
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"image\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
        body.append(imageData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        req.httpBody = body

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
        let token = KeychainStore.loadToken()
        if let token {
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
            let error = APIError(message: Self.detail(from: data) ?? "请求失败（\(http.statusCode)）",
                                  statusCode: http.statusCode)
            // 只有「带着 token 的请求」被判定未认证才算会话过期——登录/注册本身返回
            // 401（账号密码错）不该触发登出，那时候根本没带 token。
            if error.isUnauthorized && token != nil {
                NotificationCenter.default.post(name: .apiUnauthorized, object: nil)
            }
            throw error
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
