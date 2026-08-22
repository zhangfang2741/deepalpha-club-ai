# 缠论手机号/邮箱双通道认证——iOS 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 缠论 iOS App 支持手机号/邮箱双通道验证码注册、统一账号登录、找回密码，登录页增加「保持登录」勾选。

**Architecture:** 把 `AuthService` 从 `ChanService.swift` 拆出独立文件并补齐九个新端点；三个认证页面共用一组抽出来的输入控件；账号格式判别抽成纯逻辑 struct 便于复核。`AuthViewModel` 用 `@AppStorage` 持有 `rememberMe`，未勾选时启动即清 Keychain。

**Tech Stack:** SwiftUI、Swift Concurrency、URLSession（`APIClient` actor）、Keychain。

**依赖：** `docs/superpowers/plans/2026-08-22-chan-auth-backend.md` 必须先完成并合入——本计划对接的九个端点由它提供。

**设计文档：** `docs/superpowers/specs/2026-08-22-chan-auth-phone-email-design.md`

---

## 两个前置事实

**新增 Swift 文件不用改 pbxproj。** 项目用的是 Xcode 16 的
`PBXFileSystemSynchronizedRootGroup`（`ios/DeepAlphaChan.xcodeproj/project.pbxproj:24`），
`ios/DeepAlphaChan/` 目录下的文件自动纳入编译。

**这个 target 没有 XCTest。** `ios/Tests/` 是 WordLens 听写评测用的独立脚本，不是测试
target。所以本计划无法做真正的 TDD：验证手段是 `xcodebuild` 编译通过 + 明确的手工
测试矩阵（Task 8）。可测的纯逻辑抽成了 `AccountInput`，将来补测试 target 时可直接覆盖。

---

## 文件结构

**新建**

| 文件 | 职责 |
|------|------|
| `ios/DeepAlphaChan/Networking/AuthService.swift` | 认证接口封装（从 ChanService.swift 迁出 + 九个新端点） |
| `ios/DeepAlphaChan/Models/AccountInput.swift` | 账号通道枚举 + 本地格式预校验（纯逻辑，无 UI 依赖） |
| `ios/DeepAlphaChan/Views/Components/AuthFields.swift` | 三个认证页共用的输入控件 + 带倒计时的获取验证码按钮 |
| `ios/DeepAlphaChan/Views/ForgotPasswordView.swift` | 找回密码页 |

**改造**

| 文件 | 改动 |
|------|------|
| `ios/DeepAlphaChan/Networking/ChanService.swift` | 移除 `AuthService`（迁到新文件） |
| `ios/DeepAlphaChan/Models/AuthModels.swift` | email 改可空、加 phone、新增请求/响应模型 |
| `ios/DeepAlphaChan/ViewModels/AuthViewModel.swift` | rememberMe + 六个新方法 |
| `ios/DeepAlphaChan/Views/LoginView.swift` | 通道切换、保持登录勾选、忘记密码入口 |
| `ios/DeepAlphaChan/Views/RegisterView.swift` | 通道切换、验证码输入 |
| `ios/DeepAlphaChan/Views/ProfileView.swift` | email 可空后的展示 |

---

### Task 1: 账号输入的纯逻辑

先做这一层，因为它不依赖任何 UI，且后面三个页面都要用。

**Files:**
- Create: `ios/DeepAlphaChan/Models/AccountInput.swift`

- [ ] **Step 1: 创建文件**

```swift
import Foundation

/// 注册/登录的账号通道。
enum AccountChannel: String, CaseIterable, Identifiable {
    case phone
    case email

    var id: String { rawValue }

    var title: String {
        switch self {
        case .phone: return "手机号"
        case .email: return "邮箱"
        }
    }

    var placeholder: String {
        switch self {
        case .phone: return "手机号"
        case .email: return "邮箱"
        }
    }

    var icon: String {
        switch self {
        case .phone: return "iphone"
        case .email: return "envelope"
        }
    }
}

/// 账号输入的本地预校验。
///
/// 只做「明显不合法就别发请求」这一层，权威判断在服务端——手机号归一化规则
/// （全角转半角、去分隔符、086 前缀等）比这里复杂得多，两边各写一份必然走偏。
/// 这里存在的意义是省掉一次注定失败的网络往返，并且能在用户还没点按钮时就
/// 把「获取验证码」置灰。
enum AccountInput {
    /// 中国大陆手机号：1 开头，第二位 3-9，共 11 位。与后端 utils/phone.py 的
    /// _CN_MOBILE 保持一致。
    static func isValidCNMobile(_ raw: String) -> Bool {
        let digits = raw.filter(\.isNumber)
        return digits.range(of: "^1[3-9]\\d{9}$", options: .regularExpression) != nil
    }

    /// 邮箱格式的宽松校验，与后端 sanitize_email 的正则同源。
    static func isValidEmail(_ raw: String) -> Bool {
        let text = raw.trimmingCharacters(in: .whitespaces)
        let pattern = "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
        return text.range(of: pattern, options: .regularExpression) != nil
    }

    static func isValid(_ raw: String, channel: AccountChannel) -> Bool {
        switch channel {
        case .phone: return isValidCNMobile(raw)
        case .email: return isValidEmail(raw)
        }
    }

    /// 6 位数字验证码。
    static func isValidCode(_ raw: String) -> Bool {
        raw.range(of: "^\\d{6}$", options: .regularExpression) != nil
    }
}

/// 密码强度规则。与后端 validate_password_strength 对齐：8–64 位，
/// 含大小写字母、数字、特殊字符。抽出来是因为注册页和找回密码页都要用，
/// 原本只在 RegisterView 里以私有计算属性存在。
struct PasswordRules {
    let password: String

    var hasUpper: Bool { password.range(of: "[A-Z]", options: .regularExpression) != nil }
    var hasLower: Bool { password.range(of: "[a-z]", options: .regularExpression) != nil }
    var hasDigit: Bool { password.range(of: "[0-9]", options: .regularExpression) != nil }
    var hasSpecial: Bool {
        password.range(of: "[!@#$%^&*(),.?\":{}|<>]", options: .regularExpression) != nil
    }
    var longEnough: Bool { password.count >= 8 && password.count <= 64 }

    var allSatisfied: Bool { hasUpper && hasLower && hasDigit && hasSpecial && longEnough }
}
```

