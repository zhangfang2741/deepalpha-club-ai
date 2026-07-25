# WordLens iOS App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 做一个独立的 SwiftUI iOS App（WordLens），拍照识别英语单词、生成音标释义、加入生词库，用 SM-2 间隔重复算法驱动持续复习，消费已经实现并合并到 `master` 的后端 API（`/api/v1/vocabulary/*`）。

**Architecture:** 新建 `ios/WordLens.xcodeproj`（与 `ios/DeepAlphaChan.xcodeproj` 平级），SwiftUI + MVVM，网络层/Keychain/配色等基础设施直接照搬 `ios/DeepAlphaChan` 已验证过的模式（`actor` 单例 APIClient + Keychain 存 token + `enum` 命名空间 Service），零第三方依赖（全用系统框架：`Foundation`/`AVFoundation`/`PhotosUI`/`Security`）。

**Tech Stack:** Swift 5 + SwiftUI，部署目标 iOS 17.0，`AVSpeechSynthesizer` 做发音，`PhotosPicker`（`PhotosUI`）做选图/拍照。

**重要环境约束：** 这个开发环境只装了 Xcode Command Line Tools，没有完整 Xcode，**无法在这里编译/运行 iOS 代码**。按用户选择的方式推进：先按计划写完所有 Swift 文件（每个 Task 只做「写文件 + 走查代码逻辑」，没有编译验证步骤），全部写完后由用户在自己 Mac 上用 Xcode 打开工程、连手机跑一遍（对应本计划最后的 Task 11），有编译报错再回头修。

**后端对接：** 手机和开发用的 Mac 在同一 WiFi 下，`AppConfig.baseURL` 指向 Mac 的局域网 IP（当前是 `192.168.1.7`，**这个 IP 由路由器 DHCP 分配，可能会变**——如果某天 App 连不上后端，先用 `ipconfig getifaddr en0`〔在 Mac 终端跑〕确认当前 IP 有没有变，变了就改 `AppConfig.swift` 里的 `baseURL`）。跑之前需要先在 Mac 上 `make dev` 把后端启起来（监听 `0.0.0.0:8000`，不能只监听 `127.0.0.1`，否则手机连不上——`make dev` 默认用 uvicorn `--reload`，需要确认它绑定的是 `0.0.0.0`，见 Task 1 里的检查步骤）。

设计依据：[docs/superpowers/specs/2026-07-25-vocab-camera-ios-design.md](../specs/2026-07-25-vocab-camera-ios-design.md)
后端 API 契约：[docs/superpowers/plans/2026-07-25-vocab-camera-backend.md](2026-07-25-vocab-camera-backend.md) 第 5 节

---

## 文件结构总览

```
ios/WordLens.xcodeproj/                          # Task 1：手动用 Xcode 创建
ios/WordLens/
├── App/
│   ├── WordLensApp.swift                        # @main 入口
│   ├── AppConfig.swift                           # baseURL 等配置
│   └── Theme.swift                                # 配色
├── Networking/
│   ├── APIClient.swift                            # 网络层核心（照搬 DeepAlphaChan + 加 multipart 上传）
│   ├── KeychainStore.swift                         # token 存取（照搬 DeepAlphaChan，改 service 常量）
│   ├── AuthService.swift                           # 注册/登录
│   └── WordService.swift                           # 识别/生词库/复习
├── Models/
│   ├── AuthModels.swift                            # 登录/注册响应模型
│   └── WordModels.swift                            # 生词/候选词/复习队列模型
├── ViewModels/
│   ├── AuthViewModel.swift                         # 登录态 + 登录/注册
│   ├── CameraViewModel.swift                       # 拍照识别流程
│   ├── WordListViewModel.swift                     # 生词库列表
│   └── ReviewViewModel.swift                       # 复习队列 + 发音
├── Views/
│   ├── RootView.swift                              # 登录态路由
│   ├── LoginView.swift
│   ├── RegisterView.swift
│   ├── MainTabView.swift                           # 底部三个 Tab
│   ├── HomeView.swift                              # 首页统计 + 入口
│   ├── CameraCaptureView.swift                     # 拍照/选图
│   ├── RecognizeResultView.swift                   # 候选词勾选加入
│   ├── WordListView.swift                          # 生词库列表
│   ├── WordDetailView.swift                        # 单词详情
│   ├── ReviewCardView.swift                        # 复习卡片流
│   ├── SettingsView.swift                          # 口音设置 + 登出
│   └── Components/
│       └── PronounceButton.swift                   # 发音按钮（封装 AVSpeechSynthesizer）
└── Resources/
    ├── Assets.xcassets                             # Task 1 创建工程时自带
    └── Info.plist                                  # Task 1 手动配置
```

---

### Task 1: 创建 Xcode 工程 + 基础配置（手动操作，不是写代码）

这一步**必须在你自己的 Mac 上用 Xcode 手动完成**，因为新建 `.xcodeproj` 需要 Xcode 生成工程文件结构，这个环境没有完整 Xcode 做不了。

- [ ] **Step 1: 用 Xcode 新建工程**

1. 打开 Xcode → File → New → Project
2. 选 iOS → App，Next
3. 填写：
   - Product Name: `WordLens`
   - Team: 你自己的（没有 Apple Developer 账号也可以选 "None" 先跑模拟器）
   - Organization Identifier: `club.deepalpha`（这样 Bundle ID 会是 `club.deepalpha.WordLens`）
   - Interface: **SwiftUI**
   - Language: **Swift**
   - 不勾选 "Use Core Data"、不勾选 "Include Tests"（跟 `DeepAlphaChan` 保持一致）
4. Next，保存位置选 `/Users/zhangfang/deepalpha-club-ai/ios/`（**不是** `ios/WordLens/` 里面，是 `ios/` 这一级，Xcode 会自动建 `ios/WordLens/` 子目录和 `ios/WordLens.xcodeproj`）
5. 创建后，Xcode 会生成 `WordLensApp.swift`、`ContentView.swift`、`Assets.xcassets`、`Preview Content/` 等默认文件

- [ ] **Step 2: 清理默认模板文件**

删除 Xcode 自动生成的 `ContentView.swift`（后面会用自己的 `Views/RootView.swift` 替代）。`WordLensApp.swift` 先留着，Task 5 会整体替换内容。

- [ ] **Step 3: 建目录结构**

在 Xcode 左侧文件导航里，右键 `WordLens` 组 → New Group，依次建：`App`（把 `WordLensApp.swift` 拖进去）、`Networking`、`Models`、`ViewModels`、`Views`、`Views/Components`。这个工程默认是 Xcode 16 的「文件系统同步」模式（跟 `DeepAlphaChan` 一样），建的 Group 会对应真实目录，后面 Task 直接把 `.swift` 文件放进对应目录即可，不需要手动拖入 Xcode 或改 `.pbxproj`。

- [ ] **Step 4: 设置部署目标**

选中工程 → Target `WordLens` → General → Minimum Deployments，改成 **iOS 17.0**（跟 `DeepAlphaChan` 一致）。

- [ ] **Step 5: 添加自定义 Info.plist**

Xcode 16 默认工程用 Build Settings 生成 Info.plist，没有物理文件。为了配置相机权限和本地网络访问，需要加一个物理 `Info.plist` 文件：

1. 右键 `WordLens/Resources`（先建这个 Group）→ New File → Property List，命名 `Info.plist`
2. 用下面的完整内容替换（这个文件写好后用 Edit 工具打开确认内容，不需要在 Xcode 里手填每一项，直接用文本编辑器/Xcode 源码模式粘贴即可）：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDevelopmentRegion</key>
	<string>zh_CN</string>
	<key>CFBundleDisplayName</key>
	<string>WordLens</string>
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
	<string>$(MARKETING_VERSION)</string>
	<key>CFBundleVersion</key>
	<string>$(CURRENT_PROJECT_VERSION)</string>
	<key>UILaunchScreen</key>
	<dict/>
	<key>UISupportedInterfaceOrientations</key>
	<array>
		<string>UIInterfaceOrientationPortrait</string>
	</array>
	<key>ITSAppUsesNonExemptEncryption</key>
	<false/>
	<key>NSCameraUsageDescription</key>
	<string>需要访问相机拍摄含英语单词的文档或书页，用于识别生词</string>
	<key>NSPhotoLibraryUsageDescription</key>
	<string>需要访问相册选择含英语单词的图片，用于识别生词</string>
	<key>NSLocalNetworkUsageDescription</key>
	<string>需要连接同一 WiFi 下的开发服务器进行本地调试</string>
	<key>NSAppTransportSecurity</key>
	<dict>
		<!-- 生产应改为 HTTPS；MVP 阶段手机连 Mac 本机局域网 IP 走明文 HTTP 调试 -->
		<key>NSAllowsLocalNetworking</key>
		<true/>
	</dict>
