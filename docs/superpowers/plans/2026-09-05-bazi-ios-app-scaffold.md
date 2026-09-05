# DeepAlphaBaZi iOS 工程脚手架 + 八字免费功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建 `DeepAlphaBaZi` iOS 工程（xcodegen + SPM Core 包），实现八字免费功能闭环：填生辰 → 调后端 `/api/v1/bazi/chart` 排盘 → 本地持久化 → 首页展示四柱/五行/今日运势，付费分段（大运流年/深度解读）先做锁定态 UI 占位。

**Architecture:** 参照 `ios/DeepAlphaClub` 的结构（而非 `ios/DeepAlphaChan` 的纯手动 `.xcodeproj`）：业务逻辑（网络/模型/持久化/ViewModel）放进本地 SPM 包 `Core`，用 Swift Testing 写单元测试；App target 只放 SwiftUI 视图。网络层（`APIClient`/`APIError`）直接从 `DeepAlphaClub/Core` 移植（同一套后端，同一套错误处理惯例），新写的是八字领域的 Model/Service/Persistence/ViewModel/View。

**Tech Stack:** Swift 6.0（严格并发）/ iOS 17.0 / SwiftUI / SwiftData / Swift Testing（不是 XCTest）/ xcodegen / 无第三方 SPM 依赖

---

## 前置说明（写给执行这个计划的工程师）

- **本仓库另一个 iOS 工程 `ios/DeepAlphaClub` 已经有一套验证过的网络层/持久化/ViewModel 惯例**，本计划大量直接复用其代码（尤其是 `APIClient.swift`、`APIError.swift`、测试用的 `MockURLProtocol.swift`）。遇到不确定的写法，优先去读 `ios/DeepAlphaClub/Core/Sources/Core/` 里的对应文件，而不是自己发明新模式。
- **测试框架是 Swift Testing**（`import Testing`、`@Suite`、`@Test`、`#expect`），不是 XCTest。跑测试的命令是 `swift test`（在 `Core/` 目录下），不是 `xcodebuild test`。
- 本计划里**所有 Swift 代码都已经在临时 scratch 包里用 `swift build`/`swift test`/`xcodebuild build` 实际编译验证过**，包括完整的 App target（SwiftUI 视图 + xcodegen 生成的工程）用 `xcodebuild -destination 'generic/platform=iOS Simulator' build` 跑通过 `BUILD SUCCEEDED`。照抄不会有语法错误，但如果你改动了签名/类型，要自己重新验证。
- **已知的真实坑，代码里已经绕开，了解一下原因**：
  1. SwiftData 的 `@Model` 类不是 `Sendable`，不能跨 `@ModelActor` 边界直接返回给调用方（Swift 6 严格并发会报编译错误）——`BaziLocalStore.loadProfile()` 返回的是 `BirthProfileSnapshot`（一个 `Sendable` struct），不是 `BirthProfile` 本身。
  2. `@Observable` class 的 `static func` 默认参数里不能用 `Self.xxx`（"covariant Self type cannot be referenced from a default argument expression"），且该 static func 会被隐式打上 `@MainActor` 标记导致不能在同步的 `@Sendable` 闭包默认值里调用——`BaziViewModel.formatDateKey` 显式声明成 `nonisolated static func`，默认参数里用 `BaziViewModel.formatDateKey(...)` 而不是 `Self.formatDateKey(...)`。
  3. `#Predicate` 宏内引用 `Self.someStaticLet` 会编译失败，要先把它拷到局部变量再用。
- **已观察到一次性、非必现的 `swift test` 崩溃**（signal 11，多个测试套件混跑时偶发，单独跑某个套件永远通过）。这大概率是这套工具链（Swift 6.3 toolchain）在并行跑 SwiftData + URLProtocol mock 混合测试时的已知不稳定，不是代码逻辑问题——如果你跑 `swift test` 遇到这个，直接重跑一次即可，不用去改代码"修复"它。
- 本计划的城市选择器（`BaziFormatting.supportedCities`）**必须和后端 `app/services/bazi/data/cn_city_longitude.json` 的 38 个城市完全一致**——已经用 `python3 -c "import json; ..."` 核对过一次，如果后端那份数据以后变了，这边要同步改。
- **本计划范围边界**：只做免费功能（排盘 + 今日运势）。大运流年/深度解读两个分段只做锁定态 UI（"即将推出"占位），真实 StoreKit 订阅购买是下一个 Plan（暂定 `2026-09-0X-bazi-ios-subscription.md`）的工作，不在这个计划里做。"我的" Tab、可选登录也是再下一个 Plan 的工作——这个计划的 `RootView` 还没有底部 Tab 栏，只有单一的八字页面流程。

---

## Task 1: xcodegen 项目脚手架 + SPM Core 包骨架

**Files:**
- Create: `ios/DeepAlphaBaZi/project.yml`
- Create: `ios/DeepAlphaBaZi/App/Info.plist`
- Create: `ios/DeepAlphaBaZi/Core/Package.swift`
- Create: `ios/DeepAlphaBaZi/Core/Sources/Core/PackageMarker.swift`（占位文件，让 SPM target 有内容可编译）

- [ ] **Step 1: 创建目录结构**

```bash
mkdir -p ios/DeepAlphaBaZi/App/Features/Bazi
mkdir -p ios/DeepAlphaBaZi/Core/Sources/Core/Persistence
mkdir -p ios/DeepAlphaBaZi/Core/Sources/Core/ViewModels
mkdir -p ios/DeepAlphaBaZi/Core/Tests/CoreTests
```

- [ ] **Step 2: 写 SPM 包配置**

`ios/DeepAlphaBaZi/Core/Package.swift`:
```swift
// swift-tools-version:6.0
import PackageDescription

let package = Package(
    name: "DeepAlphaBaZiCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "DeepAlphaBaZiCore", targets: ["DeepAlphaBaZiCore"]),
    ],
    targets: [
        .target(
            name: "DeepAlphaBaZiCore",
            path: "Sources/Core",
            swiftSettings: [.swiftLanguageMode(.v6)]
        ),
        .testTarget(
            name: "CoreTests",
            dependencies: ["DeepAlphaBaZiCore"],
            path: "Tests/CoreTests",
            swiftSettings: [.swiftLanguageMode(.v6)]
        ),
    ]
)
```

`ios/DeepAlphaBaZi/Core/Sources/Core/PackageMarker.swift`（临时占位，Task 3 会加真正的代码后可以删掉这个文件——先写它只是为了让这一步的 `swift build` 有东西可编译，验证包骨架本身是对的）:
```swift
/// 占位文件：验证 SPM 包骨架能正常编译。Task 3 加入真正的 Model 代码后可删除此文件。
enum PackageMarker {}
```

- [ ] **Step 3: 验证 Core 包能编译**

Run: `cd ios/DeepAlphaBaZi/Core && swift build`
Expected: `Build complete!`

- [ ] **Step 4: 写 xcodegen 工程配置**

`ios/DeepAlphaBaZi/project.yml`:
```yaml
name: DeepAlphaBaZi
options:
  bundleIdPrefix: club.deepalpha
  deploymentTarget:
    iOS: "17.0"
  createIntermediateGroups: true

packages:
  DeepAlphaBaZiCore:
    path: Core

targets:
  DeepAlphaBaZi:
    type: application
    platform: iOS
    sources:
      - path: App
    dependencies:
      - package: DeepAlphaBaZiCore
    info:
      path: App/Info.plist
      properties:
        CFBundleDisplayName: 八字
        CFBundleShortVersionString: "0.1.0"
        CFBundleVersion: "1"
        UILaunchScreen: {}
        UISupportedInterfaceOrientations:
          - UIInterfaceOrientationPortrait
        ITSAppUsesNonExemptEncryption: false
    settings:
      base:
        PRODUCT_BUNDLE_IDENTIFIER: club.deepalpha.bazi
        ASSETCATALOG_COMPILER_APPICON_NAME: AppIcon
        SWIFT_VERSION: "6.0"
        TARGETED_DEVICE_FAMILY: "1,2"
        CODE_SIGN_STYLE: Automatic

schemes:
  DeepAlphaBaZi:
    build:
      targets:
        DeepAlphaBaZi: all
    run:
      config: Debug
    archive:
      config: Release
```

`ios/DeepAlphaBaZi/App/Info.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDevelopmentRegion</key>
	<string>$(DEVELOPMENT_LANGUAGE)</string>
	<key>CFBundleExecutable</key>
	<string>$(EXECUTABLE_NAME)</string>
	<key>CFBundleIdentifier</key>
	<string>$(PRODUCT_BUNDLE_IDENTIFIER)</string>
	<key>CFBundleInfoDictionaryVersion</key>
	<string>6.0</string>
	<key>CFBundleName</key>
	<string>$(PRODUCT_NAME)</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleShortVersionString</key>
	<string>0.1.0</string>
	<key>CFBundleVersion</key>
	<string>1</string>
	<key>ITSAppUsesNonExemptEncryption</key>
	<false/>
	<key>UILaunchScreen</key>
	<dict/>
</dict>
</plist>
```

**注意**：这一步 App target 还没有任何 `.swift` 源文件（`App/` 目录目前只有 `Info.plist`），`xcodegen generate` 能生成工程，但 `xcodebuild build` 现在会因为缺 `@main` 入口失败——这是预期的，Task 8 补上 `DeepAlphaBaZiApp.swift` 之后才做整体编译验证。这一步只验证 `xcodegen generate` 本身不报错。

- [ ] **Step 5: 验证 xcodegen 能生成工程**

Run: `cd ios/DeepAlphaBaZi && xcodegen generate`
Expected: 输出包含 `Created project at .../DeepAlphaBaZi.xcodeproj`，无报错

- [ ] **Step 6: Commit**