- [ ] **Step 2: 编译**

Run:
```bash
cd /Users/zhangfang/deepalpha-club-ai/ios && xcodebuild -project DeepAlphaChan.xcodeproj -scheme DeepAlphaChan -destination 'generic/platform=iOS' build 2>&1 | tail -5
```
Expected: `** BUILD SUCCEEDED **`

- [ ] **Step 3: 提交**

```bash
git add ios/DeepAlphaChan/Models/AccountInput.swift
git commit -m "feat(ios/chan): 账号通道枚举与本地格式预校验"
```

---

### Task 2: 数据模型

**Files:**
- Modify: `ios/DeepAlphaChan/Models/AuthModels.swift`

- [ ] **Step 1: 改 UserProfile 与 RegisterResponse**

后端 `email` 已改为可空（手机号注册的用户没有邮箱），这两个模型不改会解码失败。

把 `AuthModels.swift` 里的 `RegisterResponse` 和 `UserProfile` 替换为：

```swift
/// 注册响应：对应带验证码的注册端点，含用户信息与嵌套 token。
/// email 与 phone 都可空——手机号注册的用户没有邮箱，反之亦然。
struct RegisterResponse: Codable {
    let id: Int
    let email: String?
    let phone: String?
    let username: String?
    let token: LoginResponse
}

/// 当前用户资料：对应 `GET /api/v1/auth/me`。
struct UserProfile: Codable, Identifiable {
    let id: Int
    let email: String?
    let phone: String?
    let username: String?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, email, phone, username
        case createdAt = "created_at"
    }

    /// 展示用的账号：优先邮箱，其次打码手机号。
    var displayAccount: String {
        if let email, !email.isEmpty { return email }
        if let phone, !phone.isEmpty { return Self.masked(phone) }
        return "—"
    }

    /// +8613800138000 → 138****8000。号码属于个人信息，界面上不必完整显示。
    static func masked(_ e164: String) -> String {
        let digits = e164.hasPrefix("+86") ? String(e164.dropFirst(3)) : e164
        guard digits.count >= 8 else { return digits }
        let head = digits.prefix(digits.count - 8)
        let tail = digits.suffix(4)
        return "\(head)\(digits.dropFirst(digits.count - 8).prefix(3))****\(tail)"
    }
}
```

- [ ] **Step 2: 追加新端点的请求/响应模型**

在 `AuthModels.swift` 末尾追加：

```swift
// MARK: - 双通道注册 / 登录 / 找回密码

/// 发码类接口的响应：`{"sent": true}`
struct SentResponse: Codable {
    let sent: Bool
}

/// 重置密码的响应：`{"reset": true}`
struct ResetResponse: Codable {
    let reset: Bool
}
```

- [ ] **Step 3: 编译**

Run:
```bash
cd /Users/zhangfang/deepalpha-club-ai/ios && xcodebuild -project DeepAlphaChan.xcodeproj -scheme DeepAlphaChan -destination 'generic/platform=iOS' build 2>&1 | tail -20
```
Expected: FAIL。`ProfileView.swift:19` 的 `row("邮箱", p.email)` 会因 `String?` 报错，
`AuthViewModel` 里构造 `UserProfile` 的地方也可能报错。这是预期的——Task 3 修。
记下报错文件清单。

- [ ] **Step 4: 修 ProfileView**

`ios/DeepAlphaChan/Views/ProfileView.swift:19` 把：

```swift
                        row("邮箱", p.email)
```

改为：

```swift
                        row("账号", p.displayAccount)
```

- [ ] **Step 5: 编译**

Run:
```bash
cd /Users/zhangfang/deepalpha-club-ai/ios && xcodebuild -project DeepAlphaChan.xcodeproj -scheme DeepAlphaChan -destination 'generic/platform=iOS' build 2>&1 | tail -5
```
Expected: `** BUILD SUCCEEDED **`。若还有别处引用 `profile.email`，按同样方式改成
`displayAccount`。

- [ ] **Step 6: 提交**

```bash
git add ios/DeepAlphaChan/Models/AuthModels.swift ios/DeepAlphaChan/Views/ProfileView.swift
git commit -m "feat(ios/chan): 用户模型支持可空邮箱与手机号"
```

---

### Task 3: AuthService 独立成文件并补齐端点

`AuthService` 目前挤在 `ChanService.swift` 里（缠论行情接口 + 认证接口同一个文件）。
再往里加九个方法，这个文件就成了两件不相干事情的合集。拆出来。

**Files:**
- Create: `ios/DeepAlphaChan/Networking/AuthService.swift`
- Modify: `ios/DeepAlphaChan/Networking/ChanService.swift`

- [ ] **Step 1: 新建 AuthService.swift**