</dict>
</plist>
```

3. 选中 Target `WordLens` → Build Settings → 搜索 `Info.plist File`，把值设成 `WordLens/Resources/Info.plist`（指向刚建的文件，这样构建时会用它而不是自动生成的）

- [ ] **Step 6: 创建 `App/AppConfig.swift`**

```swift
// App/AppConfig.swift
import Foundation

/// 全局配置：后端地址等。
enum AppConfig {
    /// 手机和 Mac 同一 WiFi 下，指向 Mac 的局域网 IP（`make dev` 起的后端，监听 0.0.0.0:8000）。
    /// 这个 IP 是路由器 DHCP 分配的，可能会变——连不上时先在 Mac 终端跑
    /// `ipconfig getifaddr en0` 确认当前 IP，变了就改这里。
    static let baseURL = URL(string: "http://192.168.1.7:8000")!
    static let apiPrefix = "/api/v1/vocabulary"
    static let requestTimeout: TimeInterval = 30
    /// 拍照识别调 LLM，比普通请求慢很多，单独给更长超时。
    static let recognizeTimeout: TimeInterval = 60
}
```

- [ ] **Step 7: 创建 `App/Theme.swift`**

```swift
// App/Theme.swift
import SwiftUI

/// 全局配色，深色系，风格与 DeepAlphaChan 保持一致但换成背单词场景色。
enum Theme {
    static let accent = Color(hex: 0x3B82F6)
    static let background = Color(hex: 0x0B0E14)
    static let surface = Color(hex: 0x141A24)
    static let surfaceAlt = Color(hex: 0x1C2431)
    static let border = Color(hex: 0x263041)
    static let textPrimary = Color(hex: 0xE6EDF3)
    static let textSecondary = Color(hex: 0x8B98A9)

    /// 三档标记状态色：不认识/模糊/认识
    static let unknown = Color(hex: 0xEF4444)
    static let fuzzy = Color(hex: 0xF59E0B)
    static let known = Color(hex: 0x22C55E)
}

extension Color {
    init(hex: UInt32, alpha: Double = 1.0) {
        let r = Double((hex >> 16) & 0xFF) / 255.0
        let g = Double((hex >> 8) & 0xFF) / 255.0
        let b = Double(hex & 0xFF) / 255.0
        self.init(.sRGB, red: r, green: g, blue: b, opacity: alpha)
    }
}
```

- [ ] **Step 8: 提交（先不 push，本地 commit 即可，iOS 工程后续 Task 会持续追加文件）**

```bash
cd /Users/zhangfang/deepalpha-club-ai
git add ios/WordLens.xcodeproj ios/WordLens
git commit -m "feat(ios-wordlens): 新建 WordLens Xcode 工程骨架"
```

---

### Task 2: 网络层（APIClient + KeychainStore）

**Files:**
- Create: `ios/WordLens/Networking/KeychainStore.swift`
- Create: `ios/WordLens/Networking/APIClient.swift`

- [ ] **Step 1: 创建 `KeychainStore.swift`**

```swift
// Networking/KeychainStore.swift
import Foundation
import Security

/// 极简 Keychain 封装，安全保存 JWT。App 卸载即清除，不进 iCloud 明文备份。
enum KeychainStore {
    private static let service = "club.deepalpha.wordlens"
    private static let tokenAccount = "access_token"

    static func saveToken(_ token: String) {
        save(key: tokenAccount, value: token)
    }

    static func loadToken() -> String? {
        load(key: tokenAccount)
    }

    static func clearToken() {
        delete(key: tokenAccount)
    }

    // MARK: - 底层读写

    private static func save(key: String, value: String) {
        guard let data = value.data(using: .utf8) else { return }
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
        SecItemDelete(query as CFDictionary)
        var attrs = query
        attrs[kSecValueData as String] = data
        attrs[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(attrs as CFDictionary, nil)
    }

    private static func load(key: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data,
              let value = String(data: data, encoding: .utf8) else {
            return nil
        }
        return value
    }

    private static func delete(key: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
        SecItemDelete(query as CFDictionary)
    }
}
```

- [ ] **Step 2: 创建 `APIClient.swift`**

在 DeepAlphaChan 的 `APIClient` 基础上加一个 `postMultipart`（拍照识别要传图片文件）：

```swift
// Networking/APIClient.swift
import Foundation

/// 网络错误，携带对用户友好的中文信息（尽量透传后端 detail）。
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

    /// 上传图片（multipart/form-data，字段名固定为 "image"，匹配后端 `UploadFile = File(...)` 的参数名）。
    func postMultipartImage<T: Decodable>(_ path: String, imageData: Data, filename: String = "photo.jpg") async throws -> T {
        var req = request(path: path, method: "POST")
        let boundary = "Boundary-\(UUID().uuidString)"
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = AppConfig.recognizeTimeout

        var body = Data()
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
```

- [ ] **Step 3: 走查代码**

对照后端 API：`AppConfig.apiPrefix` 是 `/api/v1/vocabulary`，`APIClient` 里所有 `path` 参数据此应该只传 `/auth/register`、`/words` 这种后缀（不重复带 `/api/v1/vocabulary` 前缀），后面写 Service 层时要注意。`postMultipartImage` 的表单字段名 `"image"` 必须跟后端 `app/api/v1/vocabulary/words.py` 里 `image: UploadFile = File(...)` 的参数名一致（已核对一致）。

- [ ] **Step 4: 提交**

```bash
cd /Users/zhangfang/deepalpha-club-ai
git add ios/WordLens/Networking/
git commit -m "feat(ios-wordlens): 网络层 APIClient + KeychainStore"
```

---

### Task 3: 数据模型 + Service 层

**Files:**
- Create: `ios/WordLens/Models/AuthModels.swift`
- Create: `ios/WordLens/Models/WordModels.swift`
- Create: `ios/WordLens/Networking/AuthService.swift`
- Create: `ios/WordLens/Networking/WordService.swift`

- [ ] **Step 1: 创建 `Models/AuthModels.swift`**

对照后端 `VocabularyTokenResponse`（`app/schemas/vocabulary.py`）：`access_token`/`token_type`/`expires_at`（还有个 `request_id` 字段，前端用不到，不用建模）。

```swift
// Models/AuthModels.swift
import Foundation

/// 对应后端 VocabularyTokenResponse（注册/登录成功后的响应）。
struct AuthTokenResponse: Codable {
    let accessToken: String
    let tokenType: String
    let expiresAt: String

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case tokenType = "token_type"
        case expiresAt = "expires_at"
    }
}
```

- [ ] **Step 2: 创建 `Models/WordModels.swift`**

对照后端 `RecognizedWordSchema`/`RecognizeResponse`/`VocabularyWordResponse`/`WordsBatchCreateResponse`/`VocabularyWordListResponse`/`ReviewQueueResponse`/`ReviewSubmitResponse`（均在 `app/schemas/vocabulary.py`）：

```swift
// Models/WordModels.swift
import Foundation

/// 拍照识别出的候选词，对应后端 RecognizedWordSchema。
struct RecognizedWord: Codable, Identifiable {
    let word: String
    let phoneticIpa: String
    let partOfSpeech: String
    let definitionZh: String
    let alreadyInLibrary: Bool

    var id: String { word }