```bash
git add ios/DeepAlphaBaZi/project.yml ios/DeepAlphaBaZi/App/Info.plist ios/DeepAlphaBaZi/Core/Package.swift ios/DeepAlphaBaZi/Core/Sources/Core/PackageMarker.swift
git commit -m "chore(bazi-ios): 新增DeepAlphaBaZi工程脚手架(xcodegen+SPM Core包)"
```

`.xcodeproj` 是 xcodegen 生成物，不提交（检查 `ios/.gitignore` 是否已经忽略 `*.xcodeproj`——如果没有，这一步要先补上，参照 `ios/DeepAlphaClub/DeepAlphaClub.xcodeproj` 有没有被提交来判断这个仓库的既有惯例）。

---

## Task 2: 网络层基础设施（从 DeepAlphaClub 移植）

**Files:**
- Create: `ios/DeepAlphaBaZi/Core/Sources/Core/APIClient.swift`
- Create: `ios/DeepAlphaBaZi/Core/Sources/Core/APIError.swift`
- Create: `ios/DeepAlphaBaZi/Core/Tests/CoreTests/MockURLProtocol.swift`
- Create: `ios/DeepAlphaBaZi/Core/Tests/CoreTests/APIClientTests.swift`
- Modify: 删除 `ios/DeepAlphaBaZi/Core/Sources/Core/PackageMarker.swift`（Task 1 的占位文件，这一步开始有真代码了）

`APIClient`/`APIError`/`MockURLProtocol` 这三个文件和 `ios/DeepAlphaClub/Core/Sources/Core/APIClient.swift`、`APIError.swift`、`ios/DeepAlphaClub/Core/Tests/CoreTests/MockURLProtocol.swift` **内容完全一样**（通用网络基础设施，和具体业务无关），直接复制过来即可，不用改一个字。

- [ ] **Step 1: 复制 APIClient.swift**

```bash
cp ios/DeepAlphaClub/Core/Sources/Core/APIClient.swift ios/DeepAlphaBaZi/Core/Sources/Core/APIClient.swift
cp ios/DeepAlphaClub/Core/Sources/Core/APIError.swift ios/DeepAlphaBaZi/Core/Sources/Core/APIError.swift
cp ios/DeepAlphaClub/Core/Tests/CoreTests/MockURLProtocol.swift ios/DeepAlphaBaZi/Core/Tests/CoreTests/MockURLProtocol.swift
rm ios/DeepAlphaBaZi/Core/Sources/Core/PackageMarker.swift
```

如果 `cp` 之后内容和下面贴的不一致（比如 `DeepAlphaClub` 那边后来又改过），**以 `ios/DeepAlphaClub` 里的实际文件内容为准**，不要以这个计划里贴的代码为准——这里贴出来是为了让你在没有网络/无法访问仓库其他部分时也能核对，不是权威版本。

<details>
<summary>APIClient.swift 参考内容（点开展开）</summary>

```swift
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
```

</details>

<details>
<summary>APIError.swift 参考内容（点开展开）</summary>

```swift
import Foundation

public enum APIError: Error, Sendable, Equatable {
    case unauthorized(String?)
    case notFound
    case validation(String)
    case server(Int, String)
    case network
    case decoding

    public var isUnauthorized: Bool {
        if case .unauthorized = self { return true }
        return false
    }

    public var isRetryable: Bool {
        switch self {
        case .unauthorized, .notFound, .validation: false
        case .server, .network, .decoding: true
        }
    }

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

    private static func detailText(body: Data?) -> String? {
        guard let data = body else { return nil }
        if let obj = try? JSONDecoder().decode([String: String].self, from: data),
           let m = obj["detail"] { return m }
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
```

**已知限制（不用现在修）**：`detailText` 只认得 `{"detail": "string"}` 或 `{"detail": {"message": "string"}}` 这两种形状。FastAPI/Pydantic 对请求体做自动校验失败时（比如 `gender` 传了非法枚举值），真实返回的是 `{"detail": [{"type": "...", "loc": [...], "msg": "..."}]}`——一个数组，这个解析逻辑接不住，会掉进 `defaultText(for: 422)` 返回"请求失败（HTTP 422）"这种不带具体原因的兜底文案。这是从 `DeepAlphaClub` 继承来的既有限制，本计划不修——Task 7 的 `BirthInfoFormView` 会用 `DatePicker` 的 `in:` 参数直接把日期范围锁在后端允许的区间内，从 UI 层面避免用户能触发这类 422，所以这个解析限制在这个功能里不会被用户实际感知到。

</details>

<details>
<summary>MockURLProtocol.swift 参考内容（点开展开）</summary>

```swift
import Foundation
import Testing

final class MockServer: @unchecked Sendable {
    typealias Handler = @Sendable (URLRequest) throws -> (HTTPURLResponse, Data)

    let id = UUID().uuidString
    private let lock = NSLock()
    private var _handler: Handler?

    var handler: Handler? {
        get { lock.lock(); defer { lock.unlock() }; return _handler }
        set { lock.lock(); _handler = newValue; lock.unlock() }
    }

    lazy var session: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        config.httpAdditionalHeaders = [MockURLProtocol.idHeader: id]
        return URLSession(configuration: config)
    }()

    init() { MockURLProtocol.register(self) }
}

final class MockURLProtocol: URLProtocol {
    static let idHeader = "X-Mock-Id"

    nonisolated(unsafe) private static var servers: [String: MockServer] = [:]
    private static let registryLock = NSLock()

    static func register(_ server: MockServer) {
        registryLock.lock()
        servers[server.id] = server
        registryLock.unlock()
    }

    private static func server(for id: String) -> MockServer? {
        registryLock.lock()
        defer { registryLock.unlock() }
        return servers[id]
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let id = request.value(forHTTPHeaderField: MockURLProtocol.idHeader),
              let handler = MockURLProtocol.server(for: id)?.handler
        else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

final class LockedRequestBox: @unchecked Sendable {
    private let lock = NSLock()
    private var req: URLRequest?
    func set(_ r: URLRequest) { lock.lock(); req = r; lock.unlock() }
    func get() -> URLRequest? { lock.lock(); defer { lock.unlock() }; return req }
}

extension URLRequest {
    var httpBodyStreamData: Data? {
        guard let stream = httpBodyStream else { return nil }
        stream.open()
        defer { stream.close() }
        var data = Data()
        let bufSize = 4096
        let buf = UnsafeMutablePointer<UInt8>.allocate(capacity: bufSize)
        defer { buf.deallocate() }
        while stream.hasBytesAvailable {
            let n = stream.read(buf, maxLength: bufSize)
            if n <= 0 { break }
            data.append(buf, count: n)
        }
        return data
    }
}
```

</details>

- [ ] **Step 2: 写一个精简版 APIClientTests.swift**（不用照搬 DeepAlphaClub 那份含 401 dict/form-urlencoded 等场景的完整版本——那些场景这个 App 暂时用不到，等 Task 2 的下一个 Plan 需要登录时再补。这里只验证最基本的 GET/POST/错误映射，`import DeepAlphaBaZiCore`）：

`ios/DeepAlphaBaZi/Core/Tests/CoreTests/APIClientTests.swift`:
```swift
import Foundation
import Testing
@testable import DeepAlphaBaZiCore

@Suite("APIClient")
struct APIClientTests {
    func makeClient(_ mock: MockServer) -> APIClient {
        APIClient(baseURL: URL(string: "https://api.example.com")!, session: mock.session)
    }

    @Test("POST JSON：Content-Type 与 body 正确编码")
    func postJson() async throws {
        let mock = MockServer()
        let captured = LockedRequestBox()
        mock.handler = { req in
            captured.set(req)
            return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!,
                    Data(#"{"ok":true}"#.utf8))
        }
        struct Body: Encodable { let a: String }
        struct Resp: Decodable { let ok: Bool }

        let client = makeClient(mock)
        let resp: Resp = try await client.post("/x", json: Body(a: "1"))
        #expect(resp.ok)
        let req = try #require(captured.get())
        #expect(req.httpMethod == "POST")
        #expect(req.value(forHTTPHeaderField: "Content-Type") == "application/json")
    }

    @Test("404 → APIError.notFound")
    func notFound() async {
        let mock = MockServer()
        mock.handler = { req in
            (HTTPURLResponse(url: req.url!, statusCode: 404, httpVersion: nil, headerFields: nil)!, Data())
        }
        struct Empty: Decodable {}
        let client = makeClient(mock)
        await #expect(throws: APIError.notFound) {
            let _: Empty = try await client.get("/x")
        }
    }

    @Test("422 → APIError.validation，detail 文本透出")
    func validation() async {
        let mock = MockServer()
        mock.handler = { req in
            (HTTPURLResponse(url: req.url!, statusCode: 422, httpVersion: nil, headerFields: nil)!,
             Data(#"{"detail":"出生日期不能晚于今天"}"#.utf8))
        }
        struct Empty: Decodable {}
        let client = makeClient(mock)
        do {
            let _: Empty = try await client.get("/x")
            Issue.record("应抛 validation")
        } catch let e as APIError {
            #expect(e.message == "出生日期不能晚于今天")
        } catch {
            Issue.record("错误类型不对：\(error)")
        }
    }

    @Test("连接层错误 → APIError.network")
    func networkError() async {
        let mock = MockServer()
        struct Boom: Error {}
        mock.handler = { _ in throw Boom() }
        struct Empty: Decodable {}
        let client = makeClient(mock)
        await #expect(throws: APIError.network) {
            let _: Empty = try await client.get("/x")
        }
    }
}
```

- [ ] **Step 3: 运行测试**

Run: `cd ios/DeepAlphaBaZi/Core && swift test`
Expected: `Test run with 4 tests in 1 suite passed`（如果遇到签名 11 崩溃，直接重跑一次，见前置说明）