```swift
import Foundation

/// 认证接口封装。
///
/// 从 ChanService.swift 拆出来：那个文件原本同时装着行情接口和认证接口，
/// 加上双通道注册后认证部分的体量已经超过行情部分。
enum AuthService {

    // MARK: - 登录

    /// 统一登录：account 可以是手机号或邮箱，由服务端判别。
    static func login(account: String, password: String) async throws -> LoginResponse {
        struct Body: Encodable {
            let account: String
            let password: String
        }
        return try await APIClient.shared.postJSON(
            "/auth/login/account", body: Body(account: account, password: password))
    }

    /// Sign in with Apple：把 Apple 身份令牌换成本平台 token。
    static func appleLogin(identityToken: String, fullName: String?) async throws -> LoginResponse {
        struct Body: Encodable {
            let identity_token: String
            let full_name: String?
        }
        return try await APIClient.shared.postJSON("/auth/apple", body: Body(
            identity_token: identityToken, full_name: fullName))
    }

    // MARK: - 注册

    /// 请求注册验证码。
    @discardableResult
    static func requestRegisterCode(account: String, channel: AccountChannel) async throws -> SentResponse {
        switch channel {
        case .email:
            struct Body: Encodable { let email: String }
            return try await APIClient.shared.postJSON(
                "/auth/register/request-code", body: Body(email: account))
        case .phone:
            struct Body: Encodable { let phone: String }
            return try await APIClient.shared.postJSON(
                "/auth/phone/register/request-code", body: Body(phone: account))
        }
    }

    /// 校验验证码并注册。
    static func register(
        account: String, channel: AccountChannel, code: String,
        password: String, username: String?
    ) async throws -> RegisterResponse {
        switch channel {
        case .email:
            struct Body: Encodable {
                let email: String
                let code: String
                let password: String
                let username: String?
            }
            return try await APIClient.shared.postJSON("/auth/register/verify", body: Body(
                email: account, code: code, password: password, username: username))
        case .phone:
            struct Body: Encodable {
                let phone: String
                let code: String
                let password: String
                let username: String?
            }
            return try await APIClient.shared.postJSON("/auth/phone/register", body: Body(
                phone: account, code: code, password: password, username: username))
        }
    }

    // MARK: - 找回密码

    /// 请求找回密码验证码。
    ///
    /// 注意：无论账号是否存在服务端都返回成功（防账号枚举），所以这个调用成功
    /// 不代表账号存在，UI 上不能据此提示「账号已找到」。
    @discardableResult
    static func requestPasswordResetCode(
        account: String, channel: AccountChannel
    ) async throws -> SentResponse {
        switch channel {
        case .email:
            struct Body: Encodable { let email: String }
            return try await APIClient.shared.postJSON(
                "/auth/password-reset/request", body: Body(email: account))
        case .phone:
            struct Body: Encodable { let phone: String }
            return try await APIClient.shared.postJSON(
                "/auth/phone/password-reset/request", body: Body(phone: account))
        }
    }

    /// 凭验证码设置新密码。
    @discardableResult
    static func confirmPasswordReset(
        account: String, channel: AccountChannel, code: String, newPassword: String
    ) async throws -> ResetResponse {
        switch channel {
        case .email:
            struct Body: Encodable {
                let email: String
                let code: String
                let new_password: String
            }
            return try await APIClient.shared.postJSON(
                "/auth/password-reset/confirm",
                body: Body(email: account, code: code, new_password: newPassword))
        case .phone:
            struct Body: Encodable {
                let phone: String
                let code: String
                let new_password: String
            }
            return try await APIClient.shared.postJSON(
                "/auth/phone/password-reset/confirm",
                body: Body(phone: account, code: code, new_password: newPassword))
        }
    }

    // MARK: - 账号

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
```

- [ ] **Step 2: 从 ChanService.swift 删掉旧的 AuthService**

删除 `ios/DeepAlphaChan/Networking/ChanService.swift` 里从
`/// 认证接口封装。` 开始到文件末尾 `enum AuthService { ... }` 的整个块。
`enum ChanService` 及其三个方法保留不动。

旧的 `login(email:password:)`（form-urlencoded 打 `/auth/login`）和
`register(email:password:username:)`（无验证码打 `/auth/register`）一并删除——
App 端不再需要它们，服务端保留那两个 legacy 端点是为了已上架的旧版本，
新版本没有理由继续调用。

- [ ] **Step 3: 编译**

Run:
```bash
cd /Users/zhangfang/deepalpha-club-ai/ios && xcodebuild -project DeepAlphaChan.xcodeproj -scheme DeepAlphaChan -destination 'generic/platform=iOS' build 2>&1 | tail -20
```
Expected: FAIL。`AuthViewModel.swift` 调用的 `AuthService.login(email:password:)` 和
`AuthService.register(email:password:username:)` 签名已变。Task 4 修。

- [ ] **Step 4: 提交**

```bash
git add ios/DeepAlphaChan/Networking/AuthService.swift ios/DeepAlphaChan/Networking/ChanService.swift
git commit -m "refactor(ios/chan): AuthService 拆为独立文件并补齐双通道端点"
```

---

### Task 4: AuthViewModel

**Files:**
- Modify: `ios/DeepAlphaChan/ViewModels/AuthViewModel.swift`

- [ ] **Step 1: 整体替换文件内容**