    enum CodingKeys: String, CodingKey {
        case word
        case phoneticIpa = "phonetic_ipa"
        case partOfSpeech = "part_of_speech"
        case definitionZh = "definition_zh"
        case alreadyInLibrary = "already_in_library"
    }
}

/// 对应后端 RecognizeResponse。
struct RecognizeResponse: Codable {
    let candidates: [RecognizedWord]
}

/// 生词库条目，对应后端 VocabularyWordResponse。
struct VocabularyWord: Codable, Identifiable {
    let id: String
    let word: String
    let phoneticIpa: String
    let partOfSpeech: String
    let definitionZh: String
    let status: String
    let repetitionCount: Int
    let easinessFactor: Double
    let intervalDays: Int
    let nextReviewAt: String
    let lastReviewedAt: String?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, word, status
        case phoneticIpa = "phonetic_ipa"
        case partOfSpeech = "part_of_speech"
        case definitionZh = "definition_zh"
        case repetitionCount = "repetition_count"
        case easinessFactor = "easiness_factor"
        case intervalDays = "interval_days"
        case nextReviewAt = "next_review_at"
        case lastReviewedAt = "last_reviewed_at"
        case createdAt = "created_at"
    }
}

/// 提交给 /words/batch 的单个词，对应后端 VocabularyWordCreate。
struct VocabularyWordCreate: Codable {
    let word: String
    let phoneticIpa: String
    let partOfSpeech: String
    let definitionZh: String

    enum CodingKeys: String, CodingKey {
        case word
        case phoneticIpa = "phonetic_ipa"
        case partOfSpeech = "part_of_speech"
        case definitionZh = "definition_zh"
    }
}

/// 对应后端 WordsBatchCreateResponse。
struct WordsBatchCreateResponse: Codable {
    let created: [VocabularyWord]
    let skippedExisting: [String]

    enum CodingKeys: String, CodingKey {
        case created
        case skippedExisting = "skipped_existing"
    }
}

/// 对应后端 VocabularyWordListResponse。
struct VocabularyWordListResponse: Codable {
    let words: [VocabularyWord]
}

/// 对应后端 ReviewQueueResponse。
struct ReviewQueueResponse: Codable {
    let words: [VocabularyWord]
}

/// 对应后端 ReviewSubmitResponse。
struct ReviewSubmitResponse: Codable {
    let word: VocabularyWord
}

/// 三档复习评分，对应后端 rating 字段（0/1/2）。
enum ReviewRating: Int {
    case unknown = 0
    case fuzzy = 1
    case known = 2
}
```

- [ ] **Step 3: 创建 `Networking/AuthService.swift`**

```swift
// Networking/AuthService.swift
import Foundation

/// WordLens 独立账号的注册/登录，对应后端 /vocabulary/auth/*。
enum AuthService {
    static func register(email: String, password: String) async throws -> AuthTokenResponse {
        struct Body: Encodable { let email: String; let password: String }
        return try await APIClient.shared.postJSON("/auth/register", body: Body(email: email, password: password))
    }

    static func login(email: String, password: String) async throws -> AuthTokenResponse {
        struct Body: Encodable { let email: String; let password: String }
        return try await APIClient.shared.postJSON("/auth/login", body: Body(email: email, password: password))
    }
}
```

- [ ] **Step 4: 创建 `Networking/WordService.swift`**

```swift
// Networking/WordService.swift
import Foundation

/// 拍照识别 + 生词库 + 复习，对应后端 /vocabulary/{recognize,words,review}。
enum WordService {
    static func recognize(imageData: Data) async throws -> RecognizeResponse {
        try await APIClient.shared.postMultipartImage("/recognize", imageData: imageData)
    }

    static func addWordsBatch(_ words: [VocabularyWordCreate]) async throws -> WordsBatchCreateResponse {
        struct Body: Encodable { let words: [VocabularyWordCreate] }
        return try await APIClient.shared.postJSON("/words/batch", body: Body(words: words))
    }

    static func listWords(status: String? = nil, query: String? = nil) async throws -> [VocabularyWord] {
        var params: [String: String] = [:]
        if let status { params["status"] = status }
        if let query, !query.isEmpty { params["q"] = query }
        let resp: VocabularyWordListResponse = try await APIClient.shared.get("/words", query: params)
        return resp.words
    }

    static func wordDetail(id: String) async throws -> VocabularyWord {
        try await APIClient.shared.get("/words/\(id)")
    }

    static func deleteWord(id: String) async throws {
        struct DeleteResponse: Decodable { let deleted: Bool }
        let _: DeleteResponse = try await APIClient.shared.delete("/words/\(id)")
    }

    static func reviewQueue() async throws -> [VocabularyWord] {
        let resp: ReviewQueueResponse = try await APIClient.shared.get("/review/queue")
        return resp.words
    }

    static func submitReview(wordId: String, rating: ReviewRating) async throws -> VocabularyWord {
        struct Body: Encodable { let rating: Int }
        let resp: ReviewSubmitResponse = try await APIClient.shared.postJSON(
            "/words/\(wordId)/review", body: Body(rating: rating.rawValue)
        )
        return resp.word
    }
}
```

- [ ] **Step 5: 走查代码**

确认每个 Service 方法的 path 拼接后跟后端路由完全对应（`AppConfig.apiPrefix` + Service 里的 path）：
- `/api/v1/vocabulary` + `/auth/register` = `/api/v1/vocabulary/auth/register` ✓ 对应 `app/api/v1/vocabulary/auth.py` 的 `/register`
- `/api/v1/vocabulary` + `/recognize` = `/api/v1/vocabulary/recognize` ✓
- `/api/v1/vocabulary` + `/words/batch` = `/api/v1/vocabulary/words/batch` ✓
- `/api/v1/vocabulary` + `/words/{id}` = `/api/v1/vocabulary/words/{id}` ✓
- `/api/v1/vocabulary` + `/review/queue` = `/api/v1/vocabulary/review/queue` ✓
- `/api/v1/vocabulary` + `/words/{id}/review` = `/api/v1/vocabulary/words/{id}/review` ✓

- [ ] **Step 6: 提交**

```bash
cd /Users/zhangfang/deepalpha-club-ai
git add ios/WordLens/Models/ ios/WordLens/Networking/AuthService.swift ios/WordLens/Networking/WordService.swift
git commit -m "feat(ios-wordlens): 数据模型 + Auth/Word Service"
```

---

### Task 4: AuthViewModel + 登录/注册页面 + RootView

**Files:**
- Create: `ios/WordLens/ViewModels/AuthViewModel.swift`
- Create: `ios/WordLens/Views/LoginView.swift`
- Create: `ios/WordLens/Views/RegisterView.swift`
- Create: `ios/WordLens/Views/RootView.swift`

- [ ] **Step 1: 创建 `ViewModels/AuthViewModel.swift`**

```swift
// ViewModels/AuthViewModel.swift
import Foundation

@MainActor
final class AuthViewModel: ObservableObject {
    @Published var isAuthenticated: Bool
    @Published var isLoading = false
    @Published var errorMessage: String?

    init() {
        self.isAuthenticated = KeychainStore.loadToken() != nil
    }

    func register(email: String, password: String) async {
        guard !email.isEmpty, !password.isEmpty else {
            errorMessage = "请输入邮箱和密码"
            return
        }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let resp = try await AuthService.register(email: email, password: password)
            KeychainStore.saveToken(resp.accessToken)
            isAuthenticated = true
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "注册失败，请稍后再试"
        }
    }

    func login(email: String, password: String) async {
        guard !email.isEmpty, !password.isEmpty else {
            errorMessage = "请输入邮箱和密码"
            return
        }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let resp = try await AuthService.login(email: email, password: password)
            KeychainStore.saveToken(resp.accessToken)
            isAuthenticated = true
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "登录失败，请稍后再试"
        }
    }

    func logout() {
        KeychainStore.clearToken()
        isAuthenticated = false
    }
}
```

- [ ] **Step 2: 创建 `Views/LoginView.swift`**

```swift
// Views/LoginView.swift
import SwiftUI

struct LoginView: View {
    @EnvironmentObject var auth: AuthViewModel
    @State private var email = ""
    @State private var password = ""
    @State private var showRegister = false
    @FocusState private var focused: Field?