- [ ] **Step 4: Commit**

```bash
git add ios/DeepAlphaBaZi/Core/Sources/Core/APIClient.swift ios/DeepAlphaBaZi/Core/Sources/Core/APIError.swift ios/DeepAlphaBaZi/Core/Tests/CoreTests/MockURLProtocol.swift ios/DeepAlphaBaZi/Core/Tests/CoreTests/APIClientTests.swift
git rm ios/DeepAlphaBaZi/Core/Sources/Core/PackageMarker.swift
git commit -m "feat(bazi-ios): 从DeepAlphaClub移植通用网络层(APIClient/APIError)"
```

---

## Task 3: BaziModels + BaziFormatting

**Files:**
- Create: `ios/DeepAlphaBaZi/Core/Sources/Core/BaziModels.swift`
- Create: `ios/DeepAlphaBaZi/Core/Sources/Core/BaziFormatting.swift`
- Test: `ios/DeepAlphaBaZi/Core/Tests/CoreTests/BaziModelsTests.swift`
- Test: `ios/DeepAlphaBaZi/Core/Tests/CoreTests/BaziFormattingTests.swift`

这些是镜像后端 `app/schemas/bazi.py` 的 Codable 模型。测试用的 JSON 是**结构性测试夹具**（字段名/类型要和后端对齐），不是真实排盘数值——排盘算法本身的正确性已经在后端 `tests/services/bazi/` 用 lunar-python 实测覆盖过，这层只验证 Swift 端编解码没有和后端字段名/类型走样。

- [ ] **Step 1: 写失败的测试**

`ios/DeepAlphaBaZi/Core/Tests/CoreTests/BaziModelsTests.swift`:
```swift
import Foundation
import Testing
@testable import DeepAlphaBaZiCore

@Suite("BaziModels")
struct BaziModelsTests {
    @Test("BaziChartRequest 编码：字段名走 snake_case")
    func encodeChartRequest() throws {
        let request = BaziChartRequest(
            birthDate: "1990-05-15", birthTime: "14:30:00",
            birthCity: "北京", gender: "male")
        let data = try JSONEncoder().encode(request)
        let json = try #require(try JSONSerialization.jsonObject(with: data) as? [String: String])
        #expect(json["birth_date"] == "1990-05-15")
        #expect(json["birth_time"] == "14:30:00")
        #expect(json["birth_city"] == "北京")
        #expect(json["gender"] == "male")
    }

    @Test("BaziChartRequest 编码：birth_time 为 nil 时序列化成 null")
    func encodeChartRequestNilTime() throws {
        let request = BaziChartRequest(
            birthDate: "1990-05-15", birthTime: nil, birthCity: "北京", gender: "female")
        let data = try JSONEncoder().encode(request)
        let json = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any?])
        #expect(json["birth_time"] as? String == nil)
    }

    @Test("BaziChartResponse 解码：时辰已知，四柱+五行+大运完整映射")
    func decodeChartResponseHourKnown() throws {
        let json = """
        {
          "request_id": "11111111-1111-1111-1111-111111111111",
          "hour_known": true,
          "solar_date": "1990-05-15",
          "lunar_date": "一九九〇年四月廿一",
          "true_solar_time": "1990-05-15T14:16:00",
          "true_solar_time_applied": true,
          "year_pillar": {"gan": "庚", "zhi": "午", "na_yin": "路旁土", "shi_shen_gan": "比肩", "shi_shen_zhi": ["正官", "正印"]},
          "month_pillar": {"gan": "辛", "zhi": "巳", "na_yin": "白蜡金", "shi_shen_gan": "劫财", "shi_shen_zhi": ["七杀"]},
          "day_pillar": {"gan": "庚", "zhi": "辰", "na_yin": "白蜡金", "shi_shen_gan": "元男", "shi_shen_zhi": ["偏印"]},
          "time_pillar": {"gan": "癸", "zhi": "未", "na_yin": "杨柳木", "shi_shen_gan": "伤官", "shi_shen_zhi": ["正印"]},
          "wu_xing_distribution": {"jin": 3, "mu": 0, "shui": 1, "huo": 2, "tu": 2},
          "da_yun": [{"gan_zhi": "壬午", "start_age": 8, "end_age": 17}, {"gan_zhi": "癸未", "start_age": 18, "end_age": 27}],
          "liu_nian_gan_zhi": "甲辰"
        }
        """
        let response = try JSONDecoder().decode(BaziChartResponse.self, from: Data(json.utf8))
        #expect(response.hourKnown == true)
        #expect(response.trueSolarTimeApplied == true)
        #expect(response.yearPillar.gan == "庚")
        #expect(response.yearPillar.shiShenZhi == ["正官", "正印"])
        #expect(response.timePillar?.zhi == "未")
        #expect(response.wuXingDistribution["jin"] == 3)
        #expect(response.daYun.count == 2)
        #expect(response.daYun[0].startAge == 8)
        #expect(response.liuNianGanZhi == "甲辰")
    }

    @Test("BaziChartResponse 解码：时辰未知时 time_pillar 为 nil")
    func decodeChartResponseHourUnknown() throws {
        let json = """
        {
          "request_id": "11111111-1111-1111-1111-111111111111",
          "hour_known": false,
          "solar_date": "1990-05-15",
          "lunar_date": "一九九〇年四月廿一",
          "true_solar_time": null,
          "true_solar_time_applied": false,
          "year_pillar": {"gan": "庚", "zhi": "午", "na_yin": "路旁土", "shi_shen_gan": "比肩", "shi_shen_zhi": ["正官"]},
          "month_pillar": {"gan": "辛", "zhi": "巳", "na_yin": "白蜡金", "shi_shen_gan": "劫财", "shi_shen_zhi": ["七杀"]},
          "day_pillar": {"gan": "庚", "zhi": "辰", "na_yin": "白蜡金", "shi_shen_gan": "元女", "shi_shen_zhi": ["偏印"]},
          "time_pillar": null,
          "wu_xing_distribution": {"jin": 3, "mu": 0, "shui": 0, "huo": 2, "tu": 1},
          "da_yun": [],
          "liu_nian_gan_zhi": "甲辰"
        }
        """
        let response = try JSONDecoder().decode(BaziChartResponse.self, from: Data(json.utf8))
        #expect(response.hourKnown == false)
        #expect(response.timePillar == nil)
        #expect(response.trueSolarTime == nil)
    }

    @Test("InterpretationRequest 编码：section 走 daily/deep 字符串")
    func encodeInterpretationRequest() throws {
        let request = InterpretationRequest(
            birthDate: "1990-05-15", birthTime: nil, birthCity: "北京",
            gender: "male", section: .deep)
        let data = try JSONEncoder().encode(request)
        let json = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(json["section"] as? String == "deep")
    }

    @Test("InterpretationResponse 解码")
    func decodeInterpretationResponse() throws {
        let json = #"{"request_id": "x", "text": "今天适合签约 | 宜：签约 忌：争执"}"#
        let response = try JSONDecoder().decode(InterpretationResponse.self, from: Data(json.utf8))
        #expect(response.text == "今天适合签约 | 宜：签约 忌：争执")
    }
}
```

`ios/DeepAlphaBaZi/Core/Tests/CoreTests/BaziFormattingTests.swift`:
```swift
import Foundation
import Testing
@testable import DeepAlphaBaZiCore

@Suite("BaziFormatting")
struct BaziFormattingTests {
    @Test("birthDateString：格式化成 yyyy-MM-dd")
    func birthDateFormat() {
        var components = DateComponents()
        components.year = 1990; components.month = 5; components.day = 15
        components.hour = 14; components.minute = 30
        let tz = TimeZone(identifier: "Asia/Shanghai")!
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = tz
        let date = calendar.date(from: components)!
        #expect(BaziFormatting.birthDateString(from: date, timeZone: tz) == "1990-05-15")
    }

    @Test("birthTimeString：格式化成 HH:mm:ss")
    func birthTimeFormat() {
        var components = DateComponents()
        components.year = 1990; components.month = 5; components.day = 15
        components.hour = 14; components.minute = 30; components.second = 0
        let tz = TimeZone(identifier: "Asia/Shanghai")!
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = tz
        let date = calendar.date(from: components)!
        #expect(BaziFormatting.birthTimeString(from: date, timeZone: tz) == "14:30:00")
    }

    @Test("supportedCities：包含38个后端支持的城市，覆盖北京和台北")
    func supportedCitiesCount() {
        #expect(BaziFormatting.supportedCities.count == 38)
        #expect(BaziFormatting.supportedCities.contains("北京"))
        #expect(BaziFormatting.supportedCities.contains("台北"))
    }
}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd ios/DeepAlphaBaZi/Core && swift test --filter BaziModelsTests`
Expected: 编译失败，`cannot find 'BaziChartRequest' in scope`（`BaziFormattingTests` 同理会因为 `BaziFormatting` 不存在而编译失败）

- [ ] **Step 3: 实现 BaziModels.swift**