```swift
import Foundation
import SwiftUI

/// 全局认证状态。
///
/// 「保持登录」的语义：勾选时 token 留在 Keychain，下次启动直接进主页（这是
/// 改造前唯一的行为）；不勾选时启动即清 token，必须重新登录。判断放在 init 里
/// 而不是 logout 里，因为要覆盖的正是「上次没勾、App 被杀掉后重新打开」这种情况。
@MainActor
final class AuthViewModel: ObservableObject {
    @Published var isAuthenticated: Bool
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var profile: UserProfile?

    /// 保持登录。默认开——绝大多数用户不希望每次打开都登录一遍。
    @AppStorage("remember_me") var rememberMe: Bool = true

    init() {
        // @AppStorage 在 init 里还不能读，直接查 UserDefaults。键名必须与上面一致。
        let remembered = UserDefaults.standard.object(forKey: "remember_me") as? Bool ?? true
        if !remembered {
            KeychainStore.clearToken()
        }
        self.isAuthenticated = KeychainStore.loadToken() != nil
    }

    // MARK: - 登录

    func login(account: String, password: String) async {
        guard !account.isEmpty, !password.isEmpty else {
            errorMessage = "请输入账号和密码"
            return
        }
        await perform(fallback: "登录失败，请稍后再试") {
            let resp = try await AuthService.login(account: account, password: password)
            self.finishAuth(token: resp.accessToken)
        }
    }

    /// Sign in with Apple：用 Apple 身份令牌登录。
    func loginWithApple(identityToken: String, fullName: String?) async {
        await perform(fallback: "Apple 登录失败，请稍后再试") {
            let resp = try await AuthService.appleLogin(
                identityToken: identityToken, fullName: fullName)
            self.finishAuth(token: resp.accessToken)
        }
    }

    // MARK: - 注册

    /// 请求注册验证码。成功返回 true，供界面启动倒计时。
    func requestRegisterCode(account: String, channel: AccountChannel) async -> Bool {
        await performBool(fallback: "验证码发送失败，请稍后再试") {
            try await AuthService.requestRegisterCode(account: account, channel: channel)
        }
    }

    func register(
        account: String, channel: AccountChannel, code: String,
        password: String, username: String?
    ) async {
        await perform(fallback: "注册失败，请稍后再试") {
            let resp = try await AuthService.register(
                account: account, channel: channel, code: code,
                password: password,
                username: (username?.isEmpty == false) ? username : nil)
            self.finishAuth(token: resp.token.accessToken)
        }
    }

    // MARK: - 找回密码

    func requestPasswordResetCode(account: String, channel: AccountChannel) async -> Bool {
        await performBool(fallback: "验证码发送失败，请稍后再试") {
            try await AuthService.requestPasswordResetCode(account: account, channel: channel)
        }
    }

    /// 重置密码。成功返回 true，界面据此关闭页面并提示去登录。
    func resetPassword(
        account: String, channel: AccountChannel, code: String, newPassword: String
    ) async -> Bool {
        await performBool(fallback: "重置密码失败，请稍后再试") {
            try await AuthService.confirmPasswordReset(
                account: account, channel: channel, code: code, newPassword: newPassword)
        }
    }

    // MARK: - 账号

    func loadProfile() async {
        profile = try? await AuthService.me()
    }

    func logout() {
        KeychainStore.clearToken()
        profile = nil
        isAuthenticated = false
    }

    /// 删除账号：成功后本地登出。
    func deleteAccount() async -> Bool {
        await performBool(fallback: "删除账号失败，请稍后再试") {
            try await AuthService.deleteAccount()
            self.logout()
        }
    }

    // MARK: - 内部

    /// 登录成功后的共同收尾：存 token、置状态、拉资料。
    ///
    /// 不勾「保持登录」时仍然写 Keychain，因为本次会话的所有请求都要靠它取 token；
    /// 区别在于下次启动时 init 会把它清掉。
    private func finishAuth(token: String) {
        KeychainStore.saveToken(token)
        isAuthenticated = true
        Task { await loadProfile() }
    }

    /// 包住 isLoading / errorMessage 的样板。九个入口各写一遍 do-catch 太吵。
    private func perform(fallback: String, _ body: @escaping () async throws -> Void) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            try await body()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = fallback
        }
    }

    @discardableResult
    private func performBool(
        fallback: String, _ body: @escaping () async throws -> Void
    ) async -> Bool {
        var ok = false
        await perform(fallback: fallback) {
            try await body()
            ok = true
        }
        return ok
    }
}
```

- [ ] **Step 2: 编译**

Run:
```bash
cd /Users/zhangfang/deepalpha-club-ai/ios && xcodebuild -project DeepAlphaChan.xcodeproj -scheme DeepAlphaChan -destination 'generic/platform=iOS' build 2>&1 | tail -20
```
Expected: FAIL。`LoginView.swift` 调 `auth.login(email:password:)`、
`RegisterView.swift` 调 `auth.register(email:password:username:)`，签名都变了。
Task 6、7 修。

- [ ] **Step 3: 提交**

```bash
git add ios/DeepAlphaChan/ViewModels/AuthViewModel.swift
git commit -m "feat(ios/chan): AuthViewModel 支持双通道与保持登录"
```

---

### Task 5: 共用输入控件

`LoginView` 和 `RegisterView` 各自私有实现了一遍 `field()` 和 `secureField()`，
再加一个 `ForgotPasswordView` 就是三份。抽出来。

**Files:**
- Create: `ios/DeepAlphaChan/Views/Components/AuthFields.swift`

- [ ] **Step 1: 创建文件**