    private enum Field { case email, password }

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            VStack(spacing: 24) {
                Spacer()
                VStack(spacing: 8) {
                    Text("WordLens")
                        .font(.system(size: 32, weight: .bold))
                        .foregroundColor(Theme.textPrimary)
                    Text("拍照背单词")
                        .font(.subheadline)
                        .foregroundColor(Theme.textSecondary)
                }

                VStack(spacing: 12) {
                    field("邮箱", text: $email, keyboard: .emailAddress)
                        .focused($focused, equals: .email)
                    secureField("密码", text: $password)
                        .focused($focused, equals: .password)
                }

                if let errorMessage = auth.errorMessage {
                    Text(errorMessage)
                        .font(.footnote)
                        .foregroundColor(Theme.unknown)
                }

                Button {
                    focused = nil
                    Task { await auth.login(email: email, password: password) }
                } label: {
                    HStack {
                        if auth.isLoading { ProgressView().tint(.white) }
                        Text(auth.isLoading ? "登录中…" : "登录").fontWeight(.semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(Theme.accent)
                    .foregroundColor(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                }
                .disabled(auth.isLoading)

                Button("还没有账号？去注册") { showRegister = true }
                    .font(.footnote)
                    .foregroundColor(Theme.textSecondary)

                Spacer()
                Spacer()
            }
            .padding(24)
        }
        .sheet(isPresented: $showRegister) { RegisterView() }
    }

    private func field(_ placeholder: String, text: Binding<String>, keyboard: UIKeyboardType) -> some View {
        TextField(placeholder, text: text)
            .keyboardType(keyboard)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .padding()
            .background(Theme.surface)
            .foregroundColor(Theme.textPrimary)
            .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func secureField(_ placeholder: String, text: Binding<String>) -> some View {
        SecureField(placeholder, text: text)
            .padding()
            .background(Theme.surface)
            .foregroundColor(Theme.textPrimary)
            .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}
```

- [ ] **Step 3: 创建 `Views/RegisterView.swift`**

密码强度规则跟后端 `validate_password_strength` 对齐（≥8 位、大写、小写、数字、特殊字符）：

```swift
// Views/RegisterView.swift
import SwiftUI

struct RegisterView: View {
    @EnvironmentObject var auth: AuthViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var email = ""
    @State private var password = ""
    @State private var confirmPassword = ""

    private var hasUpper: Bool { password.contains { $0.isUppercase } }
    private var hasLower: Bool { password.contains { $0.isLowercase } }
    private var hasDigit: Bool { password.contains { $0.isNumber } }
    private var hasSpecial: Bool { password.contains { "!@#$%^&*()_+-=[]{}|;:,.<>?".contains($0) } }
    private var longEnough: Bool { password.count >= 8 }
    private var matched: Bool { !password.isEmpty && password == confirmPassword }

    private var canSubmit: Bool {
        !email.isEmpty && hasUpper && hasLower && hasDigit && hasSpecial && longEnough && matched
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                ScrollView {
                    VStack(spacing: 16) {
                        TextField("邮箱", text: $email)
                            .keyboardType(.emailAddress)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .padding()
                            .background(Theme.surface)
                            .foregroundColor(Theme.textPrimary)
                            .clipShape(RoundedRectangle(cornerRadius: 10))

                        SecureField("密码", text: $password)
                            .padding()
                            .background(Theme.surface)
                            .foregroundColor(Theme.textPrimary)
                            .clipShape(RoundedRectangle(cornerRadius: 10))

                        SecureField("确认密码", text: $confirmPassword)
                            .padding()
                            .background(Theme.surface)
                            .foregroundColor(Theme.textPrimary)
                            .clipShape(RoundedRectangle(cornerRadius: 10))

                        VStack(alignment: .leading, spacing: 6) {
                            checklistRow("至少 8 个字符", longEnough)
                            checklistRow("包含大写字母", hasUpper)
                            checklistRow("包含小写字母", hasLower)
                            checklistRow("包含数字", hasDigit)
                            checklistRow("包含特殊字符（如 !@#$%）", hasSpecial)
                            checklistRow("两次密码一致", matched)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)

                        if let errorMessage = auth.errorMessage {
                            Text(errorMessage)
                                .font(.footnote)
                                .foregroundColor(Theme.unknown)
                        }

                        Button {
                            Task {
                                await auth.register(email: email, password: password)
                                if auth.isAuthenticated { dismiss() }
                            }
                        } label: {
                            HStack {
                                if auth.isLoading { ProgressView().tint(.white) }
                                Text(auth.isLoading ? "注册中…" : "注册").fontWeight(.semibold)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 14)
                            .background(canSubmit ? Theme.accent : Theme.surfaceAlt)
                            .foregroundColor(.white)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                        .disabled(!canSubmit || auth.isLoading)
                    }
                    .padding(24)
                }
            }
            .navigationTitle("注册")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private func checklistRow(_ text: String, _ satisfied: Bool) -> some View {
        HStack(spacing: 6) {
            Image(systemName: satisfied ? "checkmark.circle.fill" : "circle")
                .foregroundColor(satisfied ? Theme.known : Theme.textSecondary)
            Text(text)
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
        }
    }
}
```

- [ ] **Step 4: 创建 `Views/RootView.swift`**

```swift
// Views/RootView.swift
import SwiftUI

struct RootView: View {
    @EnvironmentObject var auth: AuthViewModel

    var body: some View {
        Group {
            if auth.isAuthenticated {
                MainTabView()
            } else {
                LoginView()
            }
        }
        .animation(.easeInOut, value: auth.isAuthenticated)
    }
}
```

- [ ] **Step 5: 走查代码**

- `AuthViewModel.register`/`login` 的错误处理跟 `catch let error as APIError` 模式一致，能拿到后端 422/401 的具体 `detail` 文案（比如密码强度不够、邮箱已被注册）
- `RegisterView` 的密码规则五项跟后端 `app/utils/sanitization.py` 的 `validate_password_strength` 逐条对应，不会出现「前端过了后端拒」的情况
- `RootView` 依赖 `MainTabView`，这是 Task 5 才创建的文件，这一步先写完，Xcode 里会有一个「找不到 MainTabView」的编译错误，等 Task 5 写完就没了（这是预期的中间状态，不用现在处理）

- [ ] **Step 6: 提交**

```bash
cd /Users/zhangfang/deepalpha-club-ai
git add ios/WordLens/ViewModels/AuthViewModel.swift ios/WordLens/Views/LoginView.swift ios/WordLens/Views/RegisterView.swift ios/WordLens/Views/RootView.swift
git commit -m "feat(ios-wordlens): 登录注册流程 + AuthViewModel"
```

---

### Task 5: App 入口 + 主 Tab 结构 + 首页

**Files:**
- Modify: `ios/WordLens/App/WordLensApp.swift`（整体替换）
- Create: `ios/WordLens/Views/MainTabView.swift`
- Create: `ios/WordLens/Views/HomeView.swift`

- [ ] **Step 1: 整体替换 `App/WordLensApp.swift`**

```swift
// App/WordLensApp.swift
import SwiftUI

@main
struct WordLensApp: App {
    @StateObject private var auth = AuthViewModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(auth)
                .tint(Theme.accent)
                .preferredColorScheme(.dark)
        }
    }
}
```

- [ ] **Step 2: 创建 `Views/MainTabView.swift`**

对应设计文档「Tab Bar 三栏」：生词库 / 拍照 / 复习。

```swift
// Views/MainTabView.swift
import SwiftUI

struct MainTabView: View {
    var body: some View {
        TabView {
            HomeView()
                .tabItem { Label("生词库", systemImage: "book.fill") }

            CameraCaptureView()
                .tabItem { Label("拍照", systemImage: "camera.fill") }

            ReviewCardView()
                .tabItem { Label("复习", systemImage: "arrow.triangle.2.circlepath") }
        }
        .tint(Theme.accent)
    }
}
```

- [ ] **Step 3: 创建 `Views/HomeView.swift`**

首页：今日待复习数 + 生词库统计入口 + 生词库列表跳转，对应设计文档 §6.2。

```swift
// Views/HomeView.swift
import SwiftUI

struct HomeView: View {
    @StateObject private var listVM = WordListViewModel()
    @State private var reviewDueCount = 0

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                ScrollView {
                    VStack(spacing: 20) {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("今日待复习：\(reviewDueCount) 个")
                                .font(.headline)
                                .foregroundColor(Theme.textPrimary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .background(Theme.surface)
                        .clipShape(RoundedRectangle(cornerRadius: 12))

                        statsRow

                        WordListView(viewModel: listVM)
                    }
                    .padding()
                }
            }
            .navigationTitle("WordLens")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    NavigationLink(destination: SettingsView()) {
                        Image(systemName: "gearshape")
                    }
                }
            }
            .task {
                await listVM.load()
                reviewDueCount = (try? await WordService.reviewQueue().count) ?? 0
            }
            .refreshable {
                await listVM.load()
                reviewDueCount = (try? await WordService.reviewQueue().count) ?? 0
            }
        }
    }

    private var statsRow: some View {
        let words = listVM.words
        let unknownCount = words.filter { $0.status == "new" }.count
        let fuzzyCount = words.filter { $0.status == "fuzzy" }.count
        let knownCount = words.filter { $0.status == "known" }.count
        return HStack(spacing: 16) {
            statTile("不认识", unknownCount, Theme.unknown)
            statTile("模糊", fuzzyCount, Theme.fuzzy)
            statTile("认识", knownCount, Theme.known)
        }
    }

    private func statTile(_ label: String, _ count: Int, _ color: Color) -> some View {
        VStack(spacing: 4) {
            Text("\(count)")
                .font(.title2.bold())
                .foregroundColor(color)
            Text(label)
                .font(.caption)
                .foregroundColor(Theme.textSecondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}
```

- [ ] **Step 4: 走查代码**

`HomeView` 依赖 `WordListViewModel`（Task 7 才创建）、`WordListView`（Task 7）、`SettingsView`（Task 9）、`CameraCaptureView`（Task 6）、`ReviewCardView`（Task 8）——这一步写完之后编译会有多处「找不到类型」，属于预期的中间状态，后续 Task 陆续补上就没了。

- [ ] **Step 5: 提交**

```bash
cd /Users/zhangfang/deepalpha-club-ai
git add ios/WordLens/App/WordLensApp.swift ios/WordLens/Views/MainTabView.swift ios/WordLens/Views/HomeView.swift
git commit -m "feat(ios-wordlens): App 入口 + 主 Tab 结构 + 首页"
```

---

### Task 6: 拍照识别流程

**Files:**
- Create: `ios/WordLens/ViewModels/CameraViewModel.swift`
- Create: `ios/WordLens/Views/CameraCaptureView.swift`
- Create: `ios/WordLens/Views/RecognizeResultView.swift`

- [ ] **Step 1: 创建 `ViewModels/CameraViewModel.swift`**

```swift
// ViewModels/CameraViewModel.swift
import Foundation
import SwiftUI

@MainActor
final class CameraViewModel: ObservableObject {
    @Published var isRecognizing = false
    @Published var errorMessage: String?
    @Published var candidates: [RecognizedWord] = []
    @Published var selectedWords: Set<String> = []
    @Published var showResult = false

    func recognize(imageData: Data) async {
        isRecognizing = true
        errorMessage = nil
        defer { isRecognizing = false }
        do {
            let resp = try await WordService.recognize(imageData: imageData)
            candidates = resp.candidates
            // 已在生词库中的默认不勾选，其余默认全选
            selectedWords = Set(resp.candidates.filter { !$0.alreadyInLibrary }.map { $0.word })
            showResult = true
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "识别失败，请重新拍摄"
        }
    }

    func toggle(_ word: String) {
        if selectedWords.contains(word) {
            selectedWords.remove(word)
        } else {
            selectedWords.insert(word)
        }
    }

    func addSelectedToLibrary() async -> (added: Int, skipped: [String]) {
        let toAdd = candidates
            .filter { selectedWords.contains($0.word) }
            .map { VocabularyWordCreate(word: $0.word, phoneticIpa: $0.phoneticIpa,
                                        partOfSpeech: $0.partOfSpeech, definitionZh: $0.definitionZh) }
        guard !toAdd.isEmpty else { return (0, []) }
        do {
            let resp = try await WordService.addWordsBatch(toAdd)
            reset()
            return (resp.created.count, resp.skippedExisting)
        } catch let error as APIError {
            errorMessage = error.message
            return (0, [])
        } catch {
            errorMessage = "加入生词库失败"
            return (0, [])
        }
    }

    func reset() {
        candidates = []
        selectedWords = []
        showResult = false
    }
}
```

- [ ] **Step 2: 创建 `Views/CameraCaptureView.swift`**

用 `PhotosPicker`（系统相册选图）+ `UIImagePickerController` 桥接（拍照）。为了 MVP 简单，先只做「从相册选图」，拍照按钮同样走系统相机（`UIImagePickerController` 的 `.camera` sourceType，用 `UIViewControllerRepresentable` 桥接）：

```swift
// Views/CameraCaptureView.swift
import SwiftUI
import PhotosUI
import UIKit

struct CameraCaptureView: View {
    @StateObject private var viewModel = CameraViewModel()
    @State private var photoPickerItem: PhotosPickerItem?
    @State private var showCameraSheet = false

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                VStack(spacing: 24) {
                    Spacer()

                    if viewModel.isRecognizing {
                        ProgressView("正在识别单词…")
                            .tint(Theme.accent)
                            .foregroundColor(Theme.textPrimary)
                    } else {
                        Image(systemName: "camera.viewfinder")
                            .font(.system(size: 64))
                            .foregroundColor(Theme.textSecondary)
                        Text("拍摄或选择含英语单词的图片")
                            .foregroundColor(Theme.textSecondary)
                    }

                    if let errorMessage = viewModel.errorMessage {
                        Text(errorMessage)
                            .font(.footnote)
                            .foregroundColor(Theme.unknown)
                    }

                    VStack(spacing: 12) {
                        Button {
                            showCameraSheet = true
                        } label: {
                            Label("拍照", systemImage: "camera.fill")
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 14)
                                .background(Theme.accent)
                                .foregroundColor(.white)
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                        .disabled(viewModel.isRecognizing)

                        PhotosPicker(selection: $photoPickerItem, matching: .images) {
                            Label("从相册选择", systemImage: "photo.on.rectangle")
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 14)
                                .background(Theme.surface)
                                .foregroundColor(Theme.textPrimary)
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                        .disabled(viewModel.isRecognizing)
                    }
                    .padding(.horizontal)

                    Spacer()
                    Spacer()
                }
            }
            .navigationTitle("拍照识词")
            .sheet(isPresented: $showCameraSheet) {
                CameraPicker { image in
                    guard let data = image.jpegData(compressionQuality: 0.8) else { return }
                    Task { await viewModel.recognize(imageData: data) }
                }
                .ignoresSafeArea()
            }
            .onChange(of: photoPickerItem) { _, newItem in
                guard let newItem else { return }
                Task {
                    guard let data = try? await newItem.loadTransferable(type: Data.self) else { return }
                    photoPickerItem = nil
                    await viewModel.recognize(imageData: data)
                }
            }
            .sheet(isPresented: $viewModel.showResult) {
                RecognizeResultView(viewModel: viewModel)
            }
        }
    }
}