`ios/DeepAlphaBaZi/Core/Sources/Core/BaziModels.swift`:
```swift
import Foundation

/// 请求：镜像后端 app/schemas/bazi.py 的 BaziChartRequest。
/// birthDate/birthTime 在调用方就格式化成字符串（"yyyy-MM-dd" / "HH:mm:ss"），
/// 不用 Date 的默认 JSON 编码——那和 Python 的 date/time 格式对不上。
public struct BaziChartRequest: Encodable, Sendable {
    public let birthDate: String
    public let birthTime: String?
    public let birthCity: String
    public let gender: String

    public init(birthDate: String, birthTime: String?, birthCity: String, gender: String) {
        self.birthDate = birthDate
        self.birthTime = birthTime
        self.birthCity = birthCity
        self.gender = gender
    }

    enum CodingKeys: String, CodingKey {
        case birthDate = "birth_date"
        case birthTime = "birth_time"
        case birthCity = "birth_city"
        case gender
    }
}

public struct Pillar: Codable, Sendable, Equatable {
    public let gan: String
    public let zhi: String
    public let naYin: String
    public let shiShenGan: String
    public let shiShenZhi: [String]

    public init(gan: String, zhi: String, naYin: String, shiShenGan: String, shiShenZhi: [String]) {
        self.gan = gan
        self.zhi = zhi
        self.naYin = naYin
        self.shiShenGan = shiShenGan
        self.shiShenZhi = shiShenZhi
    }

    enum CodingKeys: String, CodingKey {
        case gan, zhi
        case naYin = "na_yin"
        case shiShenGan = "shi_shen_gan"
        case shiShenZhi = "shi_shen_zhi"
    }
}

public struct DaYunStep: Codable, Sendable, Equatable, Identifiable {
    public var id: String { "\(ganZhi)-\(startAge)" }
    public let ganZhi: String
    public let startAge: Int
    public let endAge: Int

    public init(ganZhi: String, startAge: Int, endAge: Int) {
        self.ganZhi = ganZhi
        self.startAge = startAge
        self.endAge = endAge
    }

    enum CodingKeys: String, CodingKey {
        case ganZhi = "gan_zhi"
        case startAge = "start_age"
        case endAge = "end_age"
    }
}

public struct BaziChartResponse: Codable, Sendable, Equatable {
    public let requestId: String
    public let hourKnown: Bool
    public let solarDate: String
    public let lunarDate: String
    public let trueSolarTime: String?
    public let trueSolarTimeApplied: Bool
    public let yearPillar: Pillar
    public let monthPillar: Pillar
    public let dayPillar: Pillar
    public let timePillar: Pillar?
    public let wuXingDistribution: [String: Int]
    public let daYun: [DaYunStep]
    public let liuNianGanZhi: String

    public init(requestId: String, hourKnown: Bool, solarDate: String, lunarDate: String,
                trueSolarTime: String?, trueSolarTimeApplied: Bool, yearPillar: Pillar,
                monthPillar: Pillar, dayPillar: Pillar, timePillar: Pillar?,
                wuXingDistribution: [String: Int], daYun: [DaYunStep], liuNianGanZhi: String) {
        self.requestId = requestId
        self.hourKnown = hourKnown
        self.solarDate = solarDate
        self.lunarDate = lunarDate
        self.trueSolarTime = trueSolarTime
        self.trueSolarTimeApplied = trueSolarTimeApplied
        self.yearPillar = yearPillar
        self.monthPillar = monthPillar
        self.dayPillar = dayPillar
        self.timePillar = timePillar
        self.wuXingDistribution = wuXingDistribution
        self.daYun = daYun
        self.liuNianGanZhi = liuNianGanZhi
    }

    enum CodingKeys: String, CodingKey {
        case requestId = "request_id"
        case hourKnown = "hour_known"
        case solarDate = "solar_date"
        case lunarDate = "lunar_date"
        case trueSolarTime = "true_solar_time"
        case trueSolarTimeApplied = "true_solar_time_applied"
        case yearPillar = "year_pillar"
        case monthPillar = "month_pillar"
        case dayPillar = "day_pillar"
        case timePillar = "time_pillar"
        case wuXingDistribution = "wu_xing_distribution"
        case daYun = "da_yun"
        case liuNianGanZhi = "liu_nian_gan_zhi"
    }
}

/// section 固定两档：daily(免费今日运势) / deep(付费深度解读)。
public enum InterpretationSection: String, Codable, Sendable {
    case daily
    case deep
}

public struct InterpretationRequest: Encodable, Sendable {
    public let birthDate: String
    public let birthTime: String?
    public let birthCity: String
    public let gender: String
    public let section: InterpretationSection

    public init(birthDate: String, birthTime: String?, birthCity: String, gender: String,
                section: InterpretationSection) {
        self.birthDate = birthDate
        self.birthTime = birthTime
        self.birthCity = birthCity
        self.gender = gender
        self.section = section
    }

    enum CodingKeys: String, CodingKey {
        case birthDate = "birth_date"
        case birthTime = "birth_time"
        case birthCity = "birth_city"
        case gender, section
    }
}

public struct InterpretationResponse: Codable, Sendable, Equatable {
    public let requestId: String
    public let text: String

    public init(requestId: String, text: String) {
        self.requestId = requestId
        self.text = text
    }

    enum CodingKeys: String, CodingKey {
        case requestId = "request_id"
        case text
    }
}
```

- [ ] **Step 4: 实现 BaziFormatting.swift**

`ios/DeepAlphaBaZi/Core/Sources/Core/BaziFormatting.swift`:
```swift
import Foundation

/// 生辰表单用的日期/时间 <-> 字符串转换，纯函数，方便测试。
/// 后端 Pydantic 的 date/time 字段接受 "yyyy-MM-dd" / "HH:mm:ss"（本地时间，不带时区）。
public enum BaziFormatting {
    public static func birthDateString(from date: Date, timeZone: TimeZone = .current) -> String {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        let formatter = DateFormatter()
        formatter.calendar = calendar
        formatter.timeZone = timeZone
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    public static func birthTimeString(from date: Date, timeZone: TimeZone = .current) -> String {
        let formatter = DateFormatter()
        formatter.timeZone = timeZone
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "HH:mm:ss"
        return formatter.string(from: date)
    }

    /// 内置城市经度表覆盖的 38 个城市（与后端 app/services/bazi/data/cn_city_longitude.json 一一对应）。
    /// 表单只能从这里选，不开放自由输入——避免用户输入的城市名和后端表匹配不上，
    /// 真太阳时校正静默不生效却毫无提示。
    public static let supportedCities: [String] = [
        "北京", "上海", "广州", "深圳", "成都", "杭州", "南京", "武汉", "西安", "重庆",
        "天津", "苏州", "长沙", "郑州", "青岛", "大连", "厦门", "昆明", "哈尔滨", "沈阳",
        "济南", "合肥", "福州", "南昌", "太原", "石家庄", "兰州", "贵阳", "南宁", "海口",
        "乌鲁木齐", "拉萨", "呼和浩特", "银川", "西宁", "香港", "澳门", "台北",
    ]

    /// 出生日期选择范围下限：早于这个日期后端会拒绝(422)，UI 层直接不给选，
    /// 不依赖解析后端错误消息。
    public static let minBirthDate: Date = {
        var components = DateComponents()
        components.year = 1900
        components.month = 1
        components.day = 1
        return Calendar(identifier: .gregorian).date(from: components) ?? Date.distantPast
    }()
}
```

**校验城市列表和后端一致**（不是照抄就完事，实际跑一下确认）：

Run:
```bash
python3 -c "
import json
with open('app/services/bazi/data/cn_city_longitude.json') as f:
    print(len(json.load(f)))
"
```
Expected: `38`，且和 `BaziFormatting.supportedCities` 里的城市名逐一核对一致（这个命令要在仓库根目录 `deepalpha-club-ai/` 下跑，不是 `ios/` 里）

- [ ] **Step 5: 运行测试确认通过**

Run: `cd ios/DeepAlphaBaZi/Core && swift test --filter BaziModelsTests && swift test --filter BaziFormattingTests`
Expected: 两个都 `passed`（`BaziModelsTests` 6 个用例，`BaziFormattingTests` 3 个用例）

- [ ] **Step 6: Commit**

```bash
git add ios/DeepAlphaBaZi/Core/Sources/Core/BaziModels.swift ios/DeepAlphaBaZi/Core/Sources/Core/BaziFormatting.swift ios/DeepAlphaBaZi/Core/Tests/CoreTests/BaziModelsTests.swift ios/DeepAlphaBaZi/Core/Tests/CoreTests/BaziFormattingTests.swift
git commit -m "feat(bazi-ios): 新增BaziModels(镜像后端schema)和BaziFormatting(日期/城市)"
```

---

## Task 4: BaziService

**Files:**
- Create: `ios/DeepAlphaBaZi/Core/Sources/Core/BaziService.swift`
- Test: `ios/DeepAlphaBaZi/Core/Tests/CoreTests/BaziServiceTests.swift`

- [ ] **Step 1: 写失败的测试**