```swift
import SwiftUI

/// 认证页面共用的输入控件。
///
/// LoginView 和 RegisterView 原本各自私有实现了一份 field/secureField，
/// 加上 ForgotPasswordView 就是三份完全一样的代码，抽到这里。

/// 带图标的普通输入框。
struct AuthTextField: View {
    let icon: String
    let placeholder: String
    @Binding var text: String

    var body: some View {
        HStack {
            Image(systemName: icon).foregroundColor(Theme.textSecondary).frame(width: 20)
            TextField(placeholder, text: $text).foregroundColor(Theme.textPrimary)
        }
        .padding(12)
        .background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

/// 带图标的密码输入框。
struct AuthSecureField: View {
    let icon: String
    let placeholder: String
    @Binding var text: String

    var body: some View {
        HStack {
            Image(systemName: icon).foregroundColor(Theme.textSecondary).frame(width: 20)
            SecureField(placeholder, text: $text).foregroundColor(Theme.textPrimary)
        }
        .padding(12)
        .background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

/// 手机号 / 邮箱切换。
struct AccountChannelPicker: View {
    @Binding var channel: AccountChannel

    var body: some View {
        Picker("", selection: $channel) {
            ForEach(AccountChannel.allCases) { c in
                Text(c.title).tag(c)
            }
        }
        .pickerStyle(.segmented)
    }
}

/// 账号输入框：键盘类型随通道切换。
struct AccountField: View {
    let channel: AccountChannel
    @Binding var text: String

    var body: some View {
        AuthTextField(icon: channel.icon, placeholder: channel.placeholder, text: $text)
            .keyboardType(channel == .phone ? .numberPad : .emailAddress)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
    }
}

/// 验证码输入框 + 获取按钮（带倒计时）。
///
/// 倒计时秒数与后端 EMAIL_CODE_RESEND_COOLDOWN 对齐（60 秒）。这只是个体验优化，
/// 真正的冷却由服务端把关——用户重装 App 也绕不过去。
struct VerificationCodeField: View {
    @Binding var code: String
    let canRequest: Bool
    /// 返回 true 表示发送成功，才开始倒计时。
    let onRequest: () async -> Bool

    @State private var remaining = 0
    @State private var isRequesting = false

    private let cooldown = 60

    var body: some View {
        HStack(spacing: 10) {
            HStack {
                Image(systemName: "number").foregroundColor(Theme.textSecondary).frame(width: 20)
                TextField("6 位验证码", text: $code)
                    .keyboardType(.numberPad)
                    .foregroundColor(Theme.textPrimary)
                    .onChange(of: code) { _, newValue in
                        // 只留数字并截断，避免粘贴进来一串带空格的内容
                        let digits = String(newValue.filter(\.isNumber).prefix(6))
                        if digits != newValue { code = digits }
                    }
            }
            .padding(12)
            .background(Theme.surfaceAlt)
            .clipShape(RoundedRectangle(cornerRadius: 10))

            Button {
                Task {
                    isRequesting = true
                    let sent = await onRequest()
                    isRequesting = false
                    if sent { startCountdown() }
                }
            } label: {
                Group {
                    if isRequesting {
                        ProgressView().tint(Theme.accent)
                    } else {
                        Text(remaining > 0 ? "\(remaining)s" : "获取验证码")
                            .font(.footnote)
                    }
                }
                .frame(width: 88)
                .padding(.vertical, 14)
                .foregroundColor(buttonEnabled ? Theme.accent : Theme.textSecondary)
                .background(Theme.surfaceAlt)
                .clipShape(RoundedRectangle(cornerRadius: 10))
            }
            .disabled(!buttonEnabled)
        }
    }

    private var buttonEnabled: Bool {
        canRequest && remaining == 0 && !isRequesting
    }

    private func startCountdown() {
        remaining = cooldown
        Task {
            while remaining > 0 {
                try? await Task.sleep(for: .seconds(1))
                remaining -= 1
            }
        }
    }
}
```

- [ ] **Step 2: 编译**

Run:
```bash
cd /Users/zhangfang/deepalpha-club-ai/ios && xcodebuild -project DeepAlphaChan.xcodeproj -scheme DeepAlphaChan -destination 'generic/platform=iOS' build 2>&1 | tail -20
```
Expected: 仍是 Task 4 遗留的 LoginView/RegisterView 报错，但不应出现
`AuthFields.swift` 自身的错误。如果 `Theme.surfaceAlt`、`Theme.border` 之类
的符号报未定义，去 `ios/DeepAlphaChan/App/Theme.swift` 核对实际名字后改用正确的。

- [ ] **Step 3: 提交**

```bash
git add ios/DeepAlphaChan/Views/Components/AuthFields.swift
git commit -m "feat(ios/chan): 抽出认证页共用输入控件与验证码倒计时按钮"
```

---

### Task 6: 登录页

**Files:**
- Modify: `ios/DeepAlphaChan/Views/LoginView.swift`

- [ ] **Step 1: 替换文件内容**