/// 桥接系统相机（PhotosPicker 只能选相册，拍照要用 UIImagePickerController）。
/// 用完成回调而不是 @Binding<UIImage?> + onChange：UIImage 不遵循 Equatable，
/// iOS 17 的 onChange(of:) 要求值类型可比较，绑定 UIImage? 会直接编译报错。
private struct CameraPicker: UIViewControllerRepresentable {
    let onCapture: (UIImage) -> Void
    @Environment(\.dismiss) private var dismiss

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let parent: CameraPicker
        init(_ parent: CameraPicker) { self.parent = parent }

        func imagePickerController(_ picker: UIImagePickerController,
                                   didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let image = info[.originalImage] as? UIImage {
                parent.onCapture(image)
            }
            parent.dismiss()
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            parent.dismiss()
        }
    }
}
```

- [ ] **Step 3: 创建 `Views/RecognizeResultView.swift`**

对应设计文档 §6.3 候选词列表。

```swift
// Views/RecognizeResultView.swift
import SwiftUI

struct RecognizeResultView: View {
    @ObservedObject var viewModel: CameraViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var isSubmitting = false
    @State private var resultMessage: String?

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                if viewModel.candidates.isEmpty {
                    VStack(spacing: 12) {
                        Text("未识别到英语单词")
                            .foregroundColor(Theme.textSecondary)
                        Text("请重新拍摄，确保文字清晰")
                            .font(.caption)
                            .foregroundColor(Theme.textSecondary)
                    }
                } else {
                    List(viewModel.candidates) { candidate in
                        candidateRow(candidate)
                    }
                    .scrollContentBackground(.hidden)
                }