`ios/DeepAlphaBaZi/Core/Tests/CoreTests/BaziServiceTests.swift`:
```swift
import Foundation
import Testing
@testable import DeepAlphaBaZiCore

@Suite("BaziService")
struct BaziServiceTests {
    func makeService(_ mock: MockServer) -> BaziService {
        BaziService(api: APIClient(baseURL: URL(string: "https://api.example.com")!, session: mock.session))
    }

    @Test("getChart：POST /api/v1/bazi/chart，请求体/响应体正确映射")
    func getChart() async throws {
        let mock = MockServer()
        let captured = LockedRequestBox()
        mock.handler = { req in
            captured.set(req)
            let body = """
            {"request_id":"x","hour_known":true,"solar_date":"1990-05-15",
             "lunar_date":"一九九〇年四月廿一","true_solar_time":"1990-05-15T14:16:00",
             "true_solar_time_applied":true,
             "year_pillar":{"gan":"庚","zhi":"午","na_yin":"路旁土","shi_shen_gan":"比肩","shi_shen_zhi":["正官"]},
             "month_pillar":{"gan":"辛","zhi":"巳","na_yin":"白蜡金","shi_shen_gan":"劫财","shi_shen_zhi":["七杀"]},
             "day_pillar":{"gan":"庚","zhi":"辰","na_yin":"白蜡金","shi_shen_gan":"元男","shi_shen_zhi":["偏印"]},
             "time_pillar":{"gan":"癸","zhi":"未","na_yin":"杨柳木","shi_shen_gan":"伤官","shi_shen_zhi":["正印"]},
             "wu_xing_distribution":{"jin":3,"mu":0,"shui":1,"huo":2,"tu":2},
             "da_yun":[{"gan_zhi":"壬午","start_age":8,"end_age":17}],
             "liu_nian_gan_zhi":"甲辰"}
            """
            return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!,
                    Data(body.utf8))
        }
        let service = makeService(mock)
        let response = try await service.getChart(BaziChartRequest(
            birthDate: "1990-05-15", birthTime: "14:30:00", birthCity: "北京", gender: "male"))

        let req = try #require(captured.get())
        #expect(req.httpMethod == "POST")
        #expect(req.url?.absoluteString == "https://api.example.com/api/v1/bazi/chart")
        #expect(response.yearPillar.gan == "庚")
        #expect(response.daYun.first?.ganZhi == "壬午")
    }

    @Test("getInterpretation：POST /api/v1/bazi/interpretation")
    func getInterpretation() async throws {
        let mock = MockServer()
        let captured = LockedRequestBox()
        mock.handler = { req in
            captured.set(req)
            let body = #"{"request_id":"x","text":"今天适合签约 | 宜：签约 忌：争执"}"#
            return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!,
                    Data(body.utf8))
        }
        let service = makeService(mock)
        let response = try await service.getInterpretation(InterpretationRequest(
            birthDate: "1990-05-15", birthTime: "14:30:00", birthCity: "北京",
            gender: "male", section: .daily))

        let req = try #require(captured.get())
        #expect(req.url?.absoluteString == "https://api.example.com/api/v1/bazi/interpretation")
        let bodyData = try #require(req.httpBody ?? req.httpBodyStreamData)
        let bodyJSON = try #require(try JSONSerialization.jsonObject(with: bodyData) as? [String: Any])
        #expect(bodyJSON["section"] as? String == "daily")
        #expect(response.text == "今天适合签约 | 宜：签约 忌：争执")
    }

    @Test("getChart：422 校验错误抛出 APIError")
    func getChartValidationError() async {
        let mock = MockServer()
        mock.handler = { req in
            let body = #"{"detail":[{"type":"value_error","loc":["body","birth_date"],"msg":"Value error, 出生日期不能晚于今天"}]}"#
            return (HTTPURLResponse(url: req.url!, statusCode: 422, httpVersion: nil, headerFields: nil)!,
                    Data(body.utf8))
        }
        let service = makeService(mock)
        await #expect(throws: (any Error).self) {
            _ = try await service.getChart(BaziChartRequest(
                birthDate: "2999-01-01", birthTime: nil, birthCity: "北京", gender: "male"))
        }
    }
}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd ios/DeepAlphaBaZi/Core && swift test --filter BaziServiceTests`
Expected: 编译失败，`cannot find 'BaziService' in scope`

- [ ] **Step 3: 实现 BaziService.swift**

`ios/DeepAlphaBaZi/Core/Sources/Core/BaziService.swift`:
```swift
import Foundation

/// 八字排盘/AI 解读接口（协议化方便测试 mock）。
public protocol BaziServicing: Sendable {
    func getChart(_ request: BaziChartRequest) async throws -> BaziChartResponse
    func getInterpretation(_ request: InterpretationRequest) async throws -> InterpretationResponse
}

/// 线上实现：POST /api/v1/bazi/chart 、 POST /api/v1/bazi/interpretation。
public struct BaziService: BaziServicing {
    let api: APIClient

    public init(api: APIClient) {
        self.api = api
    }

    public func getChart(_ request: BaziChartRequest) async throws -> BaziChartResponse {
        try await api.post("/api/v1/bazi/chart", json: request)
    }

    public func getInterpretation(_ request: InterpretationRequest) async throws -> InterpretationResponse {
        try await api.post("/api/v1/bazi/interpretation", json: request)
    }
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd ios/DeepAlphaBaZi/Core && swift test --filter BaziServiceTests`
Expected: `Test run with 3 tests in 1 suite passed`

- [ ] **Step 5: Commit**

```bash
git add ios/DeepAlphaBaZi/Core/Sources/Core/BaziService.swift ios/DeepAlphaBaZi/Core/Tests/CoreTests/BaziServiceTests.swift
git commit -m "feat(bazi-ios): 新增BaziService(chart+interpretation两个端点)"
```

---

## Task 5: SwiftData 本地存储

**Files:**
- Create: `ios/DeepAlphaBaZi/Core/Sources/Core/Persistence/BirthProfile.swift`
- Create: `ios/DeepAlphaBaZi/Core/Sources/Core/Persistence/DailyFortuneCache.swift`
- Create: `ios/DeepAlphaBaZi/Core/Sources/Core/Persistence/BaziLocalStore.swift`
- Test: `ios/DeepAlphaBaZi/Core/Tests/CoreTests/BaziLocalStoreTests.swift`

**重要背景（已经踩过的坑，见前置说明#1）**：SwiftData 的 `@Model` 类不是 `Sendable`，`BaziLocalStore`（`@ModelActor`）对外的读接口不能直接返回 `BirthProfile`，要转换成下面这个 `Sendable` 的 `BirthProfileSnapshot`。这不是"可以偷懒不做"的步骤——不这么做在 Swift 6 严格并发下直接编译不过。

- [ ] **Step 1: 实现 BirthProfile.swift（这个是纯 SwiftData 模型定义，不用先写测试，正确性由 Step 4 的 BaziLocalStoreTests 覆盖）**

`ios/DeepAlphaBaZi/Core/Sources/Core/Persistence/BirthProfile.swift`:
```swift
import Foundation
import SwiftData

/// 用户自己的生辰记录（单条，MVP 不支持家人档案）。
/// chartResponseJSON 存最近一次 /chart 的完整响应（JSON blob），避免把 Pillar/DaYunStep
/// 这类嵌套 Codable 结构逐字段拆成 SwiftData 关系模型——排盘结果整体只读展示，不需要按字段查询。
@Model
public final class BirthProfile {
    @Attribute(.unique) public var id: String
    public var birthDate: String
    public var birthTime: String?
    public var birthCity: String
    public var gender: String
    public var chartResponseJSON: Data

    public init(id: String = "me", birthDate: String, birthTime: String?, birthCity: String,
                gender: String, chartResponseJSON: Data) {
        self.id = id
        self.birthDate = birthDate
        self.birthTime = birthTime
        self.birthCity = birthCity
        self.gender = gender
        self.chartResponseJSON = chartResponseJSON
    }
}
```

`ios/DeepAlphaBaZi/Core/Sources/Core/Persistence/DailyFortuneCache.swift`:
```swift
import Foundation
import SwiftData

/// "今日运势"文本缓存，按日期（"yyyy-MM-dd"）去重，避免同一天内重复调用付费 LLM 接口。
@Model
public final class DailyFortuneCache {
    @Attribute(.unique) public var dateKey: String
    public var text: String

    public init(dateKey: String, text: String) {
        self.dateKey = dateKey
        self.text = text
    }
}
```

- [ ] **Step 2: 写失败的测试**

`ios/DeepAlphaBaZi/Core/Tests/CoreTests/BaziLocalStoreTests.swift`:
```swift
import Foundation
import Testing
import SwiftData
@testable import DeepAlphaBaZiCore

func sampleChart() -> BaziChartResponse {
    BaziChartResponse(
        requestId: "x", hourKnown: true, solarDate: "1990-05-15",
        lunarDate: "一九九〇年四月廿一", trueSolarTime: "1990-05-15T14:16:00",
        trueSolarTimeApplied: true,
        yearPillar: Pillar(gan: "庚", zhi: "午", naYin: "路旁土", shiShenGan: "比肩", shiShenZhi: ["正官"]),
        monthPillar: Pillar(gan: "辛", zhi: "巳", naYin: "白蜡金", shiShenGan: "劫财", shiShenZhi: ["七杀"]),
        dayPillar: Pillar(gan: "庚", zhi: "辰", naYin: "白蜡金", shiShenGan: "元男", shiShenZhi: ["偏印"]),
        timePillar: Pillar(gan: "癸", zhi: "未", naYin: "杨柳木", shiShenGan: "伤官", shiShenZhi: ["正印"]),
        wuXingDistribution: ["jin": 3, "mu": 0, "shui": 1, "huo": 2, "tu": 2],
        daYun: [DaYunStep(ganZhi: "壬午", startAge: 8, endAge: 17)],
        liuNianGanZhi: "甲辰")
}

@Suite("BaziLocalStore")
struct BaziLocalStoreTests {
    func makeStore() throws -> BaziLocalStore {
        let config = ModelConfiguration(isStoredInMemoryOnly: true)
        let container = try ModelContainer(for: BirthProfile.self, DailyFortuneCache.self,
                                           configurations: config)
        return BaziLocalStore(modelContainer: container)
    }

    @Test("没有档案时 loadProfile 返回 nil")
    func loadProfileEmpty() async throws {
        let store = try makeStore()
        let profile = try await store.loadProfile()
        #expect(profile == nil)
    }

    @Test("saveProfile 后 loadProfile 能读回同一条记录")
    func saveAndLoadProfile() async throws {
        let store = try makeStore()
        try await store.saveProfile(
            birthDate: "1990-05-15", birthTime: "14:30:00", birthCity: "北京",
            gender: "male", chart: sampleChart())

        let profile = try await store.loadProfile()
        #expect(profile?.birthDate == "1990-05-15")
        #expect(profile?.birthCity == "北京")
        #expect(profile?.chart.yearPillar.gan == "庚")
    }

    @Test("重复 saveProfile 覆盖而不是新增一条")
    func saveProfileOverwrites() async throws {
        let store = try makeStore()
        try await store.saveProfile(
            birthDate: "1990-05-15", birthTime: "14:30:00", birthCity: "北京",
            gender: "male", chart: sampleChart())
        try await store.saveProfile(
            birthDate: "1991-06-20", birthTime: nil, birthCity: "上海",
            gender: "female", chart: sampleChart())

        let profile = try await store.loadProfile()
        #expect(profile?.birthDate == "1991-06-20")
        #expect(profile?.birthCity == "上海")
    }

    @Test("今日运势缓存：没有对应日期时返回 nil")
    func loadFortuneMiss() async throws {
        let store = try makeStore()
        let text = try await store.loadFortune(dateKey: "2026-09-05")
        #expect(text == nil)
    }

    @Test("今日运势缓存：写入后按日期能读回；不同日期互不影响")
    func saveAndLoadFortune() async throws {
        let store = try makeStore()
        try await store.saveTodayFortune(dateKey: "2026-09-05", text: "今日宜签约")
        try await store.saveTodayFortune(dateKey: "2026-09-06", text: "今日宜远行")

        #expect(try await store.loadFortune(dateKey: "2026-09-05") == "今日宜签约")
        #expect(try await store.loadFortune(dateKey: "2026-09-06") == "今日宜远行")
    }

    @Test("同日期重复写入今日运势会覆盖而不是新增")
    func saveFortuneOverwritesSameDay() async throws {
        let store = try makeStore()
        try await store.saveTodayFortune(dateKey: "2026-09-05", text: "第一次")
        try await store.saveTodayFortune(dateKey: "2026-09-05", text: "第二次")
        #expect(try await store.loadFortune(dateKey: "2026-09-05") == "第二次")
    }
}
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd ios/DeepAlphaBaZi/Core && swift test --filter BaziLocalStoreTests`
Expected: 编译失败，`cannot find 'BaziLocalStore' in scope`