```swift
import SwiftUI
import AuthenticationServices

/// 登录页。支持：手机号/邮箱 + 密码登录、注册、找回密码、Sign in with Apple。
struct LoginView: View {
    @EnvironmentObject var auth: AuthViewModel
    @State private var channel: AccountChannel = .phone
    @State private var account = ""
    @State private var password = ""
    @State private var showRegister = false
    @State private var showForgotPassword = false
    @FocusState private var focused: Field?

    private enum Field { case account, password }

    private var canSubmit: Bool {
        AccountInput.isValid(account, channel: channel) && !password.isEmpty
    }

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            VStack(spacing: 24) {
                Spacer()
                header

                VStack(spacing: 14) {
                    AccountChannelPicker(channel: $channel)

                    AccountField(channel: channel, text: $account)
                        .focused($focused, equals: .account)
                        .submitLabel(.next)
                        .onSubmit { focused = .password }

                    AuthSecureField(icon: "lock", placeholder: "密码", text: $password)
                        .focused($focused, equals: .password)
                        .submitLabel(.go)
                        .onSubmit { submit() }

                    rememberAndForgot

                    if let error = auth.errorMessage {
                        Text(error)
                            .font(.footnote)
                            .foregroundColor(Theme.down)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    Button {
                        submit()
                    } label: {
                        HStack {
                            if auth.isLoading { ProgressView().tint(.white) }
                            Text(auth.isLoading ? "登录中…" : "登录")
                                .fontWeight(.semibold)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(canSubmit ? Theme.accent : Theme.surfaceAlt)
                        .foregroundColor(canSubmit ? .white : Theme.textSecondary)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                    .disabled(!canSubmit || auth.isLoading)

                    Button {
                        auth.errorMessage = nil
                        showRegister = true
                    } label: {
                        Text("没有账号？注册").font(.footnote).foregroundColor(Theme.accent)
                    }

                    dividerOr

                    SignInWithAppleButton(.signIn) { request in
                        request.requestedScopes = [.fullName, .email]
                    } onCompletion: { result in
                        handleApple(result)
                    }
                    .signInWithAppleButtonStyle(.white)
                    .frame(height: 48)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                }
                .padding(20)
                .background(Theme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 16))

                Spacer()

                Text("本 App 内容仅供技术研究与学习，不构成任何投资建议。\n投资有风险，决策需自主判断。")
                    .font(.caption2)
                    .multilineTextAlignment(.center)
                    .foregroundColor(Theme.textSecondary)
            }
            .padding(24)
        }
        .sheet(isPresented: $showRegister) { RegisterView() }
        .sheet(isPresented: $showForgotPassword) { ForgotPasswordView(channel: channel) }
        .onChange(of: channel) { _, _ in
            // 切换通道时清空输入，否则手机号会留在邮箱框里显得莫名其妙
            account = ""
            auth.errorMessage = nil
        }
    }

    private func submit() {
        focused = nil
        Task { await auth.login(account: account, password: password) }
    }

    private var header: some View {
        VStack(spacing: 8) {
            Image(systemName: "waveform.path.ecg")
                .font(.system(size: 44))
                .foregroundStyle(Theme.accent)
            Text("DeepAlpha 缠论")
                .font(.title.bold())
                .foregroundColor(Theme.textPrimary)
            Text("结构化技术分析")
                .font(.subheadline)
                .foregroundColor(Theme.textSecondary)
        }
    }

    private var rememberAndForgot: some View {
        HStack {
            Button {
                auth.rememberMe.toggle()
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: auth.rememberMe ? "checkmark.square.fill" : "square")
                        .foregroundColor(auth.rememberMe ? Theme.accent : Theme.textSecondary)
                    Text("保持登录").font(.footnote).foregroundColor(Theme.textSecondary)
                }
            }
            Spacer()
            Button {
                auth.errorMessage = nil
                showForgotPassword = true
            } label: {
                Text("忘记密码？").font(.footnote).foregroundColor(Theme.accent)
            }
        }
    }

    // MARK: - Sign in with Apple 处理

    private func handleApple(_ result: Result<ASAuthorization, Error>) {
        switch result {
        case .success(let authorization):
            guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
                  let tokenData = credential.identityToken,
                  let token = String(data: tokenData, encoding: .utf8) else {
                auth.errorMessage = "无法获取 Apple 身份令牌"
                return
            }
            let name = [credential.fullName?.givenName, credential.fullName?.familyName]
                .compactMap { $0 }.joined(separator: " ")
            Task { await auth.loginWithApple(identityToken: token, fullName: name.isEmpty ? nil : name) }
        case .failure(let error):
            // 用户主动取消不提示
            if (error as NSError).code != ASAuthorizationError.canceled.rawValue {
                auth.errorMessage = "Apple 登录失败，请重试"
            }
        }
    }

    private var dividerOr: some View {
        HStack(spacing: 10) {
            Rectangle().fill(Theme.border).frame(height: 1)
            Text("或").font(.caption2).foregroundColor(Theme.textSecondary)
            Rectangle().fill(Theme.border).frame(height: 1)
        }
    }
}
```

- [ ] **Step 2: 编译**

Run:
```bash
cd /Users/zhangfang/deepalpha-club-ai/ios && xcodebuild -project DeepAlphaChan.xcodeproj -scheme DeepAlphaChan -destination 'generic/platform=iOS' build 2>&1 | tail -20
```
Expected: FAIL，`cannot find 'ForgotPasswordView' in scope` 和 RegisterView 的旧签名
报错。Task 7、8 修完就好。

- [ ] **Step 3: 提交**

```bash
git add ios/DeepAlphaChan/Views/LoginView.swift
git commit -m "feat(ios/chan): 登录页支持手机号/邮箱切换与保持登录"
```

---

### Task 7: 注册页

**Files:**
- Modify: `ios/DeepAlphaChan/Views/RegisterView.swift`

- [ ] **Step 1: 替换文件内容**

