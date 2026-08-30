import Foundation

/// 通用 HTTP 客户端：token 注入、状态码→APIError 映射、JSON 编解码。
/// 协议无抽象——直接 struct，测试注入 MockURLProtocol 的 session。
public struct APIClient: Sendable {
    public let baseURL: URL
    public let session: URLSession
    public let tokenProvider: @Sendable () -> String?

    public init(baseURL: URL,
                session: URLSession = .shared,
                tokenProvider: @escaping @Sendable () -> String? = { nil }) {
        self.baseURL = baseURL
        self.session = session
        self.tokenProvider = tokenProvider
    }

    public func get<Response: Decodable>(_ path: String,
                                         query: [String: String] = [:]) async throws -> Response {
        var components = URLComponents(
            url: URL(string: baseURL.absoluteString + path)!,
            resolvingAgainstBaseURL: false)!
        if !query.isEmpty {
            components.queryItems = query.sorted { $0.key < $1.key }
                .map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        var request = try authorizedRequest(url: components.url!)
        request.httpMethod = "GET"
        return try await send(request)
    }

    public func post<Response: Decodable>(_ path: String,
                                          json: some Encodable) async throws -> Response {
        var request = try request(path: path)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(json)
        return try await send(request)
    }

    /// form-urlencoded POST（登录端点用 Form(...)，非 JSON）。
    /// 编码用 RFC 3986 unreserved 集：`+`/`@`/空格 等全部转义——
    /// URLComponents 的 percentEncodedQuery 会保留 `+`，后端按标准把它
    /// 解析成空格，密码含 + 时会被改写。
    public func postForm<Response: Decodable>(_ path: String,
                                              fields: [String: String]) async throws -> Response {
        var request = try request(path: path)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        request.httpBody = Data(Self.formEncode(fields).utf8)
        return try await send(request)
    }

    private static let formAllowed: CharacterSet = {
        var set = CharacterSet.alphanumerics
        set.insert(charactersIn: "-._~")
        return set
    }()

    private static func formEncode(_ fields: [String: String]) -> String {
        func enc(_ s: String) -> String {
            s.addingPercentEncoding(withAllowedCharacters: formAllowed) ?? s
        }
        return fields.sorted { $0.key < $1.key }
            .map { "\(enc($0.key))=\(enc($0.value))" }
            .joined(separator: "&")
    }

    private func request(path: String) throws -> URLRequest {
        guard let url = URL(string: baseURL.absoluteString + path) else {
            throw APIError.decoding
        }
        return try authorizedRequest(url: url)
    }

    /// 构造带 Authorization 头的请求（GET/POST 共用）。
    private func authorizedRequest(url: URL) throws -> URLRequest {
        var request = URLRequest(url: url)
        if let token = tokenProvider() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    private func send<Response: Decodable>(_ request: URLRequest) async throws -> Response {
        let data: Data
        let rawResponse: URLResponse
        do {
            (data, rawResponse) = try await session.data(for: request)
        } catch {
            throw APIError.network
        }
        guard let response = rawResponse as? HTTPURLResponse else {
            throw APIError.network
        }
        guard (200..<300).contains(response.statusCode) else {
            throw APIError.from(status: response.statusCode, body: data)
        }
        do {
            return try JSONDecoder().decode(Response.self, from: data)
        } catch {
            throw APIError.decoding
        }
    }
}
