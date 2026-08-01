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
        config.timeoutIntervalForResource = AppConfig.resourceTimeout
        // 让 URLSession 在网络暂时不通时挂起等待（地铁/电梯里识别请求不会立刻失败），
        // 同时不会无限等待——resourceTimeout 是硬上限。
        config.waitsForConnectivity = true
        self.session = URLSession(configuration: config)
    }

    // MARK: - Retry helper

    /// 把一次网络调用包成"URLError.networkConnectionLost 自动重试一次"。
    ///
    /// Railway / Cloudflare 这类边缘代理在 keep-alive 连接 idle 一段时间后，
    /// 会把通道 RST 掉——CFNetwork 把它报告成 -1005 (networkConnectionLost)。
    /// 移动网络下偶发，重试一次成功率非常高。但重试不能无限次（体感延迟
    /// + 用户已经看到 spinner 在转），只重试一次；其它 URLError（如
    /// `.notConnectedToInternet` 没 Wi-Fi / 信号、`.timedOut` 服务器卡）
    /// 不重试，直接抛出去让上层显示对应文案——避免无意义地掩盖真正的
    /// 网络问题。
    private static func attemptWithRetry<T>(_ body: () async throws -> T) async throws -> T {
        do {
            return try await body()
        } catch let error as URLError where error.code == .networkConnectionLost {
            // 一次 300ms 退避：代理层通常就能完成 internal connection re-establish，
            // 体感上还停留在 spinner 阶段。重试如果还是 -1005, 把第二次的原始错误
            // 原样抛出去（不再重试），让上层进入正常错误处理路径。
            try? await Task.sleep(for: .milliseconds(300))
            return try await body()
        }
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

    func patchJSON<T: Decodable>(_ path: String, body: Encodable) async throws -> T {
        var req = request(path: path, method: "PATCH")
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
    /// 走 `URLSessionUploadTask` 而不是 `URLSessionDataTask` + httpBody：图片
    /// 上传是"持续写 + 服务器处理 + 流式回包"的长流程，dataTask 在图片 multipart
    /// 拼装完整体放进 httpBody 后，URLSession 需要先把整个 body 写到 socket 上
    /// 再开始接收响应——这段写窗口里 socket 是"只写不读"，如果图片体积较大或
    /// 系统进入低功耗状态，CFNetwork 可能在 idle 窗口里把底层 socket 直接
    /// reset（NSURLErrorNetworkConnectionLost -1005）。uploadTask 内部用临时
    /// 文件做流式上传，写过程持续触发 TCP ACK，能稳定避开 idle reset。
    ///
    /// - Parameters:
    ///   - textFields: 附带的文本表单字段（名称, 值），可重复同名（如把
    ///     OCR 候选词逐个作为同名 `ocr_words` 字段发出，后端按 `list[str]` 接收）。
    ///   - onPartial: 可选，NDJSON 响应流里每出现一条 `partial` 事件就回调一次
    ///     （用 `NDJSONStreamUploader` 边收边解析响应体，而不是等整条流收完）。
    ///     传 nil 时退化为原来的行为：`session.upload(for:fromFile:)` 拿到完整
    ///     响应体后再一次性解码。
    func postMultipartImage<T: Decodable>(
        _ path: String,
        imageData: Data,
        filename: String = "photo.jpg",
        textFields: [(name: String, value: String)] = [],
        onPartial: (@Sendable (RecognizeResponse) -> Void)? = nil
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
        let bodyData = body

        // uploadTask 需要临时文件 URL 承载流式 body——系统会分块读取上传，触发
        // 持续的 socket 写流量，避免 idle reset。
        let tempURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("upload-\(UUID().uuidString).bin")
        try? FileManager.default.removeItem(at: tempURL)
        do {
            try bodyData.write(to: tempURL)
        } catch {
            throw APIError(message: "上传准备失败", statusCode: nil)
        }

        do {
            let token = KeychainStore.loadToken()
            if let token {
                req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            }
            // uploadTask 默认走 application/octet-stream，但 httpBody 留空时它
            // 会用文件后缀识别 .bin——明确指定 Content-Type 避免歧义。
            let data: Data
            let response: URLResponse
            if let onPartial {
                // NDJSONStreamUploader 自己消费了字节流，半路挂掉的状态难恢复——上层
                // onPartial 失败就该直接 user-visible 报错, 不在底层做 retry.
                (data, response) = try await NDJSONStreamUploader(onPartial: onPartial)
                    .upload(request: req, fromFile: tempURL, configuration: session.configuration)
            } else {
                // 普通 upload: -1005 自动重试一次, 加入生词库的批量上传能扛一截
                // Railway 边缘代理 RST. retry 直接复用同一个临时文件 (fromFile),
                // 不会把图片重新编码 / 重拼 multipart boundary.
                (data, response) = try await Self.attemptWithRetry {
                    try await session.upload(for: req, fromFile: tempURL)
                }
            }
            try? FileManager.default.removeItem(at: tempURL)
            if let http = response as? HTTPURLResponse,
               (200..<300).contains(http.statusCode),
               http.value(forHTTPHeaderField: "Content-Type")?.contains("application/x-ndjson") == true {
                do {
                    return try NDJSONStreamDecoder.decode(T.self, from: data)
                } catch let error as NDJSONStreamDecodeError {
                    throw APIError(message: error.errorDescription ?? "识别失败，请重试", statusCode: nil)
                }
            }
            return try Self.process(data: data, response: response, sentToken: token)
        } catch let apiError as APIError {
            try? FileManager.default.removeItem(at: tempURL)
            throw apiError
        } catch {
            try? FileManager.default.removeItem(at: tempURL)
            // URLSession 把 -1005 这类底层错误包装成 URLError，统一映射成对用户
            // 友好的中文（之前的 catch 已经覆盖了大部分情况）。
            if let urlError = error as? URLError {
                throw APIError(message: Self.friendlyMessage(for: urlError), statusCode: nil)
            }
            throw APIError(message: "网络连接失败，请检查网络后重试", statusCode: nil)
        }
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
            (data, response) = try await Self.attemptWithRetry {
                try await session.data(for: req)
            }
        } catch let urlError as URLError {
            throw APIError(message: Self.friendlyMessage(for: urlError), statusCode: nil)
        } catch {
            throw APIError(message: "网络连接失败，请检查网络后重试", statusCode: nil)
        }
        return try Self.process(data: data, response: response, sentToken: token)
    }

    /// 共享的"HTTP 响应 → 解码结果"处理：从 dataTask / uploadTask 拿到 (Data, URLResponse)
    /// 后都走这里，集中状态码 / 401 / JSON 解码的逻辑。
    private static func process<T: Decodable>(data: Data, response: URLResponse, sentToken: String?) throws -> T {
        guard let http = response as? HTTPURLResponse else {
            throw APIError(message: "服务器响应异常", statusCode: nil)
        }

        guard (200..<300).contains(http.statusCode) else {
            let error = APIError(message: detail(from: data) ?? "请求失败（\(http.statusCode)）",
                                  statusCode: http.statusCode)
            // 只有「带着 token 的请求」被判定未认证才算会话过期——登录/注册本身返回
            // 401（账号密码错）不该触发登出，那时候根本没带 token。
            if error.isUnauthorized && sentToken != nil {
                NotificationCenter.default.post(name: .apiUnauthorized, object: nil)
            }
            throw error
        }

        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw APIError(message: "数据解析失败，请稍后再试", statusCode: http.statusCode)
        }
    }

    /// URLError → 中文用户提示。`networkConnectionLost (-1005)` 是拍照识别最常
    /// 踩到的——之前一刀切提示"网络连接失败"太模糊，用户不知道是手机断网了还
    /// 是别的，这里按错误码细分，让错误信息更可执行。
    private static func friendlyMessage(for error: URLError) -> String {
        switch error.code {
        case .networkConnectionLost, .notConnectedToInternet:
            return "网络连接已中断，请检查 Wi-Fi 或移动网络后重试"
        case .timedOut:
            return "识别超时，请稍后再试（拍照时网络可能不稳定）"
        case .cannotFindHost, .cannotConnectToHost:
            return "无法连接到服务器，请检查网络"
        case .secureConnectionFailed, .serverCertificateUntrusted:
            return "安全连接失败，请稍后再试"
        default:
            return "网络连接失败，请检查网络后重试"
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