```swift
import SwiftUI

/// 注册页。手机号或邮箱 + 验证码 + 密码。
/// 密码规则对齐后端 validate_password_strength：8–64 位，含大小写字母、数字、特殊字符。
struct RegisterView: View {
    @EnvironmentObject var auth: AuthViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var channel: AccountChannel = .phone
    @State private var account = ""
    @State private var code = ""
    @State private var username = ""
    @State private var password = ""
    @State private var confirm = ""

    private var rules: PasswordRules { PasswordRules(password: password) }
    private var matched: Bool { !confirm.isEmpty && password == confirm }
    private var accountValid: Bool { AccountInput.isValid(account, channel: channel) }

    private var canSubmit: Bool {
        accountValid && AccountInput.isValidCode(code) && rules.allSatisfied && matched
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                ScrollView {
                    VStack(spacing: 14) {
                        AccountChannelPicker(channel: $channel)

                        AccountField(channel: channel, text: $account)

                        VerificationCodeField(code: $code, canRequest: accountValid) {
                            await auth.requestRegisterCode(account: account, channel: channel)
                        }

                        AuthTextField(icon: "person", placeholder: "用户名（可选）", text: $username)
                            .autocorrectionDisabled()

                        AuthSecureField(icon: "lock", placeholder: "密码", text: $password)
                        AuthSecureField(icon: "lock.rotation", placeholder: "确认密码", text: $confirm)

                        rulesChecklist

                        if let error = auth.errorMessage {
                            Text(error).font(.footnote).foregroundColor(Theme.down)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        Button {
                            Task {
                                await auth.register(
                                    account: account, channel: channel, code: code,
                                    password: password, username: username)
                                if auth.isAuthenticated { dismiss() }
                            }
                        } label: {
                            HStack {
                                if auth.isLoading { ProgressView().tint(.white) }
                                Text(auth.isLoading ? "注册中…" : "注册并登录").fontWeight(.semibold)
                            }
                            .frame(maxWidth: .infinity).padding(.vertical, 14)
                            .background(canSubmit ? Theme.accent : Theme.surfaceAlt)
                            .foregroundColor(canSubmit ? .white : Theme.textSecondary)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                        .disabled(!canSubmit || auth.isLoading)
                    }
                    .padding(20)
                }
            }
            .navigationTitle("注册")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("取消") { auth.errorMessage = nil; dismiss() }
                }
            }
            .onChange(of: channel) { _, _ in
                // 切换通道时清空账号和验证码：验证码是绑在具体账号上的，留着只会误导
                account = ""
                code = ""
                auth.errorMessage = nil
            }
        }
    }

    private var rulesChecklist: some View {
        VStack(alignment: .leading, spacing: 6) {
            rule("8–64 位长度", rules.longEnough)
            rule("含大写字母", rules.hasUpper)
            rule("含小写字母", rules.hasLower)
            rule("含数字", rules.hasDigit)
            rule("含特殊字符（如 !@#$%^&*）", rules.hasSpecial)
            rule("两次密码一致", matched)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func rule(_ text: String, _ ok: Bool) -> some View {
        HStack(spacing: 6) {
            Image(systemName: ok ? "checkmark.circle.fill" : "circle")
                .font(.caption).foregroundColor(ok ? Theme.up : Theme.textSecondary)
            Text(text).font(.caption).foregroundColor(ok ? Theme.textPrimary : Theme.textSecondary)
        }
    }
}
```

- [ ] **Step 2: 提交**

```bash
git add ios/DeepAlphaChan/Views/RegisterView.swift
git commit -m "feat(ios/chan): 注册页支持双通道验证码注册"
```

---

### Task 8: 找回密码页

**Files:**
- Create: `ios/DeepAlphaChan/Views/ForgotPasswordView.swift`

- [ ] **Step 1: 创建文件**

```swift
import SwiftUI

/// 找回密码页。手机号或邮箱 + 验证码 + 新密码。
///
/// 注意：服务端对未注册的账号也返回「已发送」（防账号枚举），所以这里不能
/// 因为发码成功就提示「账号已找到」——用户输错账号时会一直收不到码，这是
/// 有意为之的取舍。
struct ForgotPasswordView: View {
    @EnvironmentObject var auth: AuthViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var channel: AccountChannel
    @State private var account = ""
    @State private var code = ""
    @State private var password = ""
    @State private var confirm = ""
    @State private var done = false

    /// 从登录页带过来当前选中的通道，省得用户再切一次。
    init(channel: AccountChannel = .phone) {
        _channel = State(initialValue: channel)
    }

    private var rules: PasswordRules { PasswordRules(password: password) }
    private var matched: Bool { !confirm.isEmpty && password == confirm }
    private var accountValid: Bool { AccountInput.isValid(account, channel: channel) }

    private var canSubmit: Bool {
        accountValid && AccountInput.isValidCode(code) && rules.allSatisfied && matched
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                ScrollView {
                    VStack(spacing: 14) {
                        AccountChannelPicker(channel: $channel)

                        AccountField(channel: channel, text: $account)

                        VerificationCodeField(code: $code, canRequest: accountValid) {
                            await auth.requestPasswordResetCode(account: account, channel: channel)
                        }

                        AuthSecureField(icon: "lock", placeholder: "新密码", text: $password)
                        AuthSecureField(icon: "lock.rotation", placeholder: "确认新密码", text: $confirm)

                        rulesChecklist

                        if let error = auth.errorMessage {
                            Text(error).font(.footnote).foregroundColor(Theme.down)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        if done {
                            Text("密码已重置，请用新密码登录")
                                .font(.footnote).foregroundColor(Theme.up)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        Button {
                            Task {
                                let ok = await auth.resetPassword(
                                    account: account, channel: channel,
                                    code: code, newPassword: password)
                                if ok {
                                    done = true
                                    try? await Task.sleep(for: .seconds(1))
                                    dismiss()
                                }
                            }
                        } label: {
                            HStack {
                                if auth.isLoading { ProgressView().tint(.white) }
                                Text(auth.isLoading ? "提交中…" : "重置密码").fontWeight(.semibold)
                            }
                            .frame(maxWidth: .infinity).padding(.vertical, 14)
                            .background(canSubmit ? Theme.accent : Theme.surfaceAlt)
                            .foregroundColor(canSubmit ? .white : Theme.textSecondary)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                        .disabled(!canSubmit || auth.isLoading)
                    }
                    .padding(20)
                }
            }
            .navigationTitle("找回密码")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("取消") { auth.errorMessage = nil; dismiss() }
                }
            }
            .onChange(of: channel) { _, _ in
                account = ""
                code = ""
                auth.errorMessage = nil
            }
        }
    }

    private var rulesChecklist: some View {
        VStack(alignment: .leading, spacing: 6) {
            rule("8–64 位长度", rules.longEnough)
            rule("含大写字母", rules.hasUpper)
            rule("含小写字母", rules.hasLower)
            rule("含数字", rules.hasDigit)
            rule("含特殊字符（如 !@#$%^&*）", rules.hasSpecial)
            rule("两次密码一致", matched)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func rule(_ text: String, _ ok: Bool) -> some View {
        HStack(spacing: 6) {
            Image(systemName: ok ? "checkmark.circle.fill" : "circle")
                .font(.caption).foregroundColor(ok ? Theme.up : Theme.textSecondary)
            Text(text).font(.caption).foregroundColor(ok ? Theme.textPrimary : Theme.textSecondary)
        }
    }
}
```