                if let resultMessage {
                    VStack {
                        Spacer()
                        Text(resultMessage)
                            .padding()
                            .background(Theme.surfaceAlt)
                            .foregroundColor(Theme.textPrimary)
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                            .padding(.bottom, 100)
                    }
                }
            }
            .navigationTitle("识别结果")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("取消") {
                        viewModel.reset()
                        dismiss()
                    }
                }
            }
            .safeAreaInset(edge: .bottom) {
                if !viewModel.candidates.isEmpty {
                    Button {
                        Task {
                            isSubmitting = true
                            let (added, skipped) = await viewModel.addSelectedToLibrary()
                            isSubmitting = false
                            if added > 0 || !skipped.isEmpty {
                                resultMessage = "加入 \(added) 个单词" + (skipped.isEmpty ? "" : "，\(skipped.count) 个已存在")
                                try? await Task.sleep(for: .seconds(1.2))
                                dismiss()
                            }
                        }
                    } label: {
                        HStack {
                            if isSubmitting { ProgressView().tint(.white) }
                            Text("加入生词库 (\(viewModel.selectedWords.count))")
                                .fontWeight(.semibold)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(viewModel.selectedWords.isEmpty ? Theme.surfaceAlt : Theme.accent)
                        .foregroundColor(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                    .disabled(viewModel.selectedWords.isEmpty || isSubmitting)
                    .padding()
                    .background(Theme.background)
                }
            }
        }
    }

    private func candidateRow(_ candidate: RecognizedWord) -> some View {
        HStack {
            Button {
                viewModel.toggle(candidate.word)
            } label: {
                Image(systemName: viewModel.selectedWords.contains(candidate.word) ? "checkmark.square.fill" : "square")
                    .foregroundColor(viewModel.selectedWords.contains(candidate.word) ? Theme.accent : Theme.textSecondary)
            }
            .buttonStyle(.plain)

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(candidate.word).fontWeight(.semibold)
                    PronounceButton(word: candidate.word)
                    Text("/\(candidate.phoneticIpa)/")
                        .font(.caption)
                        .foregroundColor(Theme.textSecondary)
                }
                Text("\(candidate.partOfSpeech) \(candidate.definitionZh)")
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                if candidate.alreadyInLibrary {
                    Text("已在生词库中")
                        .font(.caption2)
                        .foregroundColor(Theme.textSecondary)
                }
            }
            Spacer()
        }
        .listRowBackground(Theme.surface)
        .foregroundColor(Theme.textPrimary)
    }
}
```

- [ ] **Step 4: 走查代码**

- `CameraPicker` 用 `UIImagePickerController` 桥接系统相机，`sourceType = .camera` 在没有摄像头的模拟器上会崩溃/不可用——**必须用真机测试拍照功能**，模拟器测试时用「从相册选择」这条路径（模拟器相册可以从 Mac 拖图片进去）
- `RecognizeResultView` 依赖 `PronounceButton`（Task 8 才创建），这一步先写完，等 Task 8 补上
- `candidate.alreadyInLibrary` 为 true 的候选词默认不勾选（`CameraViewModel.recognize` 里已处理），但仍然可以手动勾选加入——如果用户手动勾选一个「已在库中」的词，提交后端会在 `skipped_existing` 里返回，`resultMessage` 会如实提示

- [ ] **Step 5: 提交**

```bash
cd /Users/zhangfang/deepalpha-club-ai
git add ios/WordLens/ViewModels/CameraViewModel.swift ios/WordLens/Views/CameraCaptureView.swift ios/WordLens/Views/RecognizeResultView.swift
git commit -m "feat(ios-wordlens): 拍照识别流程"
```

---

### Task 7: 生词库列表 + 详情

**Files:**
- Create: `ios/WordLens/ViewModels/WordListViewModel.swift`
- Create: `ios/WordLens/Views/WordListView.swift`
- Create: `ios/WordLens/Views/WordDetailView.swift`

- [ ] **Step 1: 创建 `ViewModels/WordListViewModel.swift`**

```swift
// ViewModels/WordListViewModel.swift
import Foundation

@MainActor
final class WordListViewModel: ObservableObject {
    @Published var words: [VocabularyWord] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var filterStatus: String?
    @Published var searchQuery = ""

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            words = try await WordService.listWords(status: filterStatus, query: searchQuery)
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "加载生词库失败"
        }
    }

    func delete(_ word: VocabularyWord) async {
        do {
            try await WordService.deleteWord(id: word.id)
            words.removeAll { $0.id == word.id }
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "删除失败"
        }
    }
}
```

- [ ] **Step 2: 创建 `Views/WordListView.swift`**

对应设计文档 §6.4，支持状态筛选 + 搜索。这个 View 被 `HomeView` 内嵌使用（传入共享的 `WordListViewModel`），所以不自带 `NavigationStack`。

```swift
// Views/WordListView.swift
import SwiftUI

struct WordListView: View {
    @ObservedObject var viewModel: WordListViewModel

    private let filters: [(label: String, value: String?)] = [
        ("全部", nil), ("不认识", "new"), ("模糊", "fuzzy"), ("认识", "known"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("生词库").font(.headline).foregroundColor(Theme.textPrimary)
                Spacer()
            }

            TextField("搜索单词", text: $viewModel.searchQuery)
                .padding(10)
                .background(Theme.surface)
                .foregroundColor(Theme.textPrimary)
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .onSubmit { Task { await viewModel.load() } }

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(filters, id: \.label) { filter in
                        filterChip(filter.label, filter.value)
                    }
                }
            }

            if viewModel.isLoading {
                ProgressView().tint(Theme.accent).frame(maxWidth: .infinity)
            } else if viewModel.words.isEmpty {
                Text("暂无生词，去拍照识别一些吧").font(.caption).foregroundColor(Theme.textSecondary)
            } else {
                ForEach(viewModel.words) { word in
                    NavigationLink(destination: WordDetailView(word: word, listViewModel: viewModel)) {
                        wordRow(word)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private func filterChip(_ label: String, _ value: String?) -> some View {
        Button {
            viewModel.filterStatus = value
            Task { await viewModel.load() }
        } label: {
            Text(label)
                .font(.caption)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(viewModel.filterStatus == value ? Theme.accent : Theme.surface)
                .foregroundColor(viewModel.filterStatus == value ? .white : Theme.textSecondary)
                .clipShape(Capsule())
        }
    }

    private func wordRow(_ word: VocabularyWord) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(word.word).fontWeight(.semibold).foregroundColor(Theme.textPrimary)
                Text("/\(word.phoneticIpa)/ \(word.definitionZh)")
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                    .lineLimit(1)
            }
            Spacer()
            statusDot(word.status)
        }
        .padding()
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func statusDot(_ status: String) -> some View {
        let (color, label): (Color, String) = {
            switch status {
            case "known": return (Theme.known, "认识")
            case "fuzzy": return (Theme.fuzzy, "模糊")
            default: return (Theme.unknown, "不认识")
            }
        }()
        return HStack(spacing: 4) {
            Circle().fill(color).frame(width: 8, height: 8)
            Text(label).font(.caption2).foregroundColor(Theme.textSecondary)
        }
    }
}
```

- [ ] **Step 3: 创建 `Views/WordDetailView.swift`**

```swift
// Views/WordDetailView.swift
import SwiftUI