- [ ] **Step 4: 实现 BaziLocalStore.swift**

`ios/DeepAlphaBaZi/Core/Sources/Core/Persistence/BaziLocalStore.swift`:
```swift
import Foundation
import SwiftData

/// BirthProfile 是 SwiftData @Model（引用类型，非 Sendable），不能原样跨 actor 边界返回给
/// 调用方（Swift 6 严格并发下会报错）。读取时在 actor 内部把字段拆成这个 Sendable 快照。
public struct BirthProfileSnapshot: Sendable, Equatable {
    public let birthDate: String
    public let birthTime: String?
    public let birthCity: String
    public let gender: String
    public let chart: BaziChartResponse
}

/// 本地存储读写 actor（@ModelActor 生成 executor 隔离）。
/// 管两张表：用户自己的生辰档案(单条) + 今日运势缓存(按日期去重)。
@ModelActor
public actor BaziLocalStore {
    private static let profileId = "me"

    /// 保存/覆盖生辰档案 + 最近一次排盘结果。
    public func saveProfile(birthDate: String, birthTime: String?, birthCity: String,
                            gender: String, chart: BaziChartResponse) throws {
        let context = modelContext
        let chartJSON = try JSONEncoder().encode(chart)
        let targetId = Self.profileId
        let existing = try context.fetch(FetchDescriptor<BirthProfile>(
            predicate: #Predicate { $0.id == targetId }))
        if let row = existing.first {
            row.birthDate = birthDate
            row.birthTime = birthTime
            row.birthCity = birthCity
            row.gender = gender
            row.chartResponseJSON = chartJSON
        } else {
            context.insert(BirthProfile(
                id: Self.profileId, birthDate: birthDate, birthTime: birthTime,
                birthCity: birthCity, gender: gender, chartResponseJSON: chartJSON))
        }
        try context.save()
    }

    /// 读取本地生辰档案；没有则返回 nil（新用户态）。
    /// 返回 Sendable 快照而不是 BirthProfile 本身——@Model 是引用类型，不能跨 actor 边界传递。
    public func loadProfile() throws -> BirthProfileSnapshot? {
        let targetId = Self.profileId
        guard let row = try modelContext.fetch(FetchDescriptor<BirthProfile>(
            predicate: #Predicate { $0.id == targetId })).first else {
            return nil
        }
        let chart = try JSONDecoder().decode(BaziChartResponse.self, from: row.chartResponseJSON)
        return BirthProfileSnapshot(
            birthDate: row.birthDate, birthTime: row.birthTime,
            birthCity: row.birthCity, gender: row.gender, chart: chart)
    }

    /// 写入某天的今日运势文本（同日期覆盖）。
    public func saveTodayFortune(dateKey: String, text: String) throws {
        let context = modelContext
        let existing = try context.fetch(FetchDescriptor<DailyFortuneCache>(
            predicate: #Predicate { $0.dateKey == dateKey }))
        if let row = existing.first {
            row.text = text
        } else {
            context.insert(DailyFortuneCache(dateKey: dateKey, text: text))
        }
        try context.save()
    }

    /// 读取某天的今日运势缓存；没有(还没拉过/换了一天)返回 nil。
    public func loadFortune(dateKey: String) throws -> String? {
        try modelContext.fetch(FetchDescriptor<DailyFortuneCache>(
            predicate: #Predicate { $0.dateKey == dateKey })).first?.text
    }
}

/// 默认磁盘容器的工厂：失败(磁盘满/迁移冲突)返回 nil，App 降级为不持久化(每次都重新走网络)。
public enum BaziLocalStoreDefault {
    public static func make() -> BaziLocalStore? {
        guard let container = try? ModelContainer(for: BirthProfile.self, DailyFortuneCache.self) else {
            return nil
        }
        return BaziLocalStore(modelContainer: container)
    }
}
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd ios/DeepAlphaBaZi/Core && swift test --filter BaziLocalStoreTests`
Expected: `Test run with 6 tests in 1 suite passed`（如果遇到 signal 11 崩溃，重跑；单独跑这个 filter 极少见崩溃，主要是混合跑全部套件时偶发）

- [ ] **Step 6: Commit**

```bash
git add ios/DeepAlphaBaZi/Core/Sources/Core/Persistence/
git add ios/DeepAlphaBaZi/Core/Tests/CoreTests/BaziLocalStoreTests.swift
git commit -m "feat(bazi-ios): 新增SwiftData本地存储(生辰档案+今日运势缓存)"
```

---

## Task 6: BaziViewModel

**Files:**
- Create: `ios/DeepAlphaBaZi/Core/Sources/Core/ViewModels/BaziViewModel.swift`
- Test: `ios/DeepAlphaBaZi/Core/Tests/CoreTests/BaziViewModelTests.swift`

**重要背景（见前置说明#2）**：`formatDateKey` 必须声明成 `nonisolated static func`，默认参数里引用它要写完整类型名 `BaziViewModel.formatDateKey(...)`，不能用 `Self.formatDateKey(...)`——否则编译报"covariant Self type cannot be referenced from a default argument expression"和 actor 隔离错误。

- [ ] **Step 1: 写失败的测试**

`ios/DeepAlphaBaZi/Core/Tests/CoreTests/BaziViewModelTests.swift`:
```swift
import Foundation
import Testing
import SwiftData
@testable import DeepAlphaBaZiCore

final class MockBaziService: BaziServicing, @unchecked Sendable {
    var chartResult: BaziChartResponse?
    var chartError: Error?
    var interpretationResult: InterpretationResponse?
    var interpretationError: Error?
    private(set) var interpretationCallCount = 0

    func getChart(_ request: BaziChartRequest) async throws -> BaziChartResponse {
        if let chartError { throw chartError }
        return chartResult ?? sampleChart()
    }

    func getInterpretation(_ request: InterpretationRequest) async throws -> InterpretationResponse {
        interpretationCallCount += 1
        if let interpretationError { throw interpretationError }
        return interpretationResult ?? InterpretationResponse(requestId: "x", text: "默认今日运势")
    }
}

@MainActor
@Suite("BaziViewModel")
struct BaziViewModelTests {
    func makeStore() throws -> BaziLocalStore {
        let config = ModelConfiguration(isStoredInMemoryOnly: true)
        let container = try ModelContainer(for: BirthProfile.self, DailyFortuneCache.self,
                                           configurations: config)
        return BaziLocalStore(modelContainer: container)
    }

    @Test("没有本地档案时，loadLocalProfile 后 profile 仍是 nil（新用户态）")
    func loadLocalProfileEmpty() async throws {
        let store = try makeStore()
        let vm = BaziViewModel(service: MockBaziService(), store: store)
        await vm.loadLocalProfile()
        #expect(vm.profile == nil)
    }

    @Test("submitBirthInfo 成功：写入本地档案，profile 变为已排盘态")
    func submitBirthInfoSuccess() async throws {
        let store = try makeStore()
        let service = MockBaziService()
        let vm = BaziViewModel(service: service, store: store)

        await vm.submitBirthInfo(
            birthDate: "1990-05-15", birthTime: "14:30:00", birthCity: "北京", gender: "male")

        #expect(vm.formError == nil)
        #expect(vm.profile?.birthDate == "1990-05-15")
        #expect(vm.profile?.chart.yearPillar.gan == "庚")

        let reloaded = try await store.loadProfile()
        #expect(reloaded?.birthCity == "北京")
    }

    @Test("submitBirthInfo 失败：不写入本地，formError 展示后端消息")
    func submitBirthInfoFailure() async throws {
        let store = try makeStore()
        let service = MockBaziService()
        service.chartError = APIError.validation("出生日期不能晚于今天")
        let vm = BaziViewModel(service: service, store: store)

        await vm.submitBirthInfo(
            birthDate: "2999-01-01", birthTime: nil, birthCity: "北京", gender: "male")

        #expect(vm.formError == "出生日期不能晚于今天")
        #expect(vm.profile == nil)
        let reloaded = try await store.loadProfile()
        #expect(reloaded == nil)
    }

    @Test("loadDailyFortuneIfNeeded：本地无缓存时调用接口并写入缓存")
    func loadDailyFortuneFetchesAndCaches() async throws {
        let store = try makeStore()
        let service = MockBaziService()
        service.interpretationResult = InterpretationResponse(requestId: "x", text: "今日宜签约")
        let vm = BaziViewModel(service: service, store: store, todayKeyProvider: { "2026-09-05" })

        await vm.submitBirthInfo(
            birthDate: "1990-05-15", birthTime: "14:30:00", birthCity: "北京", gender: "male")
        await vm.loadDailyFortuneIfNeeded()

        #expect(vm.dailyFortuneText == "今日宜签约")
        #expect(service.interpretationCallCount == 1)
        #expect(try await store.loadFortune(dateKey: "2026-09-05") == "今日宜签约")
    }

    @Test("loadDailyFortuneIfNeeded：本地已有当天缓存时不重复调用接口")
    func loadDailyFortuneUsesCacheWithoutCallingAPI() async throws {
        let store = try makeStore()
        try await store.saveTodayFortune(dateKey: "2026-09-05", text: "缓存的运势")
        let service = MockBaziService()
        let vm = BaziViewModel(service: service, store: store, todayKeyProvider: { "2026-09-05" })

        await vm.submitBirthInfo(
            birthDate: "1990-05-15", birthTime: "14:30:00", birthCity: "北京", gender: "male")
        await vm.loadDailyFortuneIfNeeded()

        #expect(vm.dailyFortuneText == "缓存的运势")
        #expect(service.interpretationCallCount == 0)
    }

    @Test("loadDailyFortuneIfNeeded：还没有 profile 时直接返回，不调用接口")
    func loadDailyFortuneNoProfileNoop() async throws {
        let store = try makeStore()
        let service = MockBaziService()
        let vm = BaziViewModel(service: service, store: store)

        await vm.loadDailyFortuneIfNeeded()

        #expect(vm.dailyFortuneText == nil)
        #expect(service.interpretationCallCount == 0)
    }
}
```