- [ ] **Step 2: 编译**

Run:
```bash
cd /Users/zhangfang/deepalpha-club-ai/ios && xcodebuild -project DeepAlphaChan.xcodeproj -scheme DeepAlphaChan -destination 'generic/platform=iOS' build 2>&1 | tail -5
```
Expected: `** BUILD SUCCEEDED **`（到这里所有编译错误应全部消除）

- [ ] **Step 3: 提交**

```bash
git add ios/DeepAlphaChan/Views/ForgotPasswordView.swift
git commit -m "feat(ios/chan): 新增找回密码页"
```

---

### Task 9: 手工验收

没有 XCTest target，这一步是唯一的功能验证，逐项走完，不要跳。

**前置：** 后端跑起来（`make dev`），并在本地 `.env` 里填好 `SMTP_*`；
手机通道需要 `ALIYUN_SMS_*`，没有凭据就只验证「返回 503 且界面提示友好」这一条。
`ios/DeepAlphaChan/App/AppConfig.swift` 里的 `baseURL` 指向本地后端。

- [ ] **Step 1: 编译并装到模拟器**

Run:
```bash
cd /Users/zhangfang/deepalpha-club-ai/ios && xcodebuild -project DeepAlphaChan.xcodeproj -scheme DeepAlphaChan -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -5
```
Expected: `** BUILD SUCCEEDED **`

- [ ] **Step 2: 走一遍测试矩阵**

逐项确认，把结果记在提交信息里：

| # | 操作 | 预期 |
|---|------|------|
| 1 | 登录页默认状态 | 通道是「手机号」，键盘数字键盘，「保持登录」已勾选 |
| 2 | 切到「邮箱」 | 账号框清空，键盘变邮箱键盘 |
| 3 | 手机号输入 `138` | 登录按钮置灰 |
| 4 | 手机号输入 `13800138000` + 任意密码 | 登录按钮变亮 |
| 5 | 用错误密码登录 | 提示「账号或密码错误」，不闪退 |
| 6 | 注册页，账号未填完 | 「获取验证码」置灰 |
| 7 | 注册页，邮箱填完整 | 「获取验证码」变亮；点击后变成 60s 倒计时且不可点 |
| 8 | 收到邮件 | 署名是「DeepAlpha 缠论」而不是「鹦鹉背单词」 |
| 9 | 验证码填错 | 提示「验证码错误或已过期」 |
| 10 | 验证码正确 + 合规密码 | 注册成功，直接进主页 |
| 11 | 手机通道发码（无阿里云凭据） | 提示「验证码服务暂不可用」，不是「请求失败（503）」 |
| 12 | 个人页 | 手机号注册的账号显示打码手机号，邮箱注册的显示邮箱 |
| 13 | 勾着「保持登录」杀掉 App 重开 | 直接进主页 |
| 14 | 取消勾选后杀掉 App 重开 | 回到登录页 |
| 15 | 忘记密码 → 走完流程 | 提示「密码已重置」，页面自动关闭，能用新密码登录 |
| 16 | Sign in with Apple | 仍能正常登录（真机上测，模拟器可能受限） |

- [ ] **Step 3: 修掉矩阵里发现的问题**

逐个修。每修一个单独提交。

- [ ] **Step 4: 真机验证 Apple 登录**

模拟器上 Sign in with Apple 行为不完整，第 16 项必须在真机上重跑一次。

- [ ] **Step 5: 提交收尾**

```bash
git add -A
git commit -m "chore(ios/chan): 双通道认证手工验收通过"
```

---

## 已知取舍

- **本地校验只做中国大陆手机号。** 后端 `utils/phone.py` 保留了「显式带国家码的
  国际号原样接受」的能力，但 App 的输入框和校验都按 11 位大陆号做。要支持国际号
  需要加区号选择器，本次不做。
- **没有验证码免密登录。** 验证码只用于注册和找回密码，登录一律用密码。
- **「保持登录」不影响本次会话。** 不勾选时 token 仍写 Keychain（本次会话的请求要用），
  只在下次启动时清除。真正的「完全不落盘」需要改 `APIClient` 的取 token 路径，
  收益不抵复杂度。