struct WordDetailView: View {
    let word: VocabularyWord
    @ObservedObject var listViewModel: WordListViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var showDeleteConfirm = false

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            VStack(spacing: 20) {
                VStack(spacing: 8) {
                    HStack {
                        Text(word.word).font(.largeTitle.bold()).foregroundColor(Theme.textPrimary)
                        PronounceButton(word: word.word)
                    }
                    Text("/\(word.phoneticIpa)/").foregroundColor(Theme.textSecondary)
                    Text("\(word.partOfSpeech) \(word.definitionZh)")
                        .foregroundColor(Theme.textPrimary)
                        .multilineTextAlignment(.center)
                }
                .padding()

                VStack(alignment: .leading, spacing: 8) {
                    detailRow("状态", statusLabel)
                    detailRow("连续认识次数", "\(word.repetitionCount)")
                    detailRow("复习间隔", "\(word.intervalDays) 天")
                    detailRow("下次复习", word.nextReviewAt)
                }
                .padding()
                .background(Theme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 12))

                Spacer()

                Button(role: .destructive) {
                    showDeleteConfirm = true
                } label: {
                    Text("删除单词")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Theme.surface)
                        .foregroundColor(Theme.unknown)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                }
            }
            .padding()
        }
        .navigationTitle("单词详情")
        .navigationBarTitleDisplayMode(.inline)
        .confirmationDialog("确定删除「\(word.word)」吗？", isPresented: $showDeleteConfirm, titleVisibility: .visible) {
            Button("删除", role: .destructive) {
                Task {
                    await listViewModel.delete(word)
                    dismiss()
                }
            }
            Button("取消", role: .cancel) {}
        }
    }

    private var statusLabel: String {
        switch word.status {
        case "known": return "认识"
        case "fuzzy": return "模糊"
        default: return "不认识"
        }
    }

    private func detailRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).foregroundColor(Theme.textSecondary)
            Spacer()
            Text(value).foregroundColor(Theme.textPrimary)
        }
        .font(.subheadline)
    }
}
```

- [ ] **Step 4: 走查代码**

- `WordListView` 依赖 `WordDetailView`、`PronounceButton`（Task 8）——`WordDetailView` 本身这一步已创建，`PronounceButton` 还没有，编译会报错，等 Task 8 补上
- `WordListView` 用 `@ObservedObject`（不是 `@StateObject`）因为它接收 `HomeView` 传入的共享实例，不自己创建，避免和首页统计数据不同步
- `word.nextReviewAt` 直接显示后端返回的 ISO 8601 字符串（如 `2026-07-26T08:09:11.390968`），MVP 先不做日期格式化美化

- [ ] **Step 5: 提交**

```bash
cd /Users/zhangfang/deepalpha-club-ai
git add ios/WordLens/ViewModels/WordListViewModel.swift ios/WordLens/Views/WordListView.swift ios/WordLens/Views/WordDetailView.swift
git commit -m "feat(ios-wordlens): 生词库列表 + 详情"
```

---

### Task 8: 复习流程 + 发音组件

**Files:**
- Create: `ios/WordLens/Views/Components/PronounceButton.swift`
- Create: `ios/WordLens/ViewModels/ReviewViewModel.swift`
- Create: `ios/WordLens/Views/ReviewCardView.swift`

- [ ] **Step 1: 创建 `Views/Components/PronounceButton.swift`**

对应设计文档「发音」章节：系统 TTS，默认美式，可在设置里切换英式（读取 `UserDefaults`）。

```swift
// Views/Components/PronounceButton.swift
import SwiftUI
import AVFoundation

/// 发音偏好（存 UserDefaults，设置页可切换）。
enum PronunciationAccent: String {
    case american = "en-US"
    case british = "en-GB"

    static var current: PronunciationAccent {
        get {
            let raw = UserDefaults.standard.string(forKey: "pronunciation_accent") ?? american.rawValue
            return PronunciationAccent(rawValue: raw) ?? .american
        }
        set {
            UserDefaults.standard.set(newValue.rawValue, forKey: "pronunciation_accent")
        }
    }
}

/// 单例合成器，避免每次点击都新建（新建会打断上一次朗读）。
private enum Speaker {
    static let synthesizer = AVSpeechSynthesizer()
}

struct PronounceButton: View {
    let word: String

    var body: some View {
        Button {
            speak()
        } label: {
            Image(systemName: "speaker.wave.2.fill")
                .foregroundColor(Theme.accent)
        }
        .buttonStyle(.plain)
    }

    private func speak() {
        let utterance = AVSpeechUtterance(string: word)
        utterance.voice = AVSpeechSynthesisVoice(language: PronunciationAccent.current.rawValue)
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate
        Speaker.synthesizer.stopSpeaking(at: .immediate)
        Speaker.synthesizer.speak(utterance)
    }
}
```

- [ ] **Step 2: 创建 `ViewModels/ReviewViewModel.swift`**

```swift
// ViewModels/ReviewViewModel.swift
import Foundation

@MainActor
final class ReviewViewModel: ObservableObject {
    @Published var queue: [VocabularyWord] = []
    @Published var currentIndex = 0
    @Published var isFlipped = false
    @Published var isLoading = false
    @Published var isSubmitting = false
    @Published var errorMessage: String?
    @Published var totalCount = 0

    var currentWord: VocabularyWord? {
        guard currentIndex < queue.count else { return nil }
        return queue[currentIndex]
    }

    var isFinished: Bool { !queue.isEmpty && currentIndex >= queue.count }

    func loadQueue() async {
        isLoading = true
        errorMessage = nil
        currentIndex = 0
        isFlipped = false
        defer { isLoading = false }
        do {
            queue = try await WordService.reviewQueue()
            totalCount = queue.count
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "加载复习队列失败"
        }
    }

    func flip() {
        isFlipped.toggle()
    }

    func submit(_ rating: ReviewRating) async {
        guard let word = currentWord else { return }
        isSubmitting = true
        defer { isSubmitting = false }
        do {
            _ = try await WordService.submitReview(wordId: word.id, rating: rating)
            currentIndex += 1
            isFlipped = false
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = "提交复习结果失败"
        }
    }
}
```

- [ ] **Step 3: 创建 `Views/ReviewCardView.swift`**

对应设计文档 §6.5 复习卡片流。

```swift
// Views/ReviewCardView.swift
import SwiftUI

struct ReviewCardView: View {
    @StateObject private var viewModel = ReviewViewModel()

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()