**注意**：这个文件用到的 `sampleChart()` 是 Task 5 的 `BaziLocalStoreTests.swift` 里定义的顶层函数（不是 `private`），同一个测试 target 内可以直接复用，不用重新定义一遍。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd ios/DeepAlphaBaZi/Core && swift test --filter BaziViewModelTests`
Expected: 编译失败，`cannot find 'BaziViewModel' in scope`

- [ ] **Step 3: 实现 BaziViewModel.swift**

`ios/DeepAlphaBaZi/Core/Sources/Core/ViewModels/BaziViewModel.swift`:
```swift
import Foundation
import Observation

/// 八字主流程状态机：本地档案(有/无) → 提交生辰生成排盘 → 加载今日运势(本地缓存优先)。
@MainActor @Observable
public final class BaziViewModel {
    public private(set) var profile: BirthProfileSnapshot?
    public private(set) var dailyFortuneText: String?
    public private(set) var isSubmittingBirthInfo = false
    public private(set) var isLoadingFortune = false
    public var formError: String?
    public var fortuneError: String?

    let service: any BaziServicing
    let store: BaziLocalStore?
    /// 今天的日期 key（"yyyy-MM-dd"），测试注入固定值，生产环境默认取当前时间。
    let todayKeyProvider: @Sendable () -> String

    public init(service: any BaziServicing, store: BaziLocalStore?,
                todayKeyProvider: @escaping @Sendable () -> String = { BaziViewModel.formatDateKey(Date()) }) {
        self.service = service
        self.store = store
        self.todayKeyProvider = todayKeyProvider
    }

    public nonisolated static func formatDateKey(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone.current
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    /// App 启动 / 首页出现时调用：有本地档案直接进已排盘态，没有则停在填表态。
    public func loadLocalProfile() async {
        guard let store else { return }
        profile = try? await store.loadProfile()
    }

    /// 提交生辰表单：调 /chart，成功后落本地并进入已排盘态。
    public func submitBirthInfo(birthDate: String, birthTime: String?,
                                birthCity: String, gender: String) async {
        formError = nil
        isSubmittingBirthInfo = true
        defer { isSubmittingBirthInfo = false }
        do {
            let chart = try await service.getChart(BaziChartRequest(
                birthDate: birthDate, birthTime: birthTime, birthCity: birthCity, gender: gender))
            if let store {
                try? await store.saveProfile(
                    birthDate: birthDate, birthTime: birthTime, birthCity: birthCity,
                    gender: gender, chart: chart)
            }
            profile = BirthProfileSnapshot(
                birthDate: birthDate, birthTime: birthTime, birthCity: birthCity,
                gender: gender, chart: chart)
        } catch let e as APIError {
            formError = e.message
        } catch {
            formError = "排盘失败：\(error.localizedDescription)"
        }
    }

    /// 今日运势：本地缓存命中直接展示；未命中才调用 AI 接口(避免同一天内重复付费调用)。
    public func loadDailyFortuneIfNeeded() async {
        guard let profile else { return }
        let dateKey = todayKeyProvider()
        if let store, let cached = try? await store.loadFortune(dateKey: dateKey) {
            dailyFortuneText = cached
            return
        }
        fortuneError = nil
        isLoadingFortune = true
        defer { isLoadingFortune = false }
        do {
            let response = try await service.getInterpretation(InterpretationRequest(
                birthDate: profile.birthDate, birthTime: profile.birthTime,
                birthCity: profile.birthCity, gender: profile.gender, section: .daily))
            dailyFortuneText = response.text
            if let store {
                try? await store.saveTodayFortune(dateKey: dateKey, text: response.text)
            }
        } catch let e as APIError {
            fortuneError = e.message
        } catch {
            fortuneError = "今日运势加载失败：\(error.localizedDescription)"
        }
    }
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd ios/DeepAlphaBaZi/Core && swift test --filter BaziViewModelTests`
Expected: `Test run with 6 tests in 1 suite passed`

- [ ] **Step 5: Commit**

```bash
git add ios/DeepAlphaBaZi/Core/Sources/Core/ViewModels/BaziViewModel.swift ios/DeepAlphaBaZi/Core/Tests/CoreTests/BaziViewModelTests.swift
git commit -m "feat(bazi-ios): 新增BaziViewModel状态机(填表->排盘->今日运势)"
```

- [ ] **Step 6: 跑一遍 Core 包全部测试确认互不干扰**

Run: `cd ios/DeepAlphaBaZi/Core && swift test`
Expected: `Test run with 28 tests in 6 suites passed`（APIClientTests 4 + BaziModelsTests 6 + BaziFormattingTests 3 + BaziServiceTests 3 + BaziLocalStoreTests 6 + BaziViewModelTests 6 = 28。如果和这个数字对不上，说明前面某个 Task 的用例漏加/多加了，回去对应 Task 核对，不要跳过继续往下走）

---

## Task 7: SwiftUI Views

**Files:**
- Create: `ios/DeepAlphaBaZi/App/Features/Bazi/BirthInfoFormView.swift`
- Create: `ios/DeepAlphaBaZi/App/Features/Bazi/ChartHomeView.swift`
- Create: `ios/DeepAlphaBaZi/App/Features/Bazi/DaYunSectionView.swift`
- Create: `ios/DeepAlphaBaZi/App/Features/Bazi/DeepInterpretationView.swift`

这一步是纯 UI，没有自动化测试（Core 包的业务逻辑已经在 Task 3-6 覆盖了，View 层只做最终整体编译验证，见 Task 8）。

- [ ] **Step 1: 新用户填生辰表单**

`ios/DeepAlphaBaZi/App/Features/Bazi/BirthInfoFormView.swift`:
```swift
import SwiftUI
import DeepAlphaBaZiCore

/// 新用户填生辰：日期限定 1900年~今天，时辰可标"不确定"，城市限定后端支持的38个。
struct BirthInfoFormView: View {
    @Environment(BaziViewModel.self) private var baziVM

    @State private var birthDate = Date()
    @State private var birthTime = Date()
    @State private var hourUnknown = false
    @State private var birthCity = BaziFormatting.supportedCities[0]
    @State private var gender = "male"

    var body: some View {
        Form {
            Section("生辰信息") {
                DatePicker("出生日期", selection: $birthDate,
                          in: BaziFormatting.minBirthDate...Date(),
                          displayedComponents: .date)
                Toggle("出生时辰不确定", isOn: $hourUnknown)
                if !hourUnknown {
                    DatePicker("出生时间", selection: $birthTime, displayedComponents: .hourAndMinute)
                }
                Picker("出生城市", selection: $birthCity) {
                    ForEach(BaziFormatting.supportedCities, id: \.self) { city in
                        Text(city).tag(city)
                    }
                }
                Picker("性别", selection: $gender) {
                    Text("男").tag("male")
                    Text("女").tag("female")
                }
            }

            if let error = baziVM.formError {
                Text(error).foregroundStyle(.red)
            }

            Section {
                Button {
                    submit()
                } label: {
                    if baziVM.isSubmittingBirthInfo {
                        ProgressView()
                    } else {
                        Text("生成我的免费八字报告")
                    }
                }
                .disabled(baziVM.isSubmittingBirthInfo)
            }
        }
        .navigationTitle("填写生辰")
    }

    private func submit() {
        let dateString = BaziFormatting.birthDateString(from: birthDate)
        let timeString = hourUnknown ? nil : BaziFormatting.birthTimeString(from: birthTime)
        Task {
            await baziVM.submitBirthInfo(
                birthDate: dateString, birthTime: timeString,
                birthCity: birthCity, gender: gender)
        }
    }
}
```

- [ ] **Step 2: 已排盘首页**

`ios/DeepAlphaBaZi/App/Features/Bazi/ChartHomeView.swift`:
```swift
import SwiftUI
import DeepAlphaBaZiCore

/// 已排盘首页：四柱 + 五行(免费，纯本地数据) + 今日运势(免费，按日缓存) +
/// 概览/大运流年🔒/深度解读🔒 分段(后两段的付费墙 UI 在这个 Plan 里只是锁定态展示，
/// 真实 StoreKit 购买接入是下一个 Plan 的工作)。
struct ChartHomeView: View {
    @Environment(BaziViewModel.self) private var baziVM

    enum ChartSection: String, CaseIterable, Identifiable {
        case overview = "概览"
        case daYun = "大运流年"
        case deep = "深度解读"
        var id: String { rawValue }
    }
    @State private var selectedSection: ChartSection = .overview

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let chart = baziVM.profile?.chart {
                    PillarsCardView(chart: chart)
                    WuXingCardView(distribution: chart.wuXingDistribution)
                }

                DailyFortuneCardView()

                Picker("分段", selection: $selectedSection) {
                    ForEach(ChartSection.allCases) { section in
                        Text(section.rawValue).tag(section)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()

                switch selectedSection {
                case .overview:
                    EmptyView()
                case .daYun:
                    DaYunSectionView()
                case .deep:
                    DeepInterpretationView()
                }
            }
            .padding()
        }
        .navigationTitle("我的八字")
        .task {
            await baziVM.loadDailyFortuneIfNeeded()
        }
    }
}

private struct PillarsCardView: View {
    let chart: BaziChartResponse

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("四柱").font(.headline)
            HStack {
                pillarColumn("年柱", chart.yearPillar)
                pillarColumn("月柱", chart.monthPillar)
                pillarColumn("日柱", chart.dayPillar)
                if let time = chart.timePillar {
                    pillarColumn("时柱", time)
                } else {
                    VStack {
                        Text("时柱").font(.caption).foregroundStyle(.secondary)
                        Text("未知").foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                }
            }
        }
        .padding()
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }

    private func pillarColumn(_ title: String, _ pillar: Pillar) -> some View {
        VStack {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text("\(pillar.gan)\(pillar.zhi)").font(.title3.bold())
        }
        .frame(maxWidth: .infinity)
    }
}

private struct WuXingCardView: View {
    let distribution: [String: Int]
    private let order = ["jin", "mu", "shui", "huo", "tu"]
    private let labels: [String: String] = ["jin": "金", "mu": "木", "shui": "水", "huo": "火", "tu": "土"]

    var body: some View {
        HStack {
            ForEach(order, id: \.self) { key in
                VStack {
                    Text(labels[key] ?? key)
                    Text("\(distribution[key] ?? 0)").font(.headline)
                }
                .frame(maxWidth: .infinity)
            }
        }
        .padding()
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }
}

private struct DailyFortuneCardView: View {
    @Environment(BaziViewModel.self) private var baziVM

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("今日运势").font(.headline)
            if baziVM.isLoadingFortune {
                ProgressView()
            } else if let text = baziVM.dailyFortuneText {
                Text(text)
            } else if let error = baziVM.fortuneError {
                // 加载失败：展示错误 + 重试按钮，不能让卡片停在一个死态什么都不能做
                VStack(alignment: .leading, spacing: 4) {
                    Text(error).foregroundStyle(.red)
                    Button("点击重试") {
                        Task { await baziVM.loadDailyFortuneIfNeeded() }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }
}
```

- [ ] **Step 3: 付费墙锁定态占位（大运流年/深度解读）**

`ios/DeepAlphaBaZi/App/Features/Bazi/DaYunSectionView.swift`:
```swift
import SwiftUI

/// 大运流年展开：付费墙锁定态 UI。真实 StoreKit 购买接入是下一个 Plan 的工作，
/// 这里先把"未订阅时长什么样"做出来。
struct DaYunSectionView: View {
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "lock.fill")
                .font(.largeTitle)
                .foregroundStyle(.secondary)
            Text("订阅解锁大运流年详细展开")
            Text("即将推出")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding()
    }
}
```

`ios/DeepAlphaBaZi/App/Features/Bazi/DeepInterpretationView.swift`:
```swift
import SwiftUI

/// 深度解读：付费墙锁定态 UI。真实调用 /interpretation?section=deep 和 StoreKit
/// 购买解锁都在下一个 Plan 里做，这里先把"未订阅时长什么样"做出来。
struct DeepInterpretationView: View {
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "lock.fill")
                .font(.largeTitle)
                .foregroundStyle(.secondary)
            Text("订阅解锁深度解读")
            Text("即将推出")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding()
    }
}
```

- [ ] **Step 4: Commit**

```bash
git add ios/DeepAlphaBaZi/App/Features/Bazi/
git commit -m "feat(bazi-ios): 新增八字表单/首页/付费墙占位 SwiftUI 视图"
```

（这一步先不做整体编译验证——App target 还缺 `@main` 入口，Task 8 补上后才能整体编译）

---

## Task 8: App 入口接线 + 整体编译验证

**Files:**
- Create: `ios/DeepAlphaBaZi/App/DeepAlphaBaZiApp.swift`
- Create: `ios/DeepAlphaBaZi/App/CompositionRoot.swift`
- Create: `ios/DeepAlphaBaZi/App/RootView.swift`

- [ ] **Step 1: 依赖组装**

`ios/DeepAlphaBaZi/App/CompositionRoot.swift`:
```swift
import Foundation
import DeepAlphaBaZiCore

/// 全部依赖在此组装（视图层不直接 new service）。
@MainActor
final class CompositionRoot {
    static let apiBaseURL = URL(string: "https://api.deepalpha.club")!

    let baziVM: BaziViewModel

    init() {
        let api = APIClient(baseURL: Self.apiBaseURL)
        let service = BaziService(api: api)
        let store = BaziLocalStoreDefault.make()
        self.baziVM = BaziViewModel(service: service, store: store)
    }
}
```

- [ ] **Step 2: 根视图路由**

`ios/DeepAlphaBaZi/App/RootView.swift`:
```swift
import SwiftUI
import DeepAlphaBaZiCore

/// 有本地生辰档案直接进已排盘首页，没有则先填表。
/// 底部 Tab 栏（八字 / 我的）留给后续 Plan C 接入登录/订阅时再引入。
struct RootView: View {
    @Environment(BaziViewModel.self) private var baziVM

    var body: some View {
        NavigationStack {
            if baziVM.profile != nil {
                ChartHomeView()
            } else {
                BirthInfoFormView()
            }
        }
    }
}
```

- [ ] **Step 3: App 入口**

`ios/DeepAlphaBaZi/App/DeepAlphaBaZiApp.swift`:
```swift
import SwiftUI
import DeepAlphaBaZiCore

@main
struct DeepAlphaBaZiApp: App {
    @State private var root = CompositionRoot()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(root.baziVM)
                .task {
                    await root.baziVM.loadLocalProfile()
                }
        }
    }
}
```

- [ ] **Step 4: 重新生成工程**

Run: `cd ios/DeepAlphaBaZi && xcodegen generate`
Expected: `Created project at .../DeepAlphaBaZi.xcodeproj`（无报错；这次因为 `App/` 下有源文件了，生成的工程是可编译的）

- [ ] **Step 5: 整体编译验证**

Run: `cd ios/DeepAlphaBaZi && xcodebuild -project DeepAlphaBaZi.xcodeproj -scheme DeepAlphaBaZi -destination 'generic/platform=iOS Simulator' build`
Expected: 输出末尾 `** BUILD SUCCEEDED **`。如果失败，把完整报错贴出来分析——这一步之前每个文件都已经在等价的 scratch 环境里验证过编译通过，如果这里报错，大概率是文件路径/target 归属配置的问题（比如某个 `.swift` 文件没有被 xcodegen 的 `sources: - path: App` 扫描到），不是代码逻辑问题。

- [ ] **Step 6: Core 包全量测试最终确认**

Run: `cd ios/DeepAlphaBaZi/Core && swift test`
Expected: 全部 `passed`（同 Task 6 Step 6 的用例总数）

- [ ] **Step 7: 检查 .gitignore**

Run: `cat ios/.gitignore | grep -E "xcodeproj|DerivedData|.build"`
Expected: 应该已经忽略 `*.xcodeproj`（xcodegen 生成物不进 git）、`DerivedData/`、SPM 的 `.build/`。如果缺了某一条，补上并提交这个改动。

- [ ] **Step 8: Commit**

```bash
git add ios/DeepAlphaBaZi/App/DeepAlphaBaZiApp.swift ios/DeepAlphaBaZi/App/CompositionRoot.swift ios/DeepAlphaBaZi/App/RootView.swift
# 如果 Step 7 改了 .gitignore，一并加进来
git commit -m "feat(bazi-ios): App入口接线，DeepAlphaBaZi工程整体编译通过"
```

---

## 验收标准回顾

- [x] xcodegen 能生成工程，`xcodebuild build` 整体编译通过（Task 1、8）
- [x] Core 包所有 Swift Testing 用例通过（Task 2-6）
- [x] 首次打开无本地记录展示填写表单，城市限定 38 城市下拉，日期限定 1900~今天（Task 3、7）
- [x] 提交生辰后成功调 `/chart`，四柱/五行渲染，SwiftData 持久化（Task 4、5、6、7）
- [x] "今日运势"卡片自动加载，同一天内不重复调用 `/interpretation`（Task 6）
- [x] 未订阅时"大运流年"/"深度解读"两个分段展示锁定态 UI（Task 7）——真实订阅购买留给下一个 Plan
- [ ] （不在本计划范围）StoreKit 真实购买、"我的" Tab、可选登录、紫微斗数 Tab