                if viewModel.isLoading {
                    ProgressView().tint(Theme.accent)
                } else if viewModel.queue.isEmpty {
                    emptyState(title: "今天没有待复习的单词", subtitle: "去拍照识别一些新单词吧")
                } else if viewModel.isFinished {
                    emptyState(title: "今日复习完成 🎉", subtitle: "共复习了 \(viewModel.totalCount) 个单词")
                } else if let word = viewModel.currentWord {
                    cardContent(word)
                }
            }
            .navigationTitle("复习")
            .navigationBarTitleDisplayMode(.inline)
            .task { await viewModel.loadQueue() }
            .refreshable { await viewModel.loadQueue() }
        }
    }

    private func emptyState(title: String, subtitle: String) -> some View {
        VStack(spacing: 8) {
            Text(title).font(.headline).foregroundColor(Theme.textPrimary)
            Text(subtitle).font(.caption).foregroundColor(Theme.textSecondary)
        }
    }

    private func cardContent(_ word: VocabularyWord) -> some View {
        VStack(spacing: 24) {
            Text("\(viewModel.currentIndex + 1) / \(viewModel.totalCount)")
                .font(.caption)
                .foregroundColor(Theme.textSecondary)

            Spacer()

            VStack(spacing: 16) {
                HStack {
                    Text(word.word).font(.system(size: 36, weight: .bold)).foregroundColor(Theme.textPrimary)
                    PronounceButton(word: word.word)
                }
                Text("/\(word.phoneticIpa)/").foregroundColor(Theme.textSecondary)

                if viewModel.isFlipped {
                    Text("\(word.partOfSpeech) \(word.definitionZh)")
                        .font(.title3)
                        .foregroundColor(Theme.textPrimary)
                        .multilineTextAlignment(.center)
                        .padding(.top, 8)
                } else {
                    Text("点击翻转看释义")
                        .font(.caption)
                        .foregroundColor(Theme.textSecondary)
                }
            }
            .frame(maxWidth: .infinity)
            .frame(minHeight: 220)
            .background(Theme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .onTapGesture { viewModel.flip() }
            .padding(.horizontal)

            Spacer()

            if let errorMessage = viewModel.errorMessage {
                Text(errorMessage).font(.footnote).foregroundColor(Theme.unknown)
            }

            if viewModel.isFlipped {
                HStack(spacing: 12) {
                    ratingButton("😵 不认识", Theme.unknown, .unknown)
                    ratingButton("😐 模糊", Theme.fuzzy, .fuzzy)
                    ratingButton("😊 认识", Theme.known, .known)
                }
                .padding(.horizontal)
                .padding(.bottom, 24)
            }
        }
    }

    private func ratingButton(_ label: String, _ color: Color, _ rating: ReviewRating) -> some View {
        Button {
            Task { await viewModel.submit(rating) }
        } label: {
            Text(label)
                .font(.footnote.weight(.semibold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                .background(color.opacity(0.2))
                .foregroundColor(color)
                .clipShape(RoundedRectangle(cornerRadius: 10))
        }
        .disabled(viewModel.isSubmitting)
    }
}
```

- [ ] **Step 4: 走查代码**

- `PronounceButton` 用的 `AVSpeechSynthesisVoice(language:)` 传 `"en-US"`/`"en-GB"` 是标准 BCP-47 locale 写法，系统一定内置这两种美式/英式声音，不需要额外下载语音包
- `ReviewCardView` 的翻卡片用简单的条件渲染（`if viewModel.isFlipped`），没做 3D 翻转动画，MVP 阶段先满足功能，动画效果后续可以加 `.rotation3DEffect` 优化，不在这次计划范围内
- 现在所有 View 之间的依赖应该都补全了：`HomeView`→`WordListView`/`SettingsView`（Task 9）、`CameraCaptureView`→`RecognizeResultView`→`PronounceButton`（已补）、`WordDetailView`→`PronounceButton`（已补）、`MainTabView`→`ReviewCardView`（已补）。唯一还缺的是 `SettingsView`（Task 9）

- [ ] **Step 5: 提交**

```bash
cd /Users/zhangfang/deepalpha-club-ai
git add ios/WordLens/Views/Components/PronounceButton.swift ios/WordLens/ViewModels/ReviewViewModel.swift ios/WordLens/Views/ReviewCardView.swift
git commit -m "feat(ios-wordlens): 复习流程 + 发音组件"
```

---

### Task 9: 设置页

**Files:**
- Create: `ios/WordLens/Views/SettingsView.swift`

- [ ] **Step 1: 创建 `Views/SettingsView.swift`**

发音口音切换（读写 `PronunciationAccent.current`，Task 8 已定义）+ 登出。

```swift
// Views/SettingsView.swift
import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var auth: AuthViewModel
    @State private var accent: PronunciationAccent = PronunciationAccent.current

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            Form {
                Section("发音口音") {
                    Picker("口音", selection: $accent) {
                        Text("美式").tag(PronunciationAccent.american)
                        Text("英式").tag(PronunciationAccent.british)
                    }
                    .pickerStyle(.segmented)
                    .onChange(of: accent) { _, newValue in
                        PronunciationAccent.current = newValue
                    }
                }
                .listRowBackground(Theme.surface)

                Section {
                    Button("退出登录", role: .destructive) {
                        auth.logout()
                    }
                }
                .listRowBackground(Theme.surface)
            }
            .scrollContentBackground(.hidden)
        }
        .navigationTitle("设置")
        .navigationBarTitleDisplayMode(.inline)
    }
}
```

- [ ] **Step 2: 走查代码**

`PronunciationAccent` 需要遵循 `Hashable`（`Picker` 的 `selection` 要求），它是基于 `String` 的 `enum` 且有 `RawValue`，Swift 会自动合成 `Hashable`（`RawRepresentable` + `Equatable` 场景下，只要没有关联值的 enum 默认就是 `Hashable`），不需要额外声明。

- [ ] **Step 3: 提交**

```bash
cd /Users/zhangfang/deepalpha-club-ai
git add ios/WordLens/Views/SettingsView.swift
git commit -m "feat(ios-wordlens): 设置页（口音切换 + 登出）"
```

---

### Task 10: 补齐 `.gitignore` 排除项（如需要）

**Files:**
- Modify: `.gitignore`（如果 `ios/DeepAlphaChan` 已有对应规则，这一步大概率什么都不用做）

- [ ] **Step 1: 检查是否需要新增忽略规则**

Run: `grep -n "xcuserdata\|DerivedData\|\.xcworkspace" .gitignore`

Expected: 应该已经有 `ios/DeepAlphaChan.xcodeproj/xcuserdata/` 之类的规则覆盖所有 `.xcodeproj`（比如通配符 `**/xcuserdata/`）。如果规则是精确匹配 `DeepAlphaChan` 路径而不是通配符，需要给 `WordLens.xcodeproj` 也加一条一样的规则。

- [ ] **Step 2: 如需要，补充规则并提交**

如果 Step 1 发现规则不是通配符、需要新增，编辑 `.gitignore` 加对应行，然后：

```bash
cd /Users/zhangfang/deepalpha-club-ai
git add .gitignore
git commit -m "chore(ios-wordlens): 补充 WordLens.xcodeproj 的 gitignore 规则"
```

如果 Step 1 发现已经是通配符规则，不用做任何改动，直接跳到 Task 11。

---

### Task 11: 在 Xcode 里编译 + 真机/模拟器全流程验证（用户手动操作）

这一步在你自己的 Mac 上做，之前所有 Task 写的代码在这里第一次真正编译。

- [ ] **Step 1: 起后端**

```bash
cd /Users/zhangfang/deepalpha-club-ai
make dev
```

确认输出里 uvicorn 监听的是 `0.0.0.0:8000`（不是 `127.0.0.1:8000`，否则手机连不上）。如果 `make dev` 默认绑定 `127.0.0.1`，改成 `uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` 手动起。

- [ ] **Step 2: 确认手机能连到 Mac**

在 Mac 终端跑 `ipconfig getifaddr en0`，跟 `AppConfig.swift` 里的 `baseURL` 对一下，不一致就改 `AppConfig.swift` 里的 IP。手机和 Mac 连同一个 WiFi（不是手机热点给 Mac 用，要是同一个路由器/AP）。

- [ ] **Step 3: 打开工程编译**

双击 `ios/WordLens.xcodeproj`，选一个 iOS 17+ 的真机（拍照功能需要真机，模拟器没摄像头）或模拟器（只能测「从相册选择」路径），`Cmd + B` 编译。

**如果编译报错**：把报错信息记下来，这是本计划第一次真正验证代码正确性的时刻，出编译错误是正常的（比如个别 SwiftUI API 在你的 Xcode 版本上签名不同、某个类型推断失败需要显式标注等）。逐个修复后回到这一步重新编译，直到 Build Succeeded。

- [ ] **Step 4: 真机跑通完整流程**

用真机（`Cmd + R`），依次验证：

1. **注册**：新邮箱+符合强度要求的密码，提示"注册中"→跳转主界面
2. **拍照**：点「拍照」Tab → 拍一张含英文单词的书页/文档 → 等几秒出现候选词列表（带音标和中文释义）
3. **加入生词库**：勾选几个词 →「加入生词库」→ 提示成功
4. **生词库列表**：回到首页，能看到刚加入的词，状态显示「不认识」
5. **复习**：点「复习」Tab，能看到刚加入的词（因为 `next_review_at` 是立即到期），点卡片翻转看释义，点喇叭听发音，点「认识」提交
6. **单词详情**：从生词库点进单词详情，看到复习间隔已经更新（应该变成 1 天后）
7. **删除**：详情页删除这个单词，确认从列表消失
8. **设置**：切换英式/美式发音，回到复习或详情页点喇叭确认口音变化；点「退出登录」确认回到登录页

- [ ] **Step 5: 记录问题**

如果第 4 步任何一环出问题（网络报错、UI 显示不对、崩溃），记录具体现象（哪个操作、什么报错/截图），这些问题回来一起修，不需要现在就返回给我处理——除非你想让我现在就基于这些报错继续调试。
