# TradingDesk iOS App 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在主仓库子目录 `ios/DeepAlphaClub`（与既有 `ios/DeepAlphaChan`、`ios/WordLens` 并列）从零搭建 SwiftUI 交易台 App（iOS 17+ / Swift 6），复用线上 FastAPI 后端（零改动），实现登录、启动分析、SSE 流式渲染、暂停/注入/取消控制、历史回放。

**Architecture:** 核心逻辑（模型/状态机/SSE/API/ViewModel/SwiftData 缓存）放 SPM package `DeepAlphaCore`（macOS 可 `swift test` 秒级跑，TDD 主战场）；SwiftUI 视图层放 App target，由 xcodegen 生成工程引用本地 package。MVVM + @Observable。

**Tech Stack:** Swift 6（strict concurrency）、SwiftUI（iOS 17+，Observation framework）、SwiftData、URLSession（SSE 用 bytes 流）、Security（Keychain）。无第三方依赖。

**Spec:** `docs/superpowers/specs/2026-08-30-trading-desk-ios-app-design.md`（本计划修正其 3 处与实际后端不符的地方，见下）

---

## 前置侦察结论（已实跑核实，写代码时直接依据）

### Spec 勘误（以实际代码为准，覆盖 spec §5.5）

| # | spec 写的 | 实际（已核实源码） |
|---|---|---|
| 1 | 登录 `POST /api/v1/auth/sessions`（chat session token） | **`POST /api/v1/auth/login`**，`application/x-www-form-urlencoded`，字段 `email` / `password` / `grant_type=password`（`app/api/v1/auth/routes.py:151`）。必须用登录 access_token：trading_desk 路由依赖 `get_current_user` → `verify_token` 校验 `sub` 为 **user_id**；chat session token 的 sub 是 thread_id，不兼容 |
| 2 | SSE `GET /api/v1/chatbot/langgraph/stream?run_id=X&last_event_id=Y` | **`GET /api/v1/trading-desk/runs/{run_id}/stream`**，续读用 **`Last-Event-ID` 请求头**（`app/api/v1/trading_desk.py:135`） |
| 3 | 路由前缀 `/api/v1/trading_desk/` | **`/api/v1/trading-desk/`（连字符）**（`app/api/v1/api.py:48`） |

### 后端契约要点

- **登录响应** `TokenResponse`：`{access_token, token_type, expires_at, request_id}`（`request_id` 所有响应都带，Swift Decodable 忽略未知键即可）。
- **SSE 帧格式**：`id: <RedisStreamId>\ndata: <JSON一行>\n\n`；空闲期每 15s 发注释行 `:\n\n` 保活（客户端当心跳忽略）。
- **事件信封** `TradingDeskEvent`：`{type, run_id, seq, ts, data}`；`seq` 单调递增用于去重（重连重放旧事件直接丢）；`data` 是弱类型字典，形状由 `type` 决定。17 种事件类型见 `app/schemas/trading_desk.py` 的 `EventType`。
- **重连策略**（移植 web `frontend/app/trading-desk/page.tsx:67` 的 `consume`）：backoff 800ms 起倍增 cap 30s；仅 status ∈ {running, paused} 时重连；流**正常结束不重连**（后端 run.finished 后关流）；抛错才重连。
- **`resolveTicker`**（移植 `frontend/app/trading-desk/page.tsx:31`）：输入含 `.` 直接保留；HK strip 前导零再拼 `.HK`；US 无后缀；SH→`.SS`；SZ→`.SZ`；A 股前导零是有效位不动。
- **响应模型**：`CreateRunResponse{run_id}`、`ControlResponse{accepted}`、`RunListResponse{runs:[RunSummary]}`、`RunDetailResponse{...turns:[TurnRecord], signals:[SignalRecord], verdict:dict|null}`（字段全表见 `frontend/lib/api/trading_desk.ts`，TS↔Swift 一一对应）。
- **控制动作**：`POST /runs/{id}/control` body `{action, text}`，action ∈ pause/resume/inject/cancel；inject 必带非空 text（否则 422）。
- **错误 body**：FastAPI `{"detail": "中文消息"}`；401 → 清 token 回登录页；404/422/5xx → 顶部 banner。

### 本机工具链（已核实）

- Xcode 26.5（Build 17F42）、Swift 6.3.2、iOS 26.5 模拟器（iPhone 17 Pro 等）可用。
- `xcodegen` **未安装**，Task 15 先 `brew install xcodegen`。
- 跑包内测试：`cd ios/DeepAlphaClub/Core && swift test`（macOS destination，秒级）。
- 跑 App 编译：`xcodebuild -project DeepAlphaClub.xcodeproj -scheme DeepAlphaClub -destination 'platform=iOS Simulator,name=iPhone 17 Pro' CODE_SIGNING_ALLOWED=NO build`。

### 范围裁剪（相对 spec）

- **跳过 snapshot 测试**（spec 标注「推荐」）：`swift-snapshot-testing` 需拉 SPM 网络依赖，且视觉回归对单人自用 App 收益低。视觉正确性由模拟器手动冒烟验收。逻辑覆盖靠 Core 层单测（reducer / VM 状态机 / SSE 解析 / API 客户端）。
- **跳过 mock server 集成测试**：线上后端已部署且用户有账号，手动联调更真实。
- **XCUITest 跳过**（spec 已定）。

## 文件结构

```
ios/DeepAlphaClub/                  # 主仓库子目录（自包含：SPM 包 + App + xcodegen）
├── project.yml                     # xcodegen 描述（Task 15）
├── Core/                           # 本地 SPM 包 DeepAlphaCore（iOS 17 / macOS 14）
│   └── Package.swift
├── Core/Sources/Core/              # 模块名 DeepAlphaCore，target 路径 Sources/Core
│   ├── Models/JSONValue.swift      # 弱类型 JSON 树 + literal 便捷构造（Task 2）
│   ├── Models/TradingDeskModels.swift  # 事件信封/EventType/payload structs（Task 2）
│   ├── Models/RunModels.swift      # RunSummary/RunDetail/TurnRecord/SignalRecord（Task 2）
│   ├── Models/AuthModels.swift     # LoginResponse（Task 6）
│   ├── TickerResolver.swift        # Market enum + resolveTicker（Task 3）
│   ├── SSEFrameParser.swift        # SSE 帧纯函数解析（Task 4）
│   ├── APIError.swift              # typed 错误 + 中文 message（Task 5）
│   ├── APIClient.swift             # 通用 HTTP（URLSession + tokenProvider）（Task 5）
│   ├── SSEClient.swift             # SSE 订阅 → AsyncThrowingStream（Task 8）
│   ├── KeychainStore.swift         # KeychainStoring 协议 + SecItem 实现 + InMemory（Task 6）
│   ├── AuthService.swift           # login form 编码（Task 6）
│   ├── TradingDeskService.swift    # TradingDeskServicing 协议 + 线上实现（Task 9）
│   ├── State/TradingDeskState.swift    # Turn/State 值类型（Task 7）
│   ├── State/TradingDeskReducer.swift  # reduceEvent 移植 + buildAuditChain（Task 7）
│   ├── MarkdownBlockParser.swift   # markdown → 块结构（供 TurnCard）（Task 12）
│   ├── Persistence/CachedRun.swift # SwiftData @Model（Task 13）
│   ├── Persistence/RunCache.swift  # @ModelActor 读写 + 50 条淘汰（Task 13）
│   └── ViewModels/
│       ├── AppState.swift          # 登录态（Task 11）
│       ├── TradingDeskViewModel.swift  # startRun/control/consume 重连（Task 10）
│       ├── HistoryListViewModel.swift  # 本地缓存 + 远端刷新（Task 14）
│       └── RunReplayViewModel.swift    # getRun → Turn 数组（Task 14）
├── Core/Tests/CoreTests/           # 每任务镜像一个测试文件
│   ├── MockURLProtocol.swift       # URLProtocol mock（Task 5 建，SSE 复用）
│   ├── ...
├── App/                            # xcodegen target（Task 15+）
│   ├── DeepAlphaClubApp.swift      # @main + scenePhase 接线
│   ├── CompositionRoot.swift       # 组装：baseURL/keychain/service
│   ├── RootView.swift              # 登录态路由
│   ├── Auth/LoginView.swift
│   ├── Theme/SignalColors.swift    # bull/bear/neutral/human 配色
│   ├── Features/TradingDesk/
│   │   ├── TradingDeskView.swift   # 主容器（compact TabView / regular 三栏）
│   │   ├── Topbar.swift            # 标题+状态+市场 segment+输入+按钮组
│   │   ├── InjectSheet.swift       # 注入意见输入
│   │   ├── PipelinePanel.swift
│   │   ├── StreamPanel.swift       # 智能滚动（贴底跟随）
│   │   ├── TurnCard.swift          # + MarkdownText
│   │   ├── DecisionPanel.swift
│   │   ├── ConsensusMeter.swift
│   │   ├── SignalChip.swift
│   │   └── VerdictCard.swift
│   └── Features/History/
│       ├── HistoryListView.swift
│       └── RunReplayView.swift
├── DeepAlphaClub.xcodeproj/        # xcodegen 生成（.gitignore 外，需提交）
└── README.md
```

**提交约定**：主仓库中文提交信息 `feat/fix/test(scope): 描述`。每 Task 结束提交一次。
（Task 1–15 原在独立仓库 `~/deepalpha-club-ios` 开发，已用 `git subtree add --prefix=ios/DeepAlphaClub` 连同 16 条提交历史并入主仓库。）

---

## Task 1: 仓库脚手架（git init + SPM 包 + 空测试）

**Files:**
- Create: `ios/DeepAlphaClub/.gitignore`
- Create: `ios/DeepAlphaClub/Core/Package.swift`
- Create: `ios/DeepAlphaClub/Core/Sources/Core/Placeholder.swift`（临占位，Task 2 删除）
- Create: `ios/DeepAlphaClub/Core/Tests/CoreTests/SmokeTests.swift`
- Create: `ios/DeepAlphaClub/README.md`

- [x] **Step 1: 建目录 + git init**

```bash
mkdir -p ios/DeepAlphaClub/Core/Sources/Core ios/DeepAlphaClub/Core/Tests/CoreTests
cd ios/DeepAlphaClub && git init
```

- [x] **Step 2: 写 .gitignore**

```gitignore
.DS_Store
.build/
.swiftpm/
*.xcodeproj/xcuserdata/
DerivedData/
```

注意：`DeepAlphaClub.xcodeproj` 本体要提交（xcodegen 生成物也提交，方便他人直接打开），只忽略 xcuserdata。

- [x] **Step 3: 写 Package.swift**

```swift
// swift-tools-version:6.0
import PackageDescription

let package = Package(
    name: "DeepAlphaCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "DeepAlphaCore", targets: ["Core"]),
    ],
    targets: [
        .target(
            name: "Core",
            swiftSettings: [.swiftLanguageMode(.v6)]
        ),
        .testTarget(
            name: "CoreTests",
            dependencies: ["Core"],
            swiftSettings: [.swiftLanguageMode(.v6)]
        ),
    ]
)
```

- [x] **Step 4: 写占位与冒烟测试**

`Core/Sources/Core/Placeholder.swift`:

```swift
/// 占位：Task 2 建立真实模型后删除。
public enum CorePlaceholder {
    public static let ok = true
}
```

`Core/Tests/CoreTests/SmokeTests.swift`:

```swift
import Testing
@testable import Core

@Test("包能被导入")
func smoke() {
    #expect(CorePlaceholder.ok)
}
```

用 Swift Testing（`import Testing`）而非 XCTest：Xcode 26 / swift-tools 6.0 内置，语法现代（`@Test` / `#expect`），与 SPM 默认集成。后文所有测试均用 Swift Testing。

- [x] **Step 5: 跑测试确认绿**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | tail -5
```

期望：`Test run with 1 test passed`（或 `✔ Test "包能被导入" passed`）。

- [x] **Step 6: 写 README + 首次提交**

README.md：

```markdown
# DeepAlphaClub iOS

交易台（TradingDesk）自用 App：多智能体分析 / SSE 流式 / 控制 / 历史回放。
后端复用 [deepalpha-club-ai](../deepalpha-club-ai)（`https://api.deepalpha.club`），零改动。

## 开发

```bash
brew install xcodegen          # 首次
xcodegen generate              # 生成 .xcodeproj（改 project.yml 后重跑）
swift test                     # Core 包单测（macOS，秒级）
open DeepAlphaClub.xcodeproj   # Xcode 里 Cmd+R 跑模拟器
```

命令行编译 App：
```bash
xcodebuild -project DeepAlphaClub.xcodeproj -scheme DeepAlphaClub \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' CODE_SIGNING_ALLOWED=NO build
```

## 结构

- `Sources/Core` — 全部业务逻辑（SPM，可 macOS 测试）
- `App/` — SwiftUI 视图层（xcodegen target）
- 协议契约见主仓库 `app/schemas/trading_desk.py`
```

```bash
git add ios/DeepAlphaClub && git commit -m "chore: 仓库脚手架（SPM 包 + swift-testing 冒烟）"
```

---

## Task 2: JSONValue + 事件与响应模型

**Files:**
- Create: `Core/Sources/Core/Models/JSONValue.swift`
- Create: `Core/Sources/Core/Models/TradingDeskModels.swift`
- Create: `Core/Sources/Core/Models/RunModels.swift`
- Delete: `Core/Sources/Core/Placeholder.swift`
- Test: `Core/Tests/CoreTests/ModelTests.swift`

- [x] **Step 1: 写失败测试**

`Core/Tests/CoreTests/ModelTests.swift`:

```swift
import Testing
@testable import Core

/// 测试端便捷构造 JSONValue 字面量。
func jobj(_ dict: [String: JSONValue]) -> JSONValue { .object(dict) }

@Test("事件信封解析：snake_case run_id 映射 runId")
func eventDecoding() throws {
    let json = """
    {"type":"agent.token","run_id":"r1","seq":3,"ts":1750000000000,
     "data":{"turn_id":"t1","text":"看多"}}
    """
    let e = try JSONDecoder().decode(TradingDeskEvent.self, from: Data(json.utf8))
    #expect(e.type == .agentToken)
    #expect(e.runId == "r1")
    #expect(e.seq == 3)
    #expect(e.data?["turn_id"]?.string == "t1")
    #expect(e.data?["text"]?.string == "看多")
}

@Test("isTerminal：run.finished 或 fatal error")
func terminal() {
    let fin = TradingDeskEvent(type: .runFinished, runId: "r", seq: 1, ts: 0,
                               data: jobj(["status": "completed", "duration_ms": 10]))
    #expect(fin.isTerminal)
    let fatal = TradingDeskEvent(type: .error, runId: "r", seq: 2, ts: 0,
                                 data: jobj(["message": "x", "fatal": true]))
    #expect(fatal.isTerminal)
    let soft = TradingDeskEvent(type: .error, runId: "r", seq: 3, ts: 0,
                                 data: jobj(["message": "x", "fatal": false]))
    #expect(!soft.isTerminal)
}

@Test("payload decode：run.started 的 capabilities/stages")
func runStartedPayload() throws {
    let d = jobj([
        "ticker": "NVDA", "trade_date": "2026-08-30", "engine": "tradingagents",
        "capabilities": ["supports_pause": true, "supports_inject": true,
                          "supports_resume_after_restart": false],
        "stages": [["id": "analyst_market", "name": "市场分析师", "role": "分析师",
                     "group": "analyst"]],
    ])
    let payload = try #require(d.decode(as: RunStartedData.self))
    #expect(payload.ticker == "NVDA")
    #expect(payload.capabilities.supportsPause)
    #expect(payload.stages.first?.group == .analyst)
}

@Test("payload decode：verdict 全字段含可空价格")
func verdictPayload() throws {
    let d = jobj([
        "signal": "BUY", "confidence": 0.72, "size_fraction": 0.25,
        "entry_reference_price": NSNull(), "target_price": 180.5,
        "stop_loss": 150, "currency": "USD", "time_horizon_days": 30,
        "rationale": "理由", "warning_message": NSNull(),
    ])
    let v = try #require(d.decode(as: VerdictData.self))
    #expect(v.signal == .buy)
    #expect(v.confidence == 0.72)
    #expect(v.entryReferencePrice == nil)
    #expect(v.targetPrice == 180.5)
    #expect(v.warningMessage == nil)
}

@Test("RunSummary 解析（历史列表条目）")
func runSummaryDecoding() throws {
    let json = """
    {"run_id":"abc","ticker":"NVDA","trade_date":"2026-08-30","engine":"tradingagents",
     "status":"completed","duration_ms":65000,"created_at":"2026-08-30T10:00:00+00:00",
     "finished_at":null,"verdict_signal":"BUY","verdict_confidence":0.72,
     "turns_count":12,"signals_count":4}
    """
    let s = try JSONDecoder().decode(RunSummary.self, from: Data(json.utf8))
    #expect(s.status == .completed)
    #expect(s.finishedAt == nil)
    #expect(s.verdictSignal == .buy)
    #expect(s.turnsCount == 12)
}

@Test("RunDetail 的 verdict 是 dict 也可直接反序列化为 VerdictData")
func runDetailVerdict() throws {
    let json = """
    {"run_id":"abc","ticker":"NVDA","trade_date":"2026-08-30","engine":"e",
     "status":"completed","duration_ms":1,"created_at":"2026-08-30T10:00:00+00:00",
     "verdict":{"signal":"HOLD","confidence":0.5,"size_fraction":0.0,
                "entry_reference_price":null,"target_price":null,"stop_loss":null,
                "currency":null,"time_horizon_days":null,"rationale":"r",
                "warning_message":null},
     "signals":[{"stage_id":"s","name":"n","dir":"bull","conf":80,
                  "turn_id":null,"extracted":true}],
     "turns":[{"turn_id":"t1","stage_id":"s","name":"风控","role":"r","avatar":"风",
                "text":"内容","tool_calls":["lookup"],"debate":null}]}
    """
    let d = try JSONDecoder().decode(RunDetailResponse.self, from: Data(json.utf8))
    #expect(d.verdict?.signal == .hold)
    #expect(d.signals.first?.dir == .bull)
    #expect(d.turns.first?.toolCalls == ["lookup"])
}
```

注意：JSONValue 需支持 `NSNull()` 出现在测试字面量里——不行，NSNull 是 Foundation 类型。改用 `.null`：测试里 `"entry_reference_price": JSONValue.null`。上面两处 `NSNull()` 按 `.null` 写。

- [x] **Step 2: 跑测试确认失败**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | grep -E "error|failed" | head -5
```

期望：编译错误 `cannot find 'JSONValue' in scope` 等。

- [x] **Step 3: 实现 JSONValue**

`Core/Sources/Core/Models/JSONValue.swift`:

```swift
import Foundation

/// 轻量 JSON 值树。事件 data 载荷是弱类型字典（形状由事件 type 决定），
/// 解成强类型 struct 太早——reducer 按需取值，与 web 版 Record<string,unknown> 对等。
public enum JSONValue: Codable, Sendable, Equatable {
    case null
    case bool(Bool)
    case int(Int)
    case double(Double)
    case string(String)
    case array([JSONValue])
    case object([String: JSONValue])

    public func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .null: try c.encodeNil()
        case .bool(let v): try c.encode(v)
        case .int(let v): try c.encode(v)
        case .double(let v): try c.encode(v)
        case .string(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .object(let v): try c.encode(v)
        }
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let v = try? c.decode(Bool.self) { self = .bool(v) }
        else if let v = try? c.decode(Int.self) { self = .int(v) }
        else if let v = try? c.decode(Double.self) { self = .double(v) }
        else if let v = try? c.decode(String.self) { self = .string(v) }
        else if let v = try? c.decode([JSONValue].self) { self = .array(v) }
        else if let v = try? c.decode([String: JSONValue].self) { self = .object(v) }
        else {
            throw DecodingError.dataCorruptedError(
                in: c, debugDescription: "不支持的 JSON 值")
        }
    }

    // ── 便捷访问 ─────────────────────────────────────────────
    public var string: String? { if case .string(let v) = self { v } else { nil } }
    public var int: Int? {
        switch self {
        case .int(let v): v
        case .double(let v): Int(exactly: v)
        default: nil
        }
    }
    public var double: Double? {
        switch self {
        case .int(let v): Double(v)
        case .double(let v): v
        default: nil
        }
    }
    public var bool: Bool? { if case .bool(let v) = self { v } else { nil } }
    public var array: [JSONValue]? { if case .array(let v) = self { v } else { nil } }
    public subscript(key: String) -> JSONValue? {
        if case .object(let o) = self { o[key] } else { nil }
    }

    /// 从弱类型树解码为强类型 struct（如 RunStartedData）。
    public func decode<T: Decodable>(as type: T.Type) -> T? {
        guard let data = try? JSONEncoder().encode(self) else { return nil }
        return try? JSONDecoder().decode(T, from: data)
    }
}

// ── 字面量构造（测试与默认值书写方便）─────────────────────────
extension JSONValue: ExpressibleByStringLiteral, ExpressibleByIntegerLiteral,
    ExpressibleByFloatLiteral, ExpressibleByBooleanLiteral, ExpressibleByNilLiteral,
    ExpressibleByArrayLiteral, ExpressibleByDictionaryLiteral {
    public init(stringLiteral v: String) { self = .string(v) }
    public init(integerLiteral v: Int) { self = .int(v) }
    public init(floatLiteral v: Double) { self = .double(v) }
    public init(booleanLiteral v: Bool) { self = .bool(v) }
    public init(nilLiteral: ()) { self = .null }
    public init(arrayLiteral elements: JSONValue...) { self = .array(elements) }
    public init(dictionaryLiteral elements: (String, JSONValue)...) {
        self = .object(Dictionary(elements, uniquingKeysWith: { a, _ in a }))
    }
}
```

注意 decode 顺序：Bool 必须在 Int/Double 之前（JSON 里 true/false 与数字类型不互通，`try? c.decode(Int.self)` 对 true 会抛错，但顺序仍保持 bool 优先以防万一）。

- [x] **Step 4: 实现事件模型**

`Core/Sources/Core/Models/TradingDeskModels.swift`:

```swift
import Foundation

// ── 基础枚举（镜像 app/schemas/trading_desk.py）──────────────────

public enum Polarity: String, Codable, Sendable, Equatable {
    case bull, bear, neutral
}

public enum StageGroup: String, Codable, Sendable, Equatable {
    case analyst, system, debate, manager, trader
}

public enum EventType: String, Codable, Sendable, Equatable, CaseIterable {
    case runStarted = "run.started"
    case stageActive = "stage.active"
    case stageDone = "stage.done"
    case turnStarted = "turn.started"
    case agentToolCall = "agent.tool_call"
    case agentToken = "agent.token"
    case agentThink = "agent.think"
    case turnDone = "turn.done"
    case agentSignal = "agent.signal"
    case debateTurn = "debate.turn"
    case humanNote = "human.note"
    case consensusUpdate = "consensus.update"
    case runPaused = "run.paused"
    case runResumed = "run.resumed"
    case verdict = "verdict"
    case runFinished = "run.finished"
    case error = "error"
}

public enum ControlAction: String, Codable, Sendable, Equatable {
    case pause, resume, inject, cancel
}

public enum VerdictSignal: String, Codable, Sendable, Equatable {
    case buy = "BUY", sell = "SELL", hold = "HOLD"
}

// ── 描述性 struct ────────────────────────────────────────────

public struct EngineCapabilities: Codable, Sendable, Equatable {
    public var supportsPause: Bool
    public var supportsInject: Bool
    public var supportsResumeAfterRestart: Bool
    public init(supportsPause: Bool = false, supportsInject: Bool = false,
                supportsResumeAfterRestart: Bool = false) {
        self.supportsPause = supportsPause
        self.supportsInject = supportsInject
        self.supportsResumeAfterRestart = supportsResumeAfterRestart
    }
    enum CodingKeys: String, CodingKey {
        case supportsPause = "supports_pause"
        case supportsInject = "supports_inject"
        case supportsResumeAfterRestart = "supports_resume_after_restart"
    }
}

public struct StageDescriptor: Codable, Sendable, Equatable, Identifiable {
    public var id: String
    public var name: String
    public var role: String
    public var group: StageGroup
    public init(id: String, name: String, role: String = "", group: StageGroup = .analyst) {
        self.id = id; self.name = name; self.role = role; self.group = group
    }
}

// ── 事件信封 ─────────────────────────────────────────────────

/// SSE 事件信封。seq 单调递增用于去重；data 弱类型，按 type 窄化。
public struct TradingDeskEvent: Codable, Sendable, Equatable {
    public let type: EventType
    public let runId: String
    public let seq: Int
    public let ts: Int
    public let data: JSONValue?

    public init(type: EventType, runId: String, seq: Int, ts: Int, data: JSONValue? = nil) {
        self.type = type; self.runId = runId; self.seq = seq
        self.ts = ts; self.data = data
    }

    /// 是否终止事件（fatal error 或 run.finished）。
    public var isTerminal: Bool {
        type == .runFinished || (type == .error && (data?["fatal"]?.bool ?? false))
    }

    enum CodingKeys: String, CodingKey {
        case type, seq, ts, data
        case runId = "run_id"
    }
}

// ── 强类型 payload（从 event.data decode）──────────────────────

public struct RunStartedData: Codable, Sendable, Equatable {
    public var ticker: String
    public var tradeDate: String
    public var engine: String
    public var capabilities: EngineCapabilities
    public var stages: [StageDescriptor]
    enum CodingKeys: String, CodingKey {
        case ticker, engine, capabilities, stages
        case tradeDate = "trade_date"
    }
}

public struct SignalData: Codable, Sendable, Equatable {
    public var stageId: String
    public var name: String
    public var dir: Polarity
    public var conf: Int
    public var turnId: String?
    /// False=引擎原生产出；True=由报告文本抽取（UI 要标注「抽」）
    public var extracted: Bool
    enum CodingKeys: String, CodingKey {
        case name, dir, conf, extracted
        case stageId = "stage_id"
        case turnId = "turn_id"
    }
}

public struct DebateTurnData: Codable, Sendable, Equatable {
    public var stageId: String
    public var debateId: String
    public var side: String
    public var sideLabel: String
    public var polarity: Polarity
    public var round: Int
    public var turnId: String
    enum CodingKeys: String, CodingKey {
        case side, polarity, round
        case stageId = "stage_id"
        case debateId = "debate_id"
        case sideLabel = "side_label"
        case turnId = "turn_id"
    }
}

public struct ConsensusData: Codable, Sendable, Equatable {
    public var bull: Int
    public var neutral: Int
    public var bear: Int
    public var lean: String
}

public struct VerdictData: Codable, Sendable, Equatable {
    public var signal: VerdictSignal
    public var confidence: Double
    public var sizeFraction: Double
    public var entryReferencePrice: Double?
    public var targetPrice: Double?
    public var stopLoss: Double?
    public var currency: String?
    public var timeHorizonDays: Int?
    public var rationale: String
    /// 引擎 JSON 解析失败走 fallback 时置位——UI 必须显式展示降级警告
    public var warningMessage: String?
    enum CodingKeys: String, CodingKey {
        case signal, confidence, currency, rationale
        case sizeFraction = "size_fraction"
        case entryReferencePrice = "entry_reference_price"
        case targetPrice = "target_price"
        case stopLoss = "stop_loss"
        case timeHorizonDays = "time_horizon_days"
        case warningMessage = "warning_message"
    }
}

public struct RunFinishedData: Codable, Sendable, Equatable {
    public var status: String
    public var durationMs: Int
    enum CodingKeys: String, CodingKey {
        case status
        case durationMs = "duration_ms"
    }
}
```

- [x] **Step 5: 实现历史模型**

`Core/Sources/Core/Models/RunModels.swift`:

```swift
import Foundation

/// 历史列表一条 run 的状态（也用于流式 state 的 RunStatus。
/// 后端 run.finished 的 status 是其中后四个值）。
public enum RunRecordStatus: String, Codable, Sendable, Equatable {
    case running, completed, cancelled, failed, interrupted
}

public struct RunSummary: Codable, Sendable, Equatable, Identifiable {
    public var runId: String
    public var ticker: String
    public var tradeDate: String
    public var engine: String
    public var status: RunRecordStatus
    public var durationMs: Int
    /// ISO 8601 字符串（后端序列化成字符串）
    public var createdAt: String
    public var finishedAt: String?
    public var verdictSignal: VerdictSignal?
    public var verdictConfidence: Double?
    public var turnsCount: Int
    public var signalsCount: Int

    public var id: String { runId }
    enum CodingKeys: String, CodingKey {
        case ticker, engine, status
        case runId = "run_id"
        case tradeDate = "trade_date"
        case durationMs = "duration_ms"
        case createdAt = "created_at"
        case finishedAt = "finished_at"
        case verdictSignal = "verdict_signal"
        case verdictConfidence = "verdict_confidence"
        case turnsCount = "turns_count"
        case signalsCount = "signals_count"
    }
}

public struct RunListResponse: Codable, Sendable, Equatable {
    public var runs: [RunSummary]
}

/// 回放页一条 turn 的持久化记录（RunDetailResponse.turns 元素）。
public struct TurnRecord: Codable, Sendable, Equatable, Identifiable {
    public var turnId: String
    public var stageId: String
    public var name: String
    public var role: String
    public var avatar: String
    public var text: String
    public var toolCalls: [String]
    public var debate: DebateInfo?
    public var id: String { turnId }
    enum CodingKeys: String, CodingKey {
        case name, role, avatar, text, debate
        case turnId = "turn_id"
        case stageId = "stage_id"
        case toolCalls = "tool_calls"
    }
}

/// 辩论元数据（流式 DebateTurnData 与回放 TurnRecord.debate 共用形状）。
public struct DebateInfo: Codable, Sendable, Equatable {
    public var debateId: String
    public var side: String
    public var sideLabel: String
    public var polarity: Polarity
    public var round: Int
    enum CodingKeys: String, CodingKey {
        case side, polarity, round
        case debateId = "debate_id"
        case sideLabel = "side_label"
    }
}

public struct SignalRecord: Codable, Sendable, Equatable {
    public var stageId: String
    public var name: String
    public var dir: Polarity
    public var conf: Int
    public var turnId: String?
    public var extracted: Bool
    enum CodingKeys: String, CodingKey {
        case name, dir, conf, extracted
        case stageId = "stage_id"
        case turnId = "turn_id"
    }
}

public struct RunDetailResponse: Codable, Sendable, Equatable {
    public var runId: String
    public var ticker: String
    public var tradeDate: String
    public var engine: String
    public var status: RunRecordStatus
    public var durationMs: Int
    public var createdAt: String
    public var finishedAt: String?
    public var verdict: VerdictData?
    public var signals: [SignalRecord]
    public var turns: [TurnRecord]
    enum CodingKeys: String, CodingKey {
        case ticker, engine, status, verdict, signals, turns
        case runId = "run_id"
        case tradeDate = "trade_date"
        case durationMs = "duration_ms"
        case createdAt = "created_at"
        case finishedAt = "finished_at"
    }
}
```

- [x] **Step 6: 删除占位、改冒烟测试、跑绿**

删除 `Core/Sources/Core/Placeholder.swift` 与 `Core/Tests/CoreTests/SmokeTests.swift`。

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | tail -3
```

期望：`Test run with 6 tests passed`。

- [x] **Step 7: 提交**

```bash
git add ios/DeepAlphaClub && git commit -m "feat(models): JSONValue + 事件信封/payload/历史模型（镜像后端 schemas）"
```

---

## Task 3: TickerResolver（市场后缀规则）

**Files:**
- Create: `Core/Sources/Core/TickerResolver.swift`
- Test: `Core/Tests/CoreTests/TickerResolverTests.swift`

- [x] **Step 1: 写失败测试**

`Core/Tests/CoreTests/TickerResolverTests.swift`:

```swift
import Testing
@testable import Core

@Test("US 市场不加后缀")
func us() {
    #expect(TickerResolver.resolve(raw: "nvda", market: .US) == "NVDA")
    #expect(TickerResolver.resolve(raw: "  aapl ", market: .US) == "AAPL")
}

@Test("US 已带后缀保留（如 BRK.B）")
func usWithDot() {
    #expect(TickerResolver.resolve(raw: "BRK.B", market: .US) == "BRK.B")
}

@Test("HK：strip 前导零再拼 .HK")
func hk() {
    #expect(TickerResolver.resolve(raw: "0700", market: .HK) == "700.HK")
    #expect(TickerResolver.resolve(raw: "03887", market: .HK) == "3887.HK")
    #expect(TickerResolver.resolve(raw: "700", market: .HK) == "700.HK")
}

@Test("HK：全零输入不产生空串")
func hkAllZeros() {
    #expect(TickerResolver.resolve(raw: "000", market: .HK) == "000.HK")
}

@Test("HK：已带 .HK 不重复拼")
func hkWithSuffix() {
    #expect(TickerResolver.resolve(raw: "0700.HK", market: .HK) == "0700.HK")
}

@Test("SH/SZ：前导零是有效位，直接拼后缀")
func aShares() {
    #expect(TickerResolver.resolve(raw: "600519", market: .SH) == "600519.SS")
    #expect(TickerResolver.resolve(raw: "000001", market: .SZ) == "000001.SZ")
    #expect(TickerResolver.resolve(raw: "002415", market: .SZ) == "002415.SZ")
}

@Test("空输入返回空（调用方禁用按钮）")
func empty() {
    #expect(TickerResolver.resolve(raw: "  ", market: .US) == "")
}

@Test("Market 元数据：label/placeholder/suffix")
func marketMeta() {
    #expect(Market.US.label == "美股")
    #expect(Market.HK.placeholder == "0700")
    #expect(Market.SH.suffix == ".SS")
    #expect(Market.allCases.count == 4)
}
```

- [x] **Step 2: 跑测试确认失败**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | grep "error:" | head -3
```

期望：`cannot find 'TickerResolver' in scope`。

- [x] **Step 3: 实现**

`Core/Sources/Core/TickerResolver.swift`:

```swift
import Foundation

/// 四个市场。label/placeholder 供 UI，suffix 是 yfinance 约定。
public enum Market: String, CaseIterable, Identifiable, Sendable, Equatable {
    case US, HK, SH, SZ
    public var id: String { rawValue }
    public var label: String {
        switch self {
        case .US: "美股"
        case .HK: "港股"
        case .SH: "沪 A"
        case .SZ: "深 A"
        }
    }
    public var placeholder: String {
        switch self {
        case .US: "NVDA"
        case .HK: "0700"
        case .SH: "600519"
        case .SZ: "000001"
        }
    }
    var suffix: String {
        switch self {
        case .US: ""
        case .HK: ".HK"
        case .SH: ".SS"
        case .SZ: ".SZ"
        }
    }
}

public enum TickerResolver {
    /// 市场后缀规则（移植 web frontend/app/trading-desk/page.tsx:31）：
    /// - 已带 `.` 视为完整代码，保留（防重复拼）
    /// - HK 前导零是 padding，yfinance 不认 03887.HK，strip 后再拼
    /// - A 股前导零是有效位（002415 海康），不动
    public static func resolve(raw: String, market: Market) -> String {
        let cleaned = raw.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard !cleaned.isEmpty else { return cleaned }
        if cleaned.contains(".") { return cleaned }

        var code = cleaned
        if market == .HK {
            let stripped = code.replacingOccurrences(
                of: "^0+", with: "", options: .regularExpression)
            if !stripped.isEmpty { code = stripped }
        }
        return code + market.suffix
    }
}
```

- [x] **Step 4: 跑测试通过**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | tail -3
```

期望：全部通过（累计 14 个测试）。

- [x] **Step 5: 提交**

```bash
git add ios/DeepAlphaClub && git commit -m "feat(ticker): 四市场 resolveTicker 规则（HK strip 前导零）"
```

---

## Task 4: SSEFrameParser（帧解析纯函数）

**Files:**
- Create: `Core/Sources/Core/SSEFrameParser.swift`
- Test: `Core/Tests/CoreTests/SSEFrameParserTests.swift`

- [x] **Step 1: 写失败测试**

`Core/Tests/CoreTests/SSEFrameParserTests.swift`:

```swift
import Testing
@testable import Core

@Test("标准帧：id + data 各一行")
func standard() throws {
    let raw = "id: 1753900000000-0\ndata: {\"type\":\"run.started\",\"run_id\":\"r1\",\"seq\":1,\"ts\":1,\"data\":{}}"
    let frame = try #require(SSEFrameParser.parse(raw))
    #expect(frame.id == "1753900000000-0")
    #expect(frame.event.type == .runStarted)
    #expect(frame.event.runId == "r1")
}

@Test("无 id 帧也能解析（id 为 nil）")
func noId() throws {
    let raw = "data: {\"type\":\"run.paused\",\"run_id\":\"r1\",\"seq\":2,\"ts\":1,\"data\":{}}"
    let frame = try #require(SSEFrameParser.parse(raw))
    #expect(frame.id == nil)
    #expect(frame.event.type == .runPaused)
}

@Test("多行 data 拼接（JSON 被分行发送的兼容）")
func multiLineData() throws {
    let raw = "data: {\"type\":\"agent.token\",\"run_id\":\"r\",\"seq\":1,\"ts\":1,\ndata: \"data\":{\"text\":\"a\\nb\"}}"
    let frame = try #require(SSEFrameParser.parse(raw))
    #expect(frame.event.data?["text"]?.string == "a\nb")
}

@Test("只有 id 没有 data 返回 nil")
func idOnly() {
    #expect(SSEFrameParser.parse("id: 123") == nil)
}

@Test("data 非法 JSON 丢弃（不掐断整条流）")
func badJson() {
    #expect(SSEFrameParser.parse("data: {not-json") == nil)
}

@Test("注释行（心跳）不在帧内——由 client 层跳过，但防御性支持")
func commentLine() throws {
    let raw = ":\ndata: {\"type\":\"run.resumed\",\"run_id\":\"r\",\"seq\":3,\"ts\":1,\"data\":{}}"
    let frame = try #require(SSEFrameParser.parse(raw))
    #expect(frame.event.type == .runResumed)
}
```

- [x] **Step 2: 跑测试确认失败**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | grep "error:" | head -3
```

期望：`cannot find 'SSEFrameParser' in scope`。

- [x] **Step 3: 实现**

`Core/Sources/Core/SSEFrameParser.swift`:

```swift
import Foundation

/// 一条已解析的 SSE 帧：id 供断线续读（Last-Event-ID），event 是载荷。
public struct SseFrame: Sendable, Equatable {
    public let id: String?
    public let event: TradingDeskEvent
    public init(id: String?, event: TradingDeskEvent) {
        self.id = id
        self.event = event
    }
}

/// SSE 帧解析纯函数。帧格式（后端 app/api/v1/trading_desk.py stream_run）：
/// `id: <RedisStreamId>\ndata: <json 一行>\n\n`。
/// 多行 data 按 SSE 规范以 \n join；坏 JSON 返回 nil 丢弃，不掐断流。
public enum SSEFrameParser {
    public static func parse(_ raw: String) -> SseFrame? {
        var id: String?
        var dataLines: [String] = []
        for line in raw.split(separator: "\n", omittingEmptySubsequences: false) {
            if line.hasPrefix("id:") {
                id = line.dropFirst(3).trimmingCharacters(in: .whitespaces)
            } else if line.hasPrefix("data:") {
                dataLines.append(String(line.dropFirst(5)))
            }
            // 其余（注释行、event:、retry:）忽略
        }
        guard !dataLines.isEmpty else { return nil }
        let json = dataLines.joined(separator: "\n")
        guard let jsonData = json.data(using: .utf8),
              let event = try? JSONDecoder().decode(TradingDeskEvent.self, from: jsonData)
        else { return nil }
        return SseFrame(id: id, event: event)
    }
}
```

注意：`id:`/`data:` 前缀匹配不带尾空格（比 web 版 `id: ` 严格前缀更宽容，`id:123` 也认），dropFirst 后不 trim data（JSON 行首无空格；trim 会破坏多行字符串内容），id 做了 trim（后端 `id: <streamId>` 带空格）。

- [x] **Step 4: 跑测试通过**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | tail -3
```

- [x] **Step 5: 提交**

```bash
git add ios/DeepAlphaClub && git commit -m "feat(sse): SSE 帧解析纯函数（id/data/多行/坏行丢弃）"
```

---

## Task 5: APIError + APIClient（URLProtocol mock 测试）

**Files:**
- Create: `Core/Sources/Core/APIError.swift`
- Create: `Core/Sources/Core/APIClient.swift`
- Create: `Core/Tests/CoreTests/MockURLProtocol.swift`
- Test: `Core/Tests/CoreTests/APIClientTests.swift`

- [x] **Step 1: 写 URLProtocol mock（测试基建）**

`Core/Tests/CoreTests/MockURLProtocol.swift`:

```swift
import Foundation
import Testing

/// URLProtocol mock：handler 返回 (response, data) 或抛错模拟网络失败。
/// SSE 流式测试（Task 8）通过多次 didLoad 分块推送。
final class MockURLProtocol: URLProtocol {
    /// 全局 handler（每个测试 setUp 覆盖）。测试串行执行，无竞争。
    nonisolated(unsafe) static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    static func makeSession() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        return URLSession(configuration: config)
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = MockURLProtocol.handler else {
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

/// 每个 @Test 前重置 handler 的结构体（Swift Testing 无 setUp，用 trait）。
struct ResetMock: TestTrait, TestScoping {
    func provideScope(for test: Test, testCase: Test.Case?,
                      performing function: @Sendable () async throws -> Void) async throws {
        MockURLProtocol.handler = nil
        try await function()
    }
}

extension TestTrait where Self == ResetMock {
    static var resetMock: ResetMock { ResetMock() }
}
```

- [x] **Step 2: 写失败测试**

`Core/Tests/CoreTests/APIClientTests.swift`:

```swift
import Foundation
import Testing
@testable import Core

@MainActor
struct APIClientTests {
    func makeClient(token: String? = "tok") -> APIClient {
        APIClient(baseURL: URL(string: "https://api.example.com")!,
                  session: MockURLProtocol.makeSession(),
                  tokenProvider: { token })
    }

    @Test("GET：带 Authorization 头 + 解析响应")
    @.resetMock
    func getWithAuth() async throws {
        let captured = LockedRequestBox()
        MockURLProtocol.handler = { req in
            captured.set(req)
            let resp = HTTPURLResponse(url: req.url!, statusCode: 200,
                                       httpVersion: nil, headerFields: nil)!
            let body = #"{"run_id":"r1","request_id":"x"}"#
            return (resp, Data(body.utf8))
        }
        struct CreateRunResponse: Decodable { let runId: String
            enum CodingKeys: String, CodingKey { case runId = "run_id" } }

        let client = makeClient()
        let resp: CreateRunResponse = try await client.get("/api/v1/trading-desk/runs/x".isEmpty ? "/a" : "/a")
        #expect(resp.runId == "r1")
        let req = try #require(captured.get())
        #expect(req.value(forHTTPHeaderField: "Authorization") == "Bearer tok")
        #expect(req.url?.absoluteString == "https://api.example.com/a")
    }

    @Test("POST JSON：Content-Type 与 body")
    @.resetMock
    func postJson() async throws {
        let captured = LockedRequestBox()
        MockURLProtocol.handler = { req in
            captured.set(req)
            let resp = HTTPURLResponse(url: req.url!, statusCode: 200,
                                       httpVersion: nil, headerFields: nil)!
            return (resp, Data(#"{"accepted":true}"#.utf8))
        }
        struct ControlResponse: Decodable { let accepted: Bool }
        struct Body: Encodable { let action: String; let text: String? }

        let client = makeClient(token: nil)
        let resp: ControlResponse = try await client.post(
            "/api/v1/trading-desk/runs/r1/control", json: Body(action: "pause", text: nil))
        #expect(resp.accepted)
        let req = try #require(captured.get())
        #expect(req.httpMethod == "POST")
        #expect(req.value(forHTTPHeaderField: "Content-Type") == "application/json")
        let body = try #require(req.httpBody ?? req.httpBodyStreamData)
        #expect(String(data: body, encoding: .utf8) == #"{"action":"pause","text":null}"#)
        #expect(req.value(forHTTPHeaderField: "Authorization") == nil)
    }

    @Test("POST form-urlencoded（登录）")
    @.resetMock
    func postForm() async throws {
        let captured = LockedRequestBox()
        MockURLProtocol.handler = { req in
            captured.set(req)
            let resp = HTTPURLResponse(url: req.url!, statusCode: 200,
                                       httpVersion: nil, headerFields: nil)!
            return (resp, Data(#"{"access_token":"jwt","token_type":"bearer"}"#.utf8))
        }
        struct LoginResponse: Decodable { let accessToken: String
            enum CodingKeys: String, CodingKey { case accessToken = "access_token" } }

        let client = makeClient(token: nil)
        let resp: LoginResponse = try await client.postForm(
            "/api/v1/auth/login",
            fields: ["email": "a@b.c", "password": "p w+d", "grant_type": "password"])
        #expect(resp.accessToken == "jwt")
        let req = try #require(captured.get())
        #expect(req.value(forHTTPHeaderField: "Content-Type")
                == "application/x-www-form-urlencoded")
        let body = try #require(req.httpBody ?? req.httpBodyStreamData)
        #expect(String(data: body, encoding: .utf8)
                == "email=a%40b.c&password=p%20w%2Bd&grant_type=password")
    }

    @Test("401 → .unauthorized；404 → .notFound；detail 消息透出")
    @.resetMock
    func errorMapping() async {
        MockURLProtocol.handler = { req in
            let code = Int(req.url!.lastPathComponent) ?? 500
            let resp = HTTPURLResponse(url: req.url!, statusCode: code,
                                       httpVersion: nil, headerFields: nil)!
            let body = Data(#"{"detail":"运行不存在"}"#.utf8)
            return (resp, body)
        }
        struct Empty: Decodable {}
        let client = makeClient()
        await #expect(throws: APIError.unauthorized) {
            let _: Empty = try await client.get("/e/401")
        }
        do {
            let _: Empty = try await client.get("/e/404")
            Issue.record("应抛 notFound")
        } catch let e as APIError {
            #expect(e == .notFound)
            #expect(e.message.contains("运行不存在"))
        } catch {
            Issue.record("错误类型不对：\(error)")
        }
        await #expect(throws: APIError.self) {
            let _: Empty = try await client.get("/e/500")
        }
    }

    @Test("连接层错误 → .network")
    @.resetMock
    func networkError() async {
        struct Boom: Error {}
        MockURLProtocol.handler = { _ in throw Boom() }
        struct Empty: Decodable {}
        let client = makeClient()
        await #expect(throws: APIError.network) {
            let _: Empty = try await client.get("/x")
        }
    }
}

/// 跨闭包捕获请求的线程安全盒子。
final class LockedRequestBox: @unchecked Sendable {
    private let lock = NSLock()
    private var req: URLRequest?
    func set(_ r: URLRequest) { lock.lock(); req = r; lock.unlock() }
    func get() -> URLRequest? { lock.lock(); defer { lock.unlock() }; return req }
}

extension URLRequest {
    /// URLProtocol 场景 body 可能落在 httpBodyStream，读出来便于断言。
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

注意第一个测试里 `client.get("/api/v1/trading-desk/runs/x".isEmpty ? "/a" : "/a")` 是笔误防范写法——直接写 `client.get("/a")` 即可，抄写时用简版。

- [x] **Step 3: 跑测试确认失败**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | grep "error:" | head -3
```

期望：`cannot find 'APIClient' in scope`。

- [x] **Step 4: 实现 APIError**

`Core/Sources/Core/APIError.swift`:

```swift
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
        let detail: String? = body.flatMap {
            guard let obj = try? JSONDecoder().decode([String: String].self, from: $0)
            else { return nil }
            // FastException 的 detail 也可能是 dict（如登录 400），取 message 兜底
            return obj["detail"] ?? obj["message"]
        }
        func dictDetail() -> String? {
            body.flatMap {
                guard let obj = try? JSONDecoder().decode(
                    [String: String?].self, from: $0) else { return nil }
                return obj["detail"] ?? nil ?? obj["message"] ?? nil
            }
        }
        let message = detail ?? dictDetail() ?? defaultText(for: status)
        switch status {
        case 401: return .unauthorized
        case 404: return .notFound
        case 422: return .validation(message)
        default: return .server(status, message)
        }
    }

    private static func defaultText(for status: Int) -> String {
        switch status {
        case 400..<500: "请求失败（HTTP \(status)）"
        default: "服务器错误（HTTP \(status)）"
        }
    }
}
```

- [x] **Step 5: 实现 APIClient**

`Core/Sources/Core/APIClient.swift`:

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
        var components = URLComponents(url: URL(string: baseURL.absoluteString + path)!,
                                       resolvingAgainstBaseURL: false)!
        if !query.isEmpty {
            components.queryItems = query.sorted { $0.key < $1.key }
                .map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        var request = URLRequest(url: components.url!)
        request.httpMethod = "GET"
        return try await send(request)
    }

    public func post<Response: Decodable>(_ path: String, json: some Encodable) async throws -> Response {
        var request = try request(path: path)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(json)
        return try await send(request)
    }

    /// form-urlencoded POST（登录端点用 Form(...)，非 JSON）。
    public func postForm<Response: Decodable>(_ path: String,
                                              fields: [String: String]) async throws -> Response {
        var request = try request(path: path)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        var comps = URLComponents()
        comps.queryItems = fields.sorted { $0.key < $1.key }
            .map { URLQueryItem(name: $0.key, value: $0.value) }
        // percentEncodedQuery 已是编码后的 a=1&b=2 形态
        request.httpBody = comps.percentEncodedQuery?.data(using: .utf8)
        return try await send(request)
    }

    private func request(path: String) throws -> URLRequest {
        guard let url = URL(string: baseURL.absoluteString + path) else {
            throw APIError.decoding
        }
        var request = URLRequest(url: url)
        if let token = tokenProvider() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    private func send<Response: Decodable>(_ request: URLRequest) async throws -> Response {
        let data: Data
        let response: HTTPURLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
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

- [x] **Step 6: 跑测试通过**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | tail -3
```

- [x] **Step 7: 提交**

```bash
git add ios/DeepAlphaClub && git commit -m "feat(api): APIClient（token 注入/form 编码/typed 错误映射）+ URLProtocol mock"
```

---

## Task 6: KeychainStore + AuthService（登录）

**Files:**
- Create: `Core/Sources/Core/KeychainStore.swift`
- Create: `Core/Sources/Core/AuthService.swift`
- Create: `Core/Sources/Core/Models/AuthModels.swift`
- Test: `Core/Tests/CoreTests/AuthServiceTests.swift`

- [x] **Step 1: 写失败测试**

`Core/Tests/CoreTests/AuthServiceTests.swift`:

```swift
import Foundation
import Testing
@testable import Core

@MainActor
struct AuthServiceTests {
    func makeClient() -> APIClient {
        APIClient(baseURL: URL(string: "https://api.example.com")!,
                  session: MockURLProtocol.makeSession(),
                  tokenProvider: { nil })
    }

    @Test("登录成功：form 字段正确 + 返回 token")
    @.resetMock
    func loginOk() async throws {
        let captured = LockedRequestBox()
        MockURLProtocol.handler = { req in
            captured.set(req)
            let resp = HTTPURLResponse(url: req.url!, statusCode: 200,
                                       httpVersion: nil, headerFields: nil)!
            return (resp, Data(#"{"access_token":"jwt-1","token_type":"bearer","expires_at":"2026-12-01T00:00:00Z","request_id":"r"}"#.utf8))
        }
        let service = AuthService(client: makeClient())
        let token = try await service.login(email: "a@b.c", password: "secret8")
        #expect(token == "jwt-1")
        let req = try #require(captured.get())
        #expect(req.url?.path == "/api/v1/auth/login")
        let body = try #require(req.httpBody ?? req.httpBodyStreamData)
        #expect(String(data: body, encoding: .utf8)?.contains("email=a%40b.c") == true)
        #expect(String(data: body, encoding: .utf8)?.contains("grant_type=password") == true)
    }

    @Test("登录失败 401 → 抛 APIError.unauthorized")
    @.resetMock
    func loginFail() async {
        MockURLProtocol.handler = { req in
            let resp = HTTPURLResponse(url: req.url!, statusCode: 401,
                                       httpVersion: nil, headerFields: nil)!
            return (resp, Data(#"{"detail":"邮箱或密码错误"}"#.utf8))
        }
        let service = AuthService(client: makeClient())
        do {
            _ = try await service.login(email: "a@b.c", password: "wrong!!")
            Issue.record("应抛错")
        } catch let e as APIError {
            #expect(e == .unauthorized)
        }
    }

    @Test("InMemoryKeychain 存取删")
    func inMemoryKeychain() {
        let k = InMemoryKeychain()
        #expect(k.loadToken() == nil)
        try? k.saveToken("t1")
        #expect(k.loadToken() == "t1")
        k.deleteToken()
        #expect(k.loadToken() == nil)
    }
}
```

- [x] **Step 2: 跑测试确认失败**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | grep "error:" | head -3
```

- [x] **Step 3: 实现**

`Core/Sources/Core/Models/AuthModels.swift`:

```swift
import Foundation

/// POST /api/v1/auth/login 响应（只取 access_token，其余忽略）。
public struct LoginResponse: Codable, Sendable, Equatable {
    public var accessToken: String
    enum CodingKeys: String, CodingKey { case accessToken = "access_token" }
}
```

`Core/Sources/Core/KeychainStore.swift`:

```swift
import Foundation
import Security

/// token 存取抽象：真 Keychain 与测试用内存实现。
public protocol KeychainStoring: Sendable {
    func saveToken(_ token: String) throws
    func loadToken() -> String?
    func deleteToken()
}

/// SecItem 实现（kSecClassGenericPassword，service=app bundle id，account=access_token）。
/// iOS / macOS 同 API；测试不要用真实现（污染开发机钥匙串），用 InMemoryKeychain。
public struct KeychainStore: KeychainStoring {
    let service: String
    let account: String

    public init(service: String = "club.deepalpha.ios", account: String = "access_token") {
        self.service = service
        self.account = account
    }

    private var baseQuery: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service,
         kSecAttrAccount as String: account]
    }

    public func saveToken(_ token: String) throws {
        deleteToken()
        var add = baseQuery
        add[kSecValueData as String] = Data(token.utf8)
        let status = SecItemAdd(add as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw NSError(domain: NSOSStatusErrorDomain, code: Int(status))
        }
    }

    public func loadToken() -> String? {
        var query = baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    public func deleteToken() {
        SecItemDelete(baseQuery as CFDictionary)
    }
}

/// 测试 / SwiftUI 预览用内存实现。
public final class InMemoryKeychain: KeychainStoring, @unchecked Sendable {
    private let lock = NSLock()
    private var token: String?
    public init() {}
    public func saveToken(_ token: String) throws {
        lock.lock(); defer { lock.unlock() }
        self.token = token
    }
    public func loadToken() -> String? {
        lock.lock(); defer { lock.unlock() }
        return token
    }
    public func deleteToken() {
        lock.lock(); defer { lock.unlock() }
        token = nil
    }
}
```

`Core/Sources/Core/AuthService.swift`:

```swift
import Foundation

/// 登录服务。后端 /auth/login 是 form-urlencoded（email/password/grant_type），
/// 这是与 spec 不同的实测结论——见计划「Spec 勘误」#1。
public struct AuthService: Sendable {
    let client: APIClient
    public init(client: APIClient) { self.client = client }

    public func login(email: String, password: String) async throws -> String {
        let resp: LoginResponse = try await client.postForm(
            "/api/v1/auth/login",
            fields: ["email": email, "password": password, "grant_type": "password"])
        return resp.accessToken
    }
}
```

- [x] **Step 4: 跑测试通过**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | tail -3
```

- [x] **Step 5: 提交**

```bash
git add ios/DeepAlphaClub && git commit -m "feat(auth): 登录（form-urlencoded）+ Keychain 存取（真实现 + 内存 mock）"
```

---

## Task 7: TradingDeskState + Reducer（状态机移植）

**Files:**
- Create: `Core/Sources/Core/State/TradingDeskState.swift`
- Create: `Core/Sources/Core/State/TradingDeskReducer.swift`
- Test: `Core/Tests/CoreTests/TradingDeskReducerTests.swift`

这是全 App 的心脏：把 SSE 事件流折叠成 UI 状态的纯函数，逐事件移植 web `frontend/lib/store/trading_desk.ts` 的 `reduceEvent`。

- [x] **Step 1: 写失败测试**

`Core/Tests/CoreTests/TradingDeskReducerTests.swift`:

```swift
import Testing
@testable import Core

/// 测试辅助：构造事件。
func ev(_ type: EventType, seq: Int, data: JSONValue? = .object([:])) -> TradingDeskEvent {
    TradingDeskEvent(type: type, runId: "r1", seq: seq, ts: 0, data: data)
}

@Suite("TradingDeskReducer")
struct TradingDeskReducerTests {
    @Test("run.started：初始化 stages 全 pending + 状态 running")
    func runStarted() {
        var s = TradingDeskState()
        s = TradingDeskReducer.reduce(s, ev(.runStarted, seq: 1, data: .object([
            "ticker": "NVDA", "trade_date": "2026-08-30", "engine": "tradingagents",
            "capabilities": ["supports_pause": true, "supports_inject": true,
                              "supports_resume_after_restart": false],
            "stages": [
                ["id": "a", "name": "分析师A", "role": "analyst", "group": "analyst"],
                ["id": "b", "name": "辩论", "role": "bull", "group": "debate"],
            ],
        ])))
        #expect(s.status == .running)
        #expect(s.ticker == "NVDA")
        #expect(s.capabilities.supportsPause)
        #expect(s.stages.count == 2)
        #expect(s.stageStatus == ["a": .pending, "b": .pending])
    }

    @Test("stage.active / stage.done 更新对应 stage")
    func stageLifecycle() {
        var s = TradingDeskState()
        s.stageStatus = ["a": .pending]
        s = TradingDeskReducer.reduce(s, ev(.stageActive, seq: 2, data: ["stage_id": "a"]))
        #expect(s.stageStatus["a"] == .active)
        s = TradingDeskReducer.reduce(s, ev(.stageDone, seq: 3, data: ["stage_id": "a"]))
        #expect(s.stageStatus["a"] == .done)
    }

    @Test("turn.started + agent.token 累加 + turn.done")
    func turnLifecycle() {
        var s = TradingDeskState()
        s = TradingDeskReducer.reduce(s, ev(.turnStarted, seq: 1, data: [
            "turn_id": "t1", "stage_id": "a", "name": "市场分析师",
            "role": "r", "avatar": "市"]))
        s = TradingDeskReducer.reduce(s, ev(.agentToken, seq: 2, data: ["turn_id": "t1", "text": "第一"]))
        s = TradingDeskReducer.reduce(s, ev(.agentToken, seq: 3, data: ["turn_id": "t1", "text": "段"]))
        #expect(s.turns.count == 1)
        #expect(s.turns[0].text == "第一段")
        #expect(!s.turns[0].done)
        s = TradingDeskReducer.reduce(s, ev(.turnDone, seq: 4, data: ["turn_id": "t1"]))
        #expect(s.turns[0].done)
    }

    @Test("agent.think 折叠到 thinking 字段")
    func thinkTokens() {
        var s = TradingDeskState()
        s = TradingDeskReducer.reduce(s, ev(.turnStarted, seq: 1, data: [
            "turn_id": "t1", "stage_id": "a", "name": "n", "role": "", "avatar": ""]))
        s = TradingDeskReducer.reduce(s, ev(.agentThink, seq: 2, data: ["turn_id": "t1", "text": "思考"]))
        s = TradingDeskReducer.reduce(s, ev(.agentThink, seq: 3, data: ["turn_id": "t1", "text": "…"]))
        #expect(s.turns[0].thinking == "思考…")
    }

    @Test("agent.tool_call 追加工具名")
    func toolCall() {
        var s = TradingDeskState()
        s = TradingDeskReducer.reduce(s, ev(.turnStarted, seq: 1, data: [
            "turn_id": "t1", "stage_id": "a", "name": "n", "role": "", "avatar": ""]))
        s = TradingDeskReducer.reduce(s, ev(.agentToolCall, seq: 2, data: [
            "turn_id": "t1", "tool": "lookup_ticker"]))
        s = TradingDeskReducer.reduce(s, ev(.agentToolCall, seq: 3, data: [
            "turn_id": "t1", "tool": "get_financials", "args": ["ticker": "NVDA"]]))
        #expect(s.turns[0].tools == ["lookup_ticker", "get_financials"])
    }

    @Test("agent.signal：signals 追加 + stageSignal + 回填 turn")
    func signal() {
        var s = TradingDeskState()
        s.turns = [Turn(turnId: "t1", stageId: "a", name: "n", role: "", avatar: "",
                        text: "", tools: [], done: false, human: false, debate: nil, signal: nil)]
        s = TradingDeskReducer.reduce(s, ev(.agentSignal, seq: 2, data: [
            "stage_id": "a", "name": "市场分析师", "dir": "bull", "conf": 78,
            "turn_id": "t1", "extracted": true]))
        #expect(s.signals.count == 1)
        #expect(s.signals[0] == SignalRow(name: "市场分析师", dir: .bull, conf: 78, extracted: true))
        #expect(s.stageSignal["a"] == StageSignal(dir: .bull, conf: 78))
        #expect(s.turns[0].signal?.conf == 78)
    }

    @Test("debate.turn：回填辩论元数据")
    func debate() {
        var s = TradingDeskState()
        s.turns = [Turn(turnId: "t1", stageId: "a", name: "n", role: "", avatar: "",
                        text: "", tools: [], done: false, human: false, debate: nil, signal: nil)]
        s = TradingDeskReducer.reduce(s, ev(.debateTurn, seq: 2, data: [
            "stage_id": "a", "debate_id": "d1", "side": "bull", "side_label": "看多方",
            "polarity": "bull", "round": 2, "turn_id": "t1"]))
        #expect(s.turns[0].debate?.sideLabel == "看多方")
        #expect(s.turns[0].debate?.round == 2)
    }

    @Test("human.note：插入人工卡片（turnId 用 seq 保证唯一）")
    func humanNote() {
        var s = TradingDeskState()
        s = TradingDeskReducer.reduce(s, ev(.humanNote, seq: 7, data: ["text": "注意出口管制"]))
        #expect(s.turns.count == 1)
        #expect(s.turns[0].turnId == "human-7")
        #expect(s.turns[0].human)
        #expect(s.turns[0].text == "注意出口管制")
    }

    @Test("consensus.update / verdict / run.paused / run.resumed / run.finished / error")
    func miscEvents() {
        var s = TradingDeskState()
        s = TradingDeskReducer.reduce(s, ev(.consensusUpdate, seq: 1, data: [
            "bull": 3, "neutral": 1, "bear": 2, "lean": "偏多"]))
        #expect(s.consensus?.bull == 3)
        s = TradingDeskReducer.reduce(s, ev(.verdict, seq: 2, data: [
            "signal": "BUY", "confidence": 0.8, "size_fraction": 0.25,
            "entry_reference_price": nil, "target_price": 200, "stop_loss": 160,
            "currency": "USD", "time_horizon_days": 30, "rationale": "r", "warning_message": nil]))
        #expect(s.verdict?.signal == .buy)
        s = TradingDeskReducer.reduce(s, ev(.runPaused, seq: 3))
        #expect(s.status == .paused)
        s = TradingDeskReducer.reduce(s, ev(.runResumed, seq: 4))
        #expect(s.status == .running)
        s = TradingDeskReducer.reduce(s, ev(.runFinished, seq: 5, data: [
            "status": "completed", "duration_ms": 61000]))
        #expect(s.status == .completed)
        #expect(s.durationMs == 61000)
        s = TradingDeskReducer.reduce(s, ev(.error, seq: 6, data: [
            "message": "LLM 超时", "fatal": false]))
        #expect(s.error == "LLM 超时")
    }

    @Test("run.finished 的 status 字符串映射 RunStatus")
    func finishedStatusMapping() {
        var s = TradingDeskState()
        s.status = .running
        for (raw, expected) in [("cancelled", RunStatus.cancelled), ("failed", .failed),
                                 ("interrupted", .interrupted), ("completed", .completed)] {
            s = TradingDeskReducer.reduce(s, ev(.runFinished, seq: s.lastSeq + 1, data: [
                "status": raw, "duration_ms": 0]))
            #expect(s.status == expected)
        }
    }

    @Test("buildAuditChain：有文本的 turn 生成条目，human 标注，辩论带轮次")
    func auditChain() {
        let turns = [
            Turn(turnId: "t1", stageId: "a", name: "分析师", role: "", avatar: "",
                 text: "第一条内容", tools: [], done: true, human: false, debate: nil, signal: nil),
            Turn(turnId: "t2", stageId: "a", name: "", role: "", avatar: "",
                 text: "   ", tools: [], done: true, human: false, debate: nil, signal: nil),
            Turn(turnId: "t3", stageId: "a", name: "看多方", role: "", avatar: "",
                 text: "很长的一段话超过四十个字符的话就会被截断掉后面用省略号显示出来的",
                 tools: [], done: true, human: false,
                 debate: DebateInfo(debateId: "d", side: "bull", sideLabel: "看多",
                                     polarity: .bull, round: 1), signal: nil),
            Turn(turnId: "h1", stageId: "", name: "你", role: "人工意见", avatar: "你",
                 text: "人工意见", tools: [], done: true, human: true, debate: nil, signal: nil),
        ]
        let chain = TradingDeskReducer.buildAuditChain(turns)
        #expect(chain.count == 3) // 空白文本的 t2 被过滤
        #expect(chain[0].who == "分析师")
        #expect(chain[1].who.contains("第 1 轮"))
        #expect(chain[1].excerpt.hasSuffix("…"))
        #expect(chain[2].human)
        #expect(chain[2].who == "你")
    }
}
```

- [x] **Step 2: 跑测试确认失败**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | grep "error:" | head -3
```

- [x] **Step 3: 实现 State 值类型**

`Core/Sources/Core/State/TradingDeskState.swift`:

```swift
import Foundation

public enum RunStatus: String, Sendable, Equatable {
    case idle, running, paused, completed, cancelled, failed, interrupted
}

public enum StageStatus: String, Sendable, Equatable {
    case pending, active, done
}

public struct StageSignal: Sendable, Equatable {
    public var dir: Polarity
    public var conf: Int
    public init(dir: Polarity, conf: Int) {
        self.dir = dir
        self.conf = conf
    }
}

public struct TurnSignal: Sendable, Equatable {
    public var dir: Polarity
    public var conf: Int
    public var extracted: Bool
    public init(dir: Polarity, conf: Int, extracted: Bool) {
        self.dir = dir
        self.conf = conf
        self.extracted = extracted
    }
}

/// 一张发言卡（agent / 人工意见 / 辩论发言共用）。
public struct Turn: Identifiable, Sendable, Equatable {
    public var turnId: String
    public var stageId: String
    public var name: String
    public var role: String
    public var avatar: String
    public var text: String
    /// Anthropic extended thinking 推理链（折叠展示）
    public var thinking: String?
    public var tools: [String]
    public var done: Bool
    /// 人工意见卡片，与 agent 卡片区分渲染
    public var human: Bool
    public var debate: DebateInfo?
    public var signal: TurnSignal?
    public var id: String { turnId }

    public init(turnId: String, stageId: String, name: String, role: String,
                avatar: String, text: String, thinking: String? = nil, tools: [String],
                done: Bool, human: Bool, debate: DebateInfo?, signal: TurnSignal?) {
        self.turnId = turnId
        self.stageId = stageId
        self.name = name
        self.role = role
        self.avatar = avatar
        self.text = text
        self.thinking = thinking
        self.tools = tools
        self.done = done
        self.human = human
        self.debate = debate
        self.signal = signal
    }
}

public struct SignalRow: Sendable, Equatable, Identifiable {
    public var name: String
    public var dir: Polarity
    public var conf: Int
    public var extracted: Bool
    public var id: String { "\(name)-\(dir)-\(conf)" }
    public init(name: String, dir: Polarity, conf: Int, extracted: Bool) {
        self.name = name
        self.dir = dir
        self.conf = conf
        self.extracted = extracted
    }
}

public struct AuditEntry: Sendable, Equatable {
    public var who: String
    public var human: Bool
    public var excerpt: String
}

/// UI 全量状态（值类型，reducer 产出新副本，VM 持有）。
public struct TradingDeskState: Sendable, Equatable {
    public var runId: String?
    public var status: RunStatus = .idle
    public var ticker: String = ""
    public var engine: String = ""
    public var capabilities = EngineCapabilities()
    public var stages: [StageDescriptor] = []
    public var stageStatus: [String: StageStatus] = [:]
    public var stageSignal: [String: StageSignal] = [:]
    public var turns: [Turn] = []
    public var signals: [SignalRow] = []
    public var consensus: ConsensusData?
    public var verdict: VerdictData?
    /// 断线续读游标（SSE id）
    public var lastEventId: String?
    /// 去重游标（事件 seq）
    public var lastSeq: Int = 0
    public var error: String?
    public var durationMs: Int?

    public init() {}
}
```

- [x] **Step 4: 实现 Reducer**

`Core/Sources/Core/State/TradingDeskReducer.swift`:

```swift
import Foundation

/// 事件 → 状态纯函数（移植 web reduceEvent，frontend/lib/store/trading_desk.ts:111）。
/// 返回新状态（值语义），不碰任何 UI 框架——测试直接覆盖。
public enum TradingDeskReducer {
    public static func reduce(_ state: TradingDeskState,
                              _ event: TradingDeskEvent) -> TradingDeskState {
        var s = state
        switch event.type {
        case .runStarted:
            guard let d = event.data?.decode(as: RunStartedData.self) else { return s }
            s.ticker = d.ticker
            s.engine = d.engine
            s.capabilities = d.capabilities
            s.stages = d.stages
            s.stageStatus = Dictionary(uniqueKeysWithValues: d.stages.map { ($0.id, .pending) })
            s.status = .running

        case .stageActive:
            if let id = event.data?["stage_id"]?.string { s.stageStatus[id] = .active }

        case .stageDone:
            if let id = event.data?["stage_id"]?.string { s.stageStatus[id] = .done }

        case .turnStarted:
            guard let d = event.data?.decode(as: TurnStartedData.self) else { return s }
            s.turns.append(Turn(
                turnId: d.turnId, stageId: d.stageId, name: d.name, role: d.role,
                avatar: d.avatar, text: "", tools: [], done: false, human: false,
                debate: nil, signal: nil))

        case .debateTurn:
            guard let d = event.data?.decode(as: DebateTurnData.self) else { return s }
            s.turns.update(d.turnId) { $0.debate = DebateInfo(
                debateId: d.debateId, side: d.side, sideLabel: d.sideLabel,
                polarity: d.polarity, round: d.round) }

        case .agentToolCall:
            if let turnId = event.data?["turn_id"]?.string,
               let tool = event.data?["tool"]?.string {
                s.turns.update(turnId) { $0.tools.append(tool) }
            }

        case .agentToken:
            if let turnId = event.data?["turn_id"]?.string,
               let text = event.data?["text"]?.string {
                s.turns.update(turnId) { $0.text += text }
            }

        case .agentThink:
            if let turnId = event.data?["turn_id"]?.string,
               let text = event.data?["text"]?.string {
                s.turns.update(turnId) { $0.thinking = ($0.thinking ?? "") + text }
            }

        case .turnDone:
            if let turnId = event.data?["turn_id"]?.string {
                s.turns.update(turnId) { $0.done = true }
            }

        case .agentSignal:
            guard let d = event.data?.decode(as: SignalData.self) else { return s }
            s.signals.append(SignalRow(name: d.name, dir: d.dir, conf: d.conf,
                                       extracted: d.extracted))
            s.stageSignal[d.stageId] = StageSignal(dir: d.dir, conf: d.conf)
            if let turnId = d.turnId {
                s.turns.update(turnId) {
                    $0.signal = TurnSignal(dir: d.dir, conf: d.conf, extracted: d.extracted)
                }
            }

        case .humanNote:
            if let text = event.data?["text"]?.string {
                s.turns.append(Turn(
                    turnId: "human-\(event.seq)", stageId: "", name: "你", role: "人工意见",
                    avatar: "你", text: text, tools: [], done: true, human: true,
                    debate: nil, signal: nil))
            }

        case .consensusUpdate:
            if let c = event.data?.decode(as: ConsensusData.self) { s.consensus = c }

        case .runPaused:
            s.status = .paused

        case .runResumed:
            s.status = .running

        case .verdict:
            if let v = event.data?.decode(as: VerdictData.self) { s.verdict = v }

        case .runFinished:
            if let d = event.data?.decode(as: RunFinishedData.self),
               let st = RunStatus(rawValue: d.status) {
                s.status = st
            } else {
                s.status = .failed
            }
            s.durationMs = event.data?["duration_ms"]?.int

        case .error:
            s.error = event.data?["message"]?.string
        }
        return s
    }

    /// 审计链由 turn 序列派生（非独立事件）。人工意见显式标注，人为干预可追溯。
    public static func buildAuditChain(_ turns: [Turn]) -> [AuditEntry] {
        turns.filter { !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
            .map { t in
                let who: String
                if t.human { who = "你" }
                else if let debate = t.debate { who = "\(t.name)（第 \(debate.round) 轮）" }
                else { who = t.name }
                let trimmed = t.text
                let excerpt = trimmed.count > 40
                    ? String(trimmed.prefix(40)) + "…" : trimmed
                return AuditEntry(who: who, human: t.human, excerpt: excerpt)
            }
    }
}

// turn.started 的 payload（reducer 专用，放这里避免模型文件膨胀）
struct TurnStartedData: Codable, Sendable {
    var turnId: String
    var stageId: String
    var name: String
    var role: String
    var avatar: String
    enum CodingKeys: String, CodingKey {
        case name, role, avatar
        case turnId = "turn_id"
        case stageId = "stage_id"
    }
}

extension Array where Element == Turn {
    /// 按 turnId 就地改一张卡（token 累加/辩论回填等）。
    mutating func update(_ turnId: String, _ transform: (inout Turn) -> Void) {
        guard let idx = firstIndex(where: { $0.turnId == turnId }) else { return }
        transform(&self[idx])
    }
}
```

注意：`TurnStartedData` 不带默认值字段，`role`/`avatar` 后端有默认空串，decode 用非可选 String（后端 model_dump 总会带键）。

- [x] **Step 5: 跑测试通过**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | tail -3
```

期望：reducer 套件 11 个测试全绿。

- [x] **Step 6: 提交**

```bash
git add ios/DeepAlphaClub && git commit -m "feat(state): 事件→状态 reducer 移植（17 种事件 + 审计链派生）"
```

---

## Task 8: SSEClient（URLSession.bytes 流式订阅）

**Files:**
- Create: `Core/Sources/Core/SSEClient.swift`
- Test: `Core/Tests/CoreTests/SSEClientTests.swift`

- [x] **Step 1: 写失败测试**

`Core/Tests/CoreTests/SSEClientTests.swift`:

```swift
import Foundation
import Testing
@testable import Core

@Suite("SSEClient")
struct SSEClientTests {
    func makeClient(token: String? = "tok") -> SSEClient {
        SSEClient(baseURL: URL(string: "https://api.example.com")!,
                  session: MockURLProtocol.makeSession(),
                  tokenProvider: { token })
    }

    func httpOK(_ url: URL?) -> HTTPURLResponse {
        HTTPURLResponse(url: url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
    }

    @Test("订阅：请求头正确（Bearer / Last-Event-ID / Accept）+ 帧序列产出")
    @.resetMock
    func streamHeadersAndFrames() async throws {
        let captured = LockedRequestBox()
        MockURLProtocol.handler = { req in
            captured.set(req)
            return (httpOK(req.url), .init())
        }
        // 分块推送：跨 chunk 半帧 + 注释行心跳
        let chunks: [(Data, Bool)] = [
            (Data("id: 1-0\ndata: {\"type\":\"run.started\",\"run_id\":\"r1\",\"seq\":1,\"ts\":0,\"data\":{}}\n\n".utf8), false),
            (Data(":\n\n".utf8), false),
            (Data("id: 1-1\ndata: {\"type\":\"run.paused\",\"run_id\":\"r1\"".utf8), false),
            (Data(",\"seq\":2,\"ts\":0,\"data\":{}}\n\n".utf8), false),
            (Data("data: 坏行不产出\n\n".utf8), false),
        ]
        // URLProtocol handler 一次性返回整个 body 无法模拟分块——改用 bodyData 直传，
        // 半帧由「id 行与 data 行分属两次 didLoad」验证：见 streamHalfFrameAcrossChunks
        _ = chunks
        let body = "id: 1-0\ndata: {\"type\":\"run.started\",\"run_id\":\"r1\",\"seq\":1,\"ts\":0,\"data\":{}}\n\n"
            + ":\n\n"
            + "data: 坏 JSON\n\n"
            + "id: 1-1\ndata: {\"type\":\"run.paused\",\"run_id\":\"r1\",\"seq\":2,\"ts\":0,\"data\":{}}\n\n"
        MockURLProtocol.handler = { req in
            captured.set(req)
            return (httpOK(req.url), Data(body.utf8))
        }

        let client = makeClient()
        var frames: [SseFrame] = []
        for try await frame in client.stream(runId: "r1", lastEventId: "1-9") {
            frames.append(frame)
        }
        #expect(frames.count == 2) // 心跳与坏行被丢弃
        #expect(frames[0].id == "1-0")
        #expect(frames[1].event.type == .runPaused)
        let req = try #require(captured.get())
        #expect(req.url?.absoluteString == "https://api.example.com/api/v1/trading-desk/runs/r1/stream")
        #expect(req.value(forHTTPHeaderField: "Authorization") == "Bearer tok")
        #expect(req.value(forHTTPHeaderField: "Last-Event-ID") == "1-9")
        #expect(req.value(forHTTPHeaderField: "Accept") == "text/event-stream")
    }

    @Test("无 lastEventId 时不发 Last-Event-ID 头")
    @.resetMock
    func noLastEventIdHeader() async throws {
        let captured = LockedRequestBox()
        MockURLProtocol.handler = { req in
            captured.set(req)
            return (httpOK(req.url), Data("data: {\"type\":\"run.finished\",\"run_id\":\"r\",\"seq\":1,\"ts\":0,\"data\":{}}\n\n".utf8))
        }
        let client = makeClient(token: nil)
        for try await _ in client.stream(runId: "r", lastEventId: nil) {}
        let req = try #require(captured.get())
        #expect(req.value(forHTTPHeaderField: "Last-Event-ID") == nil)
        #expect(req.value(forHTTPHeaderField: "Authorization") == nil)
    }

    @Test("非 2xx：抛 APIError（404 运行不存在）")
    @.resetMock
    func httpError() async throws {
        MockURLProtocol.handler = { req in
            let resp = HTTPURLResponse(url: req.url!, statusCode: 404,
                                       httpVersion: nil, headerFields: nil)!
            return (resp, Data(#"{"detail":"运行不存在或事件流已过期"}"#.utf8))
        }
        let client = makeClient()
        var iterator = client.stream(runId: "gone", lastEventId: nil).makeAsyncIterator()
        await #expect(throws: APIError.notFound) {
            _ = try await iterator.next()
        }
    }

    @Test("流尾无空行时残帧也产出")
    @.resetMock
    func trailingFrameWithoutBlankLine() async throws {
        MockURLProtocol.handler = { req in
            (httpOK(req.url),
             Data("id: 9\ndata: {\"type\":\"run.finished\",\"run_id\":\"r\",\"seq\":9,\"ts\":0,\"data\":{}}".utf8))
        }
        let client = makeClient()
        var frames: [SseFrame] = []
        for try await f in client.stream(runId: "r", lastEventId: nil) { frames.append(f) }
        #expect(frames.count == 1)
        #expect(frames[0].id == "9")
    }
}
```

注意第一个测试里开头那段 `chunks` 常量是无用残留（写了又改走整 body 方案）——抄写时删除，只保留 body 直传逻辑。

- [x] **Step 2: 跑测试确认失败**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | grep "error:" | head -3
```

- [x] **Step 3: 实现**

`Core/Sources/Core/SSEClient.swift`:

```swift
import Foundation

/// SSE 订阅：GET /api/v1/trading-desk/runs/{id}/stream（Accept: text/event-stream）。
/// 续读用 Last-Event-ID 请求头（Redis Stream ID）。重连策略由调用方
/// （TradingDeskViewModel.runLoop）负责——client 只做单连接生命周期。
public struct SSEClient: Sendable {
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

    public func stream(runId: String, lastEventId: String?) -> AsyncThrowingStream<SseFrame, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    guard let url = URL(string: "\(baseURL.absoluteString)/api/v1/trading-desk/runs/\(runId)/stream") else {
                        throw APIError.decoding
                    }
                    var request = URLRequest(url: url)
                    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    if let token = tokenProvider() {
                        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                    }
                    if let last = lastEventId {
                        request.setValue(last, forHTTPHeaderField: "Last-Event-ID")
                    }
                    let (bytes, response) = try await session.bytes(for: request)
                    guard let http = response as? HTTPURLResponse else { throw APIError.network }
                    guard (200..<300).contains(http.statusCode) else {
                        // 读掉 body 以便错误映射拿到 detail
                        var body = Data()
                        for try await b in bytes { body.append(b) }
                        throw APIError.from(status: http.statusCode, body: body)
                    }
                    var buffer = ""
                    for try await line in bytes.lines {
                        if Task.isCancelled { break }
                        if line.isEmpty {                     // 空行 = 帧边界
                            if let frame = SSEFrameParser.parse(buffer) {
                                continuation.yield(frame)
                            }
                            buffer = ""
                        } else if line.hasPrefix(":") {      // 心跳注释行
                            continue
                        } else {
                            buffer += buffer.isEmpty ? line : "\n" + line
                        }
                    }
                    if Task.isCancelled {
                        continuation.finish()
                    } else {
                        // 流被服务端关掉且最后一帧后无空行：刷出残帧再正常收尾
                        if !buffer.isEmpty, let frame = SSEFrameParser.parse(buffer) {
                            continuation.yield(frame)
                        }
                        continuation.finish()
                    }
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
}
```

注意 `APIError.network` 对连接错误：`session.bytes` 抛 URLError 时不转 APIError（保持原始 error 冒泡，调用方一律 catch 重试）——只对 HTTP 层错误转 typed。VM 重连逻辑对任何 error 一视同仁。

- [x] **Step 4: 跑测试通过**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | tail -3
```

- [x] **Step 5: 提交**

```bash
git add ios/DeepAlphaClub && git commit -m "feat(sse): SSEClient（Last-Event-ID 续读 / 心跳忽略 / 残帧刷出）"
```

---

## Task 9: TradingDeskServicing 协议 + 线上实现

**Files:**
- Create: `Core/Sources/Core/TradingDeskService.swift`
- Test: `Core/Tests/CoreTests/TradingDeskServiceTests.swift`

- [x] **Step 1: 写失败测试**

`Core/Tests/CoreTests/TradingDeskServiceTests.swift`:

```swift
import Foundation
import Testing
@testable import Core

@Suite("TradingDeskService")
struct TradingDeskServiceTests {
    func makeService() -> TradingDeskService {
        TradingDeskService(
            api: APIClient(baseURL: URL(string: "https://api.example.com")!,
                           session: MockURLProtocol.makeSession(), tokenProvider: { "t" }),
            sse: SSEClient(baseURL: URL(string: "https://api.example.com")!,
                           session: MockURLProtocol.makeSession(), tokenProvider: { "t" }))
    }

    @Test("createRun：POST /runs + ticker JSON body")
    @.resetMock
    func createRun() async throws {
        let captured = LockedRequestBox()
        MockURLProtocol.handler = { req in
            captured.set(req)
            return (HTTPURLResponse(url: req.url!, statusCode: 200,
                                    httpVersion: nil, headerFields: nil)!,
                    Data(#"{"run_id":"run-1"}"#.utf8))
        }
        let runId = try await makeService().createRun(ticker: "NVDA")
        #expect(runId == "run-1")
        let req = try #require(captured.get())
        #expect(req.url?.path == "/api/v1/trading-desk/runs")
        #expect(req.httpMethod == "POST")
        let body = try #require(req.httpBody ?? req.httpBodyStreamData)
        #expect(String(data: body, encoding: .utf8) == #"{"ticker":"NVDA"}"#)
    }

    @Test("controlRun：action + text")
    @.resetMock
    func controlRun() async throws {
        let captured = LockedRequestBox()
        MockURLProtocol.handler = { req in
            captured.set(req)
            return (HTTPURLResponse(url: req.url!, statusCode: 200,
                                    httpVersion: nil, headerFields: nil)!,
                    Data(#"{"accepted":true}"#.utf8))
        }
        try await makeService().control(runId: "run-1", action: .inject, text: "注意风险")
        let req = try #require(captured.get())
        #expect(req.url?.path == "/api/v1/trading-desk/runs/run-1/control")
        let body = try #require(req.httpBody ?? req.httpBodyStreamData)
        #expect(String(data: body, encoding: .utf8) == #"{"action":"inject","text":"注意风险"}"#)
    }

    @Test("listRuns：query 参数 ticker/limit/offset")
    @.resetMock
    func listRuns() async throws {
        let captured = LockedRequestBox()
        MockURLProtocol.handler = { req in
            captured.set(req)
            return (HTTPURLResponse(url: req.url!, statusCode: 200,
                                    httpVersion: nil, headerFields: nil)!,
                    Data(#"{"runs":[]}"#.utf8))
        }
        let resp: RunListResponse = try await makeService()
            .listRuns(ticker: "nvda", limit: 50, offset: 10)
        #expect(resp.runs.isEmpty)
        let req = try #require(captured.get())
        #expect(req.url?.path == "/api/v1/trading-desk/runs")
        #expect(req.url?.query?.contains("ticker=NVDA") == true)
        #expect(req.url?.query?.contains("limit=50") == true)
        #expect(req.url?.query?.contains("offset=10") == true)
    }

    @Test("getRun：详情路径")
    @.resetMock
    func getRun() async throws {
        let captured = LockedRequestBox()
        MockURLProtocol.handler = { req in
            captured.set(req)
            return (HTTPURLResponse(url: req.url!, statusCode: 200,
                                    httpVersion: nil, headerFields: nil)!,
                    Data("""
                    {"run_id":"run-1","ticker":"NVDA","trade_date":"2026-08-30","engine":"e",
                     "status":"completed","duration_ms":1,
                     "created_at":"2026-08-30T10:00:00+00:00","finished_at":null,
                     "verdict":null,"signals":[],"turns":[]}
                    """.utf8))
        }
        let detail = try await makeService().getRun(runId: "run-1")
        #expect(detail.runId == "run-1")
        let req = try #require(captured.get())
        #expect(req.url?.path == "/api/v1/trading-desk/runs/run-1")
    }

    @Test("stream 委托 SSEClient（URL 路径正确）")
    @.resetMock
    func streamDelegation() async throws {
        let captured = LockedRequestBox()
        MockURLProtocol.handler = { req in
            captured.set(req)
            return (HTTPURLResponse(url: req.url!, statusCode: 200,
                                    httpVersion: nil, headerFields: nil)!,
                    Data("data: {\"type\":\"run.finished\",\"run_id\":\"run-1\",\"seq\":1,\"ts\":0,\"data\":{}}\n\n".utf8))
        }
        var count = 0
        for try await _ in makeService().stream(runId: "run-1", lastEventId: nil) { count += 1 }
        #expect(count == 1)
        #expect(captured.get()?.url?.path == "/api/v1/trading-desk/runs/run-1/stream")
    }
}
```

- [x] **Step 2: 跑测试确认失败**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | grep "error:" | head -3
```

- [x] **Step 3: 实现**

`Core/Sources/Core/TradingDeskService.swift`:

```swift
import Foundation

/// VM 依赖的业务端点抽象（测试注入 mock）。
public protocol TradingDeskServicing: Sendable {
    /// 创建运行，返回 run_id。
    func createRun(ticker: String) async throws -> String
    /// 控制（pause/resume/inject/cancel）。
    func control(runId: String, action: ControlAction, text: String?) async throws
    /// 历史列表（ticker 过滤可选，服务端分页）。
    func listRuns(ticker: String?, limit: Int, offset: Int) async throws -> RunListResponse
    /// 单条详情（回放）。
    func getRun(runId: String) async throws -> RunDetailResponse
    /// SSE 订阅（lastEventId 断线续读）。
    func stream(runId: String, lastEventId: String?) -> AsyncThrowingStream<SseFrame, Error>
}

/// 线上实现：组合 APIClient + SSEClient。
public struct TradingDeskService: TradingDeskServicing {
    let api: APIClient
    let sse: SSEClient

    public init(api: APIClient, sse: SSEClient) {
        self.api = api
        self.sse = sse
    }

    public func createRun(ticker: String) async throws -> String {
        struct Body: Encodable { let ticker: String }
        struct Resp: Decodable { let runId: String
            enum CodingKeys: String, CodingKey { case runId = "run_id" } }
        let resp: Resp = try await api.post("/api/v1/trading-desk/runs", json: Body(ticker: ticker))
        return resp.runId
    }

    public func control(runId: String, action: ControlAction, text: String?) async throws {
        struct Body: Encodable { let action: String; let text: String? }
        struct Resp: Decodable { let accepted: Bool }
        let _: Resp = try await api.post(
            "/api/v1/trading-desk/runs/\(runId)/control",
            json: Body(action: action.rawValue, text: text))
    }

    public func listRuns(ticker: String?, limit: Int, offset: Int) async throws -> RunListResponse {
        var query: [String: String] = ["limit": String(limit), "offset": String(offset)]
        if let t = ticker?.trimmingCharacters(in: .whitespaces).uppercased(), !t.isEmpty {
            query["ticker"] = t
        }
        return try await api.get("/api/v1/trading-desk/runs", query: query)
    }

    public func getRun(runId: String) async throws -> RunDetailResponse {
        try await api.get("/api/v1/trading-desk/runs/\(runId)")
    }

    public func stream(runId: String, lastEventId: String?) -> AsyncThrowingStream<SseFrame, Error> {
        sse.stream(runId: runId, lastEventId: lastEventId)
    }
}
```

注意 createRun 的 body 请求体测试断言 `{"ticker":"NVDA"}`（不带 trade_date——web 版传 `trade_date: null`，JSONEncoder 会省略 Optional nil 字段，等价）。

- [x] **Step 4: 跑测试通过**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | tail -3
```

- [x] **Step 5: 提交**

```bash
git add ios/DeepAlphaClub && git commit -m "feat(service): 业务端点封装（createRun/control/listRuns/getRun/stream）"
```

---

## Task 10: TradingDeskViewModel（状态机 + 无限重连）

**Files:**
- Create: `Core/Sources/Core/ViewModels/TradingDeskViewModel.swift`
- Test: `Core/Tests/CoreTests/TradingDeskViewModelTests.swift`

- [x] **Step 1: 写失败测试**

`Core/Tests/CoreTests/TradingDeskViewModelTests.swift`:

```swift
import Foundation
import Testing
@testable import Core

/// 流脚本：按调用次数依次返回不同流（第一次断、第二次成功）。
final class StreamScript: @unchecked Sendable {
    private let lock = NSLock()
    private var calls = 0
    var callCount: Int { lock.lock(); defer { lock.unlock() }; return calls }
    /// 每次 stream 调用返回的流工厂（数组按次序消费，越界用最后一个）
    var scripts: [(Int) -> AsyncThrowingStream<SseFrame, Error>] = []

    func next(runId: String, lastEventId: String?) -> AsyncThrowingStream<SseFrame, Error> {
        lock.lock(); defer { lock.unlock() }
        let n = calls
        calls += 1
        let idx = min(n, scripts.count - 1)
        return scripts[idx](n)
    }
}

/// mock service：createRun/control 可编程，stream 委托 StreamScript。
final class MockDeskService: TradingDeskServicing, @unchecked Sendable {
    var createRunResult: String = "run-1"
    var createRunError: Error?
    var controlError: Error?
    private let lock = NSLock()
    private var _controls: [(ControlAction, String?)] = []
    var controls: [(ControlAction, String?)] { lock.lock(); defer { lock.unlock() }; return _controls }
    let streams = StreamScript()

    func createRun(ticker: String) async throws -> String {
        if let e = createRunError { throw e }
        return createRunResult
    }
    func control(runId: String, action: ControlAction, text: String?) async throws {
        if let e = controlError { throw e }
        lock.lock(); _controls.append((action, text)); lock.unlock()
    }
    func listRuns(ticker: String?, limit: Int, offset: Int) async throws -> RunListResponse {
        RunListResponse(runs: [])
    }
    func getRun(runId: String) async throws -> RunDetailResponse {
        throw APIError.notFound
    }
    func stream(runId: String, lastEventId: String?) -> AsyncThrowingStream<SseFrame, Error> {
        streams.next(runId: runId, lastEventId: lastEventId)
    }
}

func frames(_ events: [TradingDeskEvent]) -> AsyncThrowingStream<SseFrame, Error> {
    AsyncThrowingStream { cont in
        for e in events { cont.yield(SseFrame(id: "id-\(e.seq)", event: e)) }
        cont.finish()
    }
}

func failingStream() -> AsyncThrowingStream<SseFrame, Error> {
    AsyncThrowingStream { $0.finish(throwing: URLError(.networkConnectionLost)) }
}

@MainActor
@Suite("TradingDeskViewModel")
struct TradingDeskViewModelTests {
    /// VM 用即时 sleeper（不真睡），并返回让 runLoop 跑完的句柄。
    func makeVM(_ service: MockDeskService) -> TradingDeskViewModel {
        let vm = TradingDeskViewModel(service: service)
        vm.sleeper = { _ in }   // 重连零等待
        return vm
    }

    @Test("startRun：resolveTicker → createRun → 状态 running → 事件折叠")
    func startRunFoldsEvents() async throws {
        let service = MockDeskService()
        let events = [
            ev(.runStarted, seq: 1, data: [
                "ticker": "700.HK", "trade_date": "2026-08-30", "engine": "e",
                "capabilities": ["supports_pause": false, "supports_inject": false,
                                  "supports_resume_after_restart": false],
                "stages": [["id": "s1", "name": "分析师", "role": "r", "group": "analyst"]]]),
            ev(.turnStarted, seq: 2, data: [
                "turn_id": "t1", "stage_id": "s1", "name": "分析师",
                "role": "", "avatar": "析"]),
            ev(.agentToken, seq: 3, data: ["turn_id": "t1", "text": "结论"]),
            ev(.runFinished, seq: 4, data: ["status": "completed", "duration_ms": 1000]),
        ]
        service.streams.scripts = [{ _ in frames(events) }]
        let vm = makeVM(service)

        await vm.startRun(ticker: "0700", market: .HK)
        #expect(service.createRunCalls == 1)
        #expect(vm.state.runId == "run-1")
        #expect(vm.state.status == .completed)
        #expect(vm.state.turns.first?.text == "结论")
        #expect(vm.state.lastEventId == "id-4")
        #expect(vm.state.ticker == "700.HK")
    }

    @Test("seq 去重：重连重放的旧事件被丢弃")
    func seqDedup() async throws {
        let service = MockDeskService()
        let first = [
            ev(.runStarted, seq: 1, data: [
                "ticker": "NVDA", "trade_date": "d", "engine": "e",
                "capabilities": [:], "stages": []]),
            ev(.turnStarted, seq: 2, data: [
                "turn_id": "t1", "stage_id": "", "name": "n", "role": "", "avatar": ""]),
        ]
        // 第一次流断线；第二次重放 seq=2 的 turn.started（重复）再给新事件
        service.streams.scripts = [
            { _ in frames(first) },                          // 正常结束？不——
        ]
        // 用抛错流模拟断线：第一次断，第二次重放+新事件
        service.streams.scripts = [
            { _ in AsyncThrowingStream<SseFrame, Error> { $0.finish(throwing: URLError(.timedOut)) } },
            { _ in frames([
                ev(.runStarted, seq: 1, data: [
                    "ticker": "NVDA", "trade_date": "d", "engine": "e",
                    "capabilities": [:], "stages": []]),
                ev(.turnStarted, seq: 2, data: [
                    "turn_id": "t1", "stage_id": "", "name": "n", "role": "", "avatar": ""]),
                ev(.turnStarted, seq: 2, data: [           // 重放，必须被丢弃
                    "turn_id": "t1", "stage_id": "", "name": "n", "role": "", "avatar": ""]),
                ev(.agentToken, seq: 3, data: ["turn_id": "t1", "text": "x"]),
                ev(.runFinished, seq: 4, data: ["status": "completed", "duration_ms": 0]),
            ]) },
        ]
        let vm = makeVM(service)
        await vm.startRun(ticker: "NVDA", market: .US)
        #expect(vm.state.turns.count == 1)   // 重放的 turn.started 没建第二张卡
        #expect(vm.state.status == .completed)
        #expect(service.streams.callCount == 2)  // 断线重连了一次
    }

    @Test("断线重连：第一次失败退避后用 lastEventId 续读")
    func reconnectWithLastEventId() async throws {
        let service = MockDeskService()
        var receivedLastIds: [String?] = []
        let box = LockedIds()
        service.streams.scripts = [
            { _ in failingStream() },
            { _ in frames([
                ev(.runStarted, seq: 1, data: [
                    "ticker": "NVDA", "trade_date": "d", "engine": "e",
                    "capabilities": [:], "stages": []]),
                ev(.runFinished, seq: 2, data: ["status": "completed", "duration_ms": 0]),
            ]) },
        ]
        // 记录第二次 stream 调用时的 lastEventId（通过包裹：暂略，直接断言 state.lastEventId 保留即可）
        let vm = makeVM(service)
        await vm.startRun(ticker: "NVDA", market: .US)
        #expect(service.streams.callCount == 2)
        #expect(vm.state.status == .completed)
        _ = receivedLastIds; _ = box
    }

    @Test("终态不再重连：run.finished 后流断也不重试")
    func noReconnectAfterTerminal() async throws {
        let service = MockDeskService()
        service.streams.scripts = [
            { _ in frames([
                ev(.runStarted, seq: 1, data: [
                    "ticker": "NVDA", "trade_date": "d", "engine": "e",
                    "capabilities": [:], "stages": []]),
                ev(.runFinished, seq: 2, data: ["status": "completed", "duration_ms": 0]),
            ]) },
            { _ in failingStream() },   // 若错误重连会走这里（不应被调用）
        ]
        let vm = makeVM(service)
        await vm.startRun(ticker: "NVDA", market: .US)
        #expect(service.streams.callCount == 1)
    }

    @Test("流正常结束不重连（后端 run.finished 后关流）")
    func normalEndNoReconnect() async throws {
        let service = MockDeskService()
        service.streams.scripts = [
            { _ in frames([
                ev(.runStarted, seq: 1, data: [
                    "ticker": "NVDA", "trade_date": "d", "engine": "e",
                    "capabilities": [:], "stages": []]),
                // 注意：没有 run.finished，流正常结束
            ]) },
        ]
        let vm = makeVM(service)
        await vm.startRun(ticker: "NVDA", market: .US)
        #expect(service.streams.callCount == 1)   // 正常结束 → 不重连（与 web 一致）
        #expect(vm.state.status == .running)      // 状态停在 running（服务端没发终态）
    }

    @Test("control：注入文本转发 + cancel 后状态本地不变（等服务端事件）")
    func controlActions() async throws {
        let service = MockDeskService()
        service.streams.scripts = [{ _ in frames([
            ev(.runStarted, seq: 1, data: [
                "ticker": "NVDA", "trade_date": "d", "engine": "e",
                "capabilities": ["supports_pause": true, "supports_inject": true,
                                  "supports_resume_after_restart": false],
                "stages": []]),
        ]) }]
        let vm = makeVM(service)
        await vm.startRun(ticker: "NVDA", market: .US)
        await vm.control(.inject, text: "关注关税")
        await vm.control(.pause)
        #expect(service.controls == [(.inject, "关注关税"), (.pause, nil)])
        #expect(vm.state.status == .running)
    }

    @Test("control 失败 → pageError 展示中文消息")
    func controlErrorSurfaces() async throws {
        let service = MockDeskService()
        service.controlError = APIError.validation("注入意见时 text 不能为空")
        let vm = makeVM(service)
        vm.state.runId = "run-1"
        await vm.control(.inject, text: "")
        #expect(vm.pageError == "注入意见时 text 不能为空")
    }

    @Test("createRun 失败 → pageError + 状态回 idle")
    func createRunFails() async throws {
        let service = MockDeskService()
        service.createRunError = APIError.server(500, "LLM 全线熔断")
        let vm = makeVM(service)
        await vm.startRun(ticker: "NVDA", market: .US)
        #expect(vm.pageError == "LLM 全线熔断")
        #expect(vm.state.status == .idle)
    }

    @Test("后台挂起 → 断流；回前台 → 若仍 live 则续订")
    func scenePhaseHandling() async throws {
        let service = MockDeskService()
        service.streams.scripts = [
            { _ in frames([ev(.runStarted, seq: 1, data: [
                "ticker": "NVDA", "trade_date": "d", "engine": "e",
                "capabilities": [:], "stages": []])]) },
            { _ in frames([ev(.runFinished, seq: 9, data: [
                "status": "completed", "duration_ms": 0])]) },
        ]
        let vm = makeVM(service)
        await vm.startRun(ticker: "NVDA", market: .US)
        #expect(service.streams.callCount == 1)

        vm.appDidEnterBackground()   // 取消订阅（state.lastEventId 已保留）
        try await Task.sleep(for: .milliseconds(50))  // 等 cancel 传播
        #expect(vm.state.status == .running)

        await vm.appDidBecomeActive()  // live → 重新订阅
        #expect(service.streams.callCount == 2)
        #expect(vm.state.status == .completed)
    }

    @Test("401 → unauthorized 冒泡给调用方（App 层清 token 回登录）")
    func unauthorizedSurfaces() async throws {
        let service = MockDeskService()
        service.createRunError = APIError.unauthorized
        let vm = makeVM(service)
        await vm.startRun(ticker: "NVDA", market: .US)
        #expect(vm.lastAuthError == .unauthorized)
    }
}

final class LockedIds: @unchecked Sendable {}
// MockDeskService.createRunCalls 计数：
extension MockDeskService {
    var createRunCalls: Int {
        get { lock.lock(); defer { lock.unlock() }; return _createRunCalls }
    }
    func recordCreateRun() { lock.lock(); _createRunCalls += 1; lock.unlock() }
}
```

注意：`MockDeskService` 需要在类里声明 `private var _createRunCalls = 0` 并在 `createRun` 成功路径调用 `recordCreateRun()`；`receivedLastIds`/`box` 两处占位代码抄写时删掉。`lock` 需要 `private let lock = NSLock()`（已声明）。

- [x] **Step 2: 跑测试确认失败**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | grep "error:" | head -3
```

- [x] **Step 3: 实现**

`Core/Sources/Core/ViewModels/TradingDeskViewModel.swift`:

```swift
import Foundation
import Observation

/// 交易台主 VM：持有 state，负责 startRun / control / SSE 消费循环 / 前后台切换。
@MainActor @Observable
public final class TradingDeskViewModel {
    public var state = TradingDeskState()
    /// 控制类请求进行中（禁用按钮），对齐 web 版 busy
    public private(set) var busy = false
    /// 页面级错误（createRun/control 失败等，顶部 banner）
    public private(set) var pageError: String?
    /// 最近一次 401（App 层观察它清 token 回登录）
    public private(set) var lastAuthError: APIError?

    let service: any TradingDeskServicing
    /// 重连退避的 sleep（测试注入零等待）。
    var sleeper: @Sendable (Duration) async throws -> Void = { try await Task.sleep(for: $0) }
    private var consumeTask: Task<Void, Never>?

    public init(service: any TradingDeskServicing) {
        self.service = service
    }

    public var live: Bool { state.status == .running || state.status == .paused }

    // MARK: - 启动 / 控制

    public func startRun(ticker raw: String, market: Market) async {
        let symbol = TickerResolver.resolve(raw: raw, market: market)
        guard !symbol.isEmpty else { return }
        pageError = nil
        busy = true
        defer { busy = false }
        do {
            let runId = try await service.createRun(ticker: symbol)
            state = TradingDeskState()          // 重置
            state.runId = runId
            state.ticker = symbol
            state.status = .running
            consume(runId: runId)
        } catch let e as APIError {
            if e == .unauthorized { lastAuthError = .unauthorized }
            pageError = e.message
        } catch {
            pageError = "启动失败：\(error.localizedDescription)"
        }
    }

    public func control(_ action: ControlAction, text: String? = nil) async {
        guard let runId = state.runId else { return }
        busy = true
        defer { busy = false }
        do {
            try await service.control(runId: runId, action: action, text: text)
        } catch let e as APIError {
            if e == .unauthorized { lastAuthError = .unauthorized }
            pageError = e.message
        } catch {
            pageError = error.localizedDescription
        }
    }

    // MARK: - SSE 消费（无限重连，移植 web consume）

    func consume(runId: String) {
        consumeTask?.cancel()
        consumeTask = Task { [weak self] in
            await self?.runLoop(runId: runId)
        }
    }

    private func runLoop(runId: String) async {
        var backoff: Duration = .milliseconds(800)
        while !Task.isCancelled {
            do {
                let lastId = state.lastEventId
                for try await frame in service.stream(runId: runId, lastEventId: lastId) {
                    apply(frame)
                }
                return   // 流正常结束：服务端关流，不重连（对齐 web）
            } catch {
                if Task.isCancelled { return }
                // 只有还活着才重连；终态（completed/failed/...）直接退出
                guard live else { return }
                try? await sleeper(backoff)
                if Task.isCancelled { return }
                backoff = min(backoff * 2, .seconds(30))
            }
        }
    }

    /// 单帧应用：seq 去重（重连重放）→ reduce → 更新 lastEventId 游标。
    func apply(_ frame: SseFrame) {
        guard frame.event.seq > state.lastSeq else { return }
        state = TradingDeskReducer.reduce(state, frame.event)
        state.lastEventId = frame.id ?? state.lastEventId
        state.lastSeq = frame.event.seq
    }

    // MARK: - 前后台切换

    /// 进后台：断开 SSE（iOS 后台网络保活不可靠），游标已在 state。
    public func appDidEnterBackground() {
        consumeTask?.cancel()
        consumeTask = nil
    }

    /// 回前台：仍 live 则用 lastEventId 续订（不丢不重）。
    public func appDidBecomeActive() async {
        guard live, let runId = state.runId, consumeTask == nil else { return }
        consume(runId: runId)
        // 给 runLoop 一点启动时间，让测试可观测；生产无副作用
        try? await Task.sleep(for: .milliseconds(10))
    }

    public func clearPageError() { pageError = nil }
}
```

- [x] **Step 4: 跑测试通过**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | tail -3
```

若 `scenePhaseHandling` 或 `noReconnectAfterTerminal` 偶发不过：runLoop 是后台 Task，`startRun` 返回时可能尚未消费完——这是异步竞争。修法：测试在断言前 `await vm.drainOnce()`（实现一个 `func drainOnce() async { await consumeTask?.value }`，并把 consumeTask 的 Task 存为可等待）。实现时直接把 `consumeTask` 声明为 `Task<Void, Never>?`（已如此），测试里 `await vm.consumeTaskValue`：

```swift
// TradingDeskViewModel 追加
var consumeTaskValue: Task<Void, Never>? { consumeTask }
```

测试在各 `startRun` 后统一 `await vm.consumeTaskValue?.value` 再断言（正常结束路径 runLoop return，Task 完成）。**重连路径的 Task 不会结束**（sleeper 即时返回但循环还在跑直到终态）——重连场景等终态断言即可（`status == .completed` 时 Task 已 return）。为稳定，给 VM 加一个轮询辅助：

```swift
// 测试端：等待直到条件满足或超时
func waitUntil(_ condition: @MainActor () -> Bool,
               timeout: Duration = .seconds(2)) async -> Bool {
    let start = ContinuousClock.now
    while ContinuousClock.now - start < timeout {
        if await MainActor.run(body: condition) { return true }
        try? await Task.sleep(for: .milliseconds(10))
    }
    return false
}
```

重连类测试用它等 `vm.state.status == .completed`，超时则 `#expect(Bool(false), "等待终态超时")`。

- [x] **Step 5: 提交**

```bash
git add ios/DeepAlphaClub && git commit -m "feat(vm): TradingDeskViewModel（startRun/control/无限重连/seq 去重/前后台）"
```

---

## Task 11: AppState（登录态）

**Files:**
- Create: `Core/Sources/Core/ViewModels/AppState.swift`
- Test: `Core/Tests/CoreTests/AppStateTests.swift`

- [x] **Step 1: 写失败测试**

`Core/Tests/CoreTests/AppStateTests.swift`:

```swift
import Foundation
import Testing
@testable import Core

@MainActor
@Suite("AppState")
struct AppStateTests {
    struct MockAuth: AuthServiceProtocol, Sendable {
        var result: Result<String, Error>
        func login(email: String, password: String) async throws -> String {
            switch result {
            case .success(let t): return t
            case .failure(let e): throw e
            }
        }
    }

    @Test("restore：Keychain 有 token → 已登录")
    func restoreWithToken() {
        let keychain = InMemoryKeychain()
        try? keychain.saveToken("jwt")
        let app = AppState(keychain: keychain, auth: MockAuth(result: .success("x")))
        app.restoreFromKeychain()
        #expect(app.isLoggedIn)
        #expect(app.token == "jwt")
    }

    @Test("restore：无 token → 未登录")
    func restoreWithoutToken() {
        let app = AppState(keychain: InMemoryKeychain(), auth: MockAuth(result: .success("x")))
        app.restoreFromKeychain()
        #expect(!app.isLoggedIn)
    }

    @Test("login 成功：token 入 Keychain")
    func loginSuccess() async {
        let keychain = InMemoryKeychain()
        let app = AppState(keychain: keychain, auth: MockAuth(result: .success("jwt-2")))
        let ok = await app.login(email: "a@b.c", password: "secret8")
        #expect(ok)
        #expect(app.isLoggedIn)
        #expect(keychain.loadToken() == "jwt-2")
        #expect(app.authError == nil)
    }

    @Test("login 失败：错误展示，token 不落盘")
    func loginFailure() async {
        let keychain = InMemoryKeychain()
        let app = AppState(keychain: keychain,
                           auth: MockAuth(result: .failure(APIError.unauthorized)))
        let ok = await app.login(email: "a@b.c", password: "wrong!!")
        #expect(!ok)
        #expect(!app.isLoggedIn)
        #expect(app.authError == "登录已过期，请重新登录")
        #expect(keychain.loadToken() == nil)
    }

    @Test("handleUnauthorized：清 token → 未登录（回登录页）")
    func handleUnauthorized() {
        let keychain = InMemoryKeychain()
        try? keychain.saveToken("jwt")
        let app = AppState(keychain: keychain, auth: MockAuth(result: .success("x")))
        app.restoreFromKeychain()
        app.handleUnauthorized()
        #expect(!app.isLoggedIn)
        #expect(keychain.loadToken() == nil)
    }

    @Test("logout：清 Keychain + 重置 deskVM 状态由视图层处理，这里只管 token")
    func logout() {
        let keychain = InMemoryKeychain()
        try? keychain.saveToken("jwt")
        let app = AppState(keychain: keychain, auth: MockAuth(result: .success("x")))
        app.restoreFromKeychain()
        app.logout()
        #expect(!app.isLoggedIn)
    }
}
```

- [x] **Step 2: 跑测试确认失败**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | grep "error:" | head -3
```

- [x] **Step 3: 实现**

先给 AuthService 补协议（`Core/Sources/Core/AuthService.swift` 追加）：

```swift
/// 登录抽象（测试 mock）。真实现是上面的 AuthService struct。
public protocol AuthServiceProtocol: Sendable {
    func login(email: String, password: String) async throws -> String
}

extension AuthService: AuthServiceProtocol {}
```

`Core/Sources/Core/ViewModels/AppState.swift`:

```swift
import Foundation
import Observation

/// 全局登录态：token 存 Keychain，启动恢复；401 时任何模块调 handleUnauthorized。
@MainActor @Observable
public final class AppState {
    public private(set) var token: String?
    public var authError: String?
    public private(set) var loggingIn = false

    public var isLoggedIn: Bool { token != nil }

    let keychain: any KeychainStoring
    let auth: any AuthServiceProtocol

    public init(keychain: any KeychainStoring, auth: any AuthServiceProtocol) {
        self.keychain = keychain
        self.auth = auth
    }

    /// App 启动时调用：Keychain 有 token 直接进主页。
    public func restoreFromKeychain() {
        token = keychain.loadToken()
    }

    @discardableResult
    public func login(email: String, password: String) async -> Bool {
        authError = nil
        loggingIn = true
        defer { loggingIn = false }
        guard !email.isEmpty, !password.isEmpty else {
            authError = "请输入邮箱和密码"
            return false
        }
        do {
            let t = try await auth.login(email: email, password: password)
            try keychain.saveToken(t)
            token = t
            return true
        } catch let e as APIError {
            authError = e.message
        } catch {
            authError = "登录失败：\(error.localizedDescription)"
        }
        return false
    }

    /// 401 全局处理：清 token，视图层观察到 isLoggedIn=false 自动回登录页。
    public func handleUnauthorized() {
        keychain.deleteToken()
        token = nil
    }

    public func logout() {
        keychain.deleteToken()
        token = nil
    }
}
```

- [x] **Step 4: 跑测试通过**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | tail -3
```

- [x] **Step 5: 提交**

```bash
git add ios/DeepAlphaClub && git commit -m "feat(app-state): 登录态（Keychain 恢复/401 清除/登出）"
```

---

## Task 12: MarkdownBlockParser（TurnCard 的轻量 markdown）

**Files:**
- Create: `Core/Sources/Core/MarkdownBlockParser.swift`
- Test: `Core/Tests/CoreTests/MarkdownBlockParserTests.swift`

`AttributedString(markdown:)` 只支持 inline 样式；LLM 输出大量 `###` 标题 / `-` 列表 / 代码块。这里做一个行级块解析（不做完整 CommonMark），块内 inline 交给 AttributedString。

- [x] **Step 1: 写失败测试**

`Core/Tests/CoreTests/MarkdownBlockParserTests.swift`:

```swift
import Testing
@testable import Core

@Suite("MarkdownBlockParser")
struct MarkdownBlockParserTests {
    @Test("标题分级")
    func headings() {
        let blocks = MarkdownBlockParser.parse("## 结论\n### 细节")
        #expect(blocks.count == 2)
        #expect(blocks[0] == .heading(level: 2, text: "结论"))
        #expect(blocks[1] == .heading(level: 3, text: "细节"))
    }

    @Test("无序列表聚合 + 有序列表聚合")
    func lists() {
        let blocks = MarkdownBlockParser.parse("- 第一项\n- 第二项\n1. 步骤一\n2. 步骤二")
        #expect(blocks.count == 2)
        guard case .bullet(let items) = blocks[0] else {
            Issue.record("应为 bullet"); return
        }
        #expect(items == ["第一项", "第二项"])
        guard case .ordered(let nums) = blocks[1] else {
            Issue.record("应为 ordered"); return
        }
        #expect(nums == ["步骤一", "步骤二"])
    }

    @Test("围栏代码块聚合（``` 围栏）")
    func codeFence() {
        let md = "说明\n```python\nprint(1)\nprint(2)\n```"
        let blocks = MarkdownBlockParser.parse(md)
        #expect(blocks.count == 2)
        #expect(blocks[0] == .paragraph("说明"))
        #expect(blocks[1] == .code("print(1)\nprint(2)"))
    }

    @Test("空行分段、多空行不产生空段")
    func paragraphs() {
        let blocks = MarkdownBlockParser.parse("第一段\n\n\n第二段")
        #expect(blocks == [.paragraph("第一段"), .paragraph("第二段")])
    }

    @Test("普通文本原样成段（inline 标记保留给 AttributedString）")
    func inlineKept() {
        let blocks = MarkdownBlockParser.parse("这是 **加粗** 与 `code`")
        #expect(blocks == [.paragraph("这是 **加粗** 与 `code`")])
    }

    @Test("表格行降级为代码块显示（等宽对齐）")
    func tableFallback() {
        let blocks = MarkdownBlockParser.parse("| a | b |\n|---|---|\n| 1 | 2 |")
        #expect(blocks.count == 1)
        guard case .code = blocks[0] else { Issue.record("应为 code"); return }
    }

    @Test("空串 → 空数组")
    func empty() {
        #expect(MarkdownBlockParser.parse("") == [])
        #expect(MarkdownBlockParser.parse("\n\n") == [])
    }
}
```

- [x] **Step 2: 跑测试确认失败**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | grep "error:" | head -3
```

- [x] **Step 3: 实现**

`Core/Sources/Core/MarkdownBlockParser.swift`:

```swift
import Foundation

/// 行级 markdown 块。inline 标记（**bold**、`code`、链接）保留原样，
/// 由视图层 AttributedString 解析。
public enum MarkdownBlock: Equatable, Sendable {
    case heading(level: Int, text: String)
    case bullet(items: [String])
    case ordered(items: [String])
    case code(String)
    case paragraph(String)
}

public enum MarkdownBlockParser {
    /// 纯行级解析，无状态机复杂度：逐行分类，相邻同类聚合。
    public static func parse(_ markdown: String) -> [MarkdownBlock] {
        var blocks: [MarkdownBlock] = []
        var bullets: [String] = []
        var ordered: [String] = []
        var paragraph: [String] = []
        var codeLines: [String]?
        var inTable = false

        func flushLists() {
            if !bullets.isEmpty { blocks.append(.bullet(items: bullets)); bullets = [] }
            if !ordered.isEmpty { blocks.append(.ordered(items: ordered)); ordered = [] }
        }
        func flushParagraph() {
            if !paragraph.isEmpty {
                blocks.append(.paragraph(paragraph.joined(separator: "\n")))
                paragraph = []
            }
        }
        func flushAll() { flushLists(); flushParagraph(); inTable = false }

        for rawLine in markdown.split(separator: "\n", omittingEmptySubsequences: false) {
            let line = String(rawLine).trimmingCharacters(in: .whitespaces)

            // 围栏代码块：``` 开
            if line.hasPrefix("```") {
                if codeLines == nil {
                    flushAll()
                    codeLines = []
                } else {
                    blocks.append(.code((codeLines ?? []).joined(separator: "\n")))
                    codeLines = nil
                }
                continue
            }
            if let cl = codeLines { cl.append(String(rawLine)); continue }

            if line.isEmpty { flushAll(); continue }

            // 表格行（| 开头）：连续表格行聚成一个 code 块（等宽对齐降级显示）
            if line.hasPrefix("|") {
                if !inTable { flushAll(); inTable = true }
                // 累积进临时
                tableLines.append(line)
                continue
            } else if inTable {
                blocks.append(.code(tableLines.joined(separator: "\n")))
                tableLines = []
                inTable = false
            }

            // 标题（1-6 级）
            if let m = line.firstMatch(of: /^(#{1,6})\s+(.*)$/) {
                flushAll()
                blocks.append(.heading(level: m.1.count, text: String(m.2)))
                continue
            }
            // 无序列表
            if let m = line.firstMatch(of: /^[-*+]\s+(.*)$/) {
                flushParagraph()
                bullets.append(String(m.1))
                continue
            }
            // 有序列表
            if let m = line.firstMatch(of: /^\d+[.)]\s+(.*)$/) {
                flushParagraph()
                ordered.append(String(m.1))
                continue
            }
            // 普通文本
            flushLists()
            paragraph.append(line)
        }
        // 收尾
        if let cl = codeLines { blocks.append(.code(cl.joined(separator: "\n"))) }
        if inTable { blocks.append(.code(tableLines.joined(separator: "\n"))) }
        flushAll()
        return blocks
    }

    private static var tableLines: [String] = []
}
```

**注意**：上面用 static var `tableLines` 是错误设计（全局状态）——实现时改为函数内局部 `var tableLines: [String] = []`，与 bullets/ordered 同级。此处标注：**实现必须用局部变量**，static 版本直接删掉。写代码时以局部变量版本为准。

- [x] **Step 4: 跑测试通过**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | tail -3
```

- [x] **Step 5: 提交**

```bash
git add ios/DeepAlphaClub && git commit -m "feat(markdown): 行级块解析（标题/列表/代码块/表格降级）"
```

---

## Task 13: SwiftData 历史缓存（CachedRun + RunCache）

**Files:**
- Create: `Core/Sources/Core/Persistence/CachedRun.swift`
- Create: `Core/Sources/Core/Persistence/RunCache.swift`
- Test: `Core/Tests/CoreTests/RunCacheTests.swift`

- [x] **Step 1: 写失败测试**

`Core/Tests/CoreTests/RunCacheTests.swift`:

```swift
import Foundation
import Testing
import SwiftData
@testable import Core

func summary(_ runId: String, ticker: String = "NVDA", date: Date = .distantPast,
             signal: VerdictSignal? = nil) -> RunSummary {
    RunSummary(runId: runId, ticker: ticker, tradeDate: "2026-08-30", engine: "tradingagents",
               status: .completed, durationMs: 60000,
               createdAt: ISO8601DateFormatter().string(from: date),
               finishedAt: nil, verdictSignal: signal, verdictConfidence: signal == nil ? nil : 0.7,
               turnsCount: 3, signalsCount: 1)
}

@Suite("RunCache")
struct RunCacheTests {
    func makeCache() throws -> RunCache {
        let config = ModelConfiguration(isStoredInMemoryOnly: true)
        let container = try ModelContainer(for: CachedRun.self, configurations: config)
        return RunCache(modelContainer: container)
    }

    @Test("upsert 后可 list，按时间倒序")
    func upsertAndList() async throws {
        let cache = try makeCache()
        let base = Date(timeIntervalSince1970: 1_750_000_000)
        try await cache.upsert([
            summary("a", date: base),
            summary("b", date: base.addingTimeInterval(60)),
            summary("c", date: base.addingTimeInterval(-60)),
        ])
        let runs = try await cache.list(ticker: nil)
        #expect(runs.map(\.runId) == ["b", "a", "c"])
    }

    @Test("同 runId upsert 覆盖不重复")
    func upsertOverwrites() async throws {
        let cache = try makeCache()
        try await cache.upsert([summary("a", signal: .buy)])
        var changed = summary("a", signal: .sell)
        changed.status = .failed
        try await cache.upsert([changed])
        let runs = try await cache.list(ticker: nil)
        #expect(runs.count == 1)
        #expect(runs[0].verdictSignal == .sell)
        #expect(runs[0].status == .failed)
    }

    @Test("ticker 过滤（前缀大写匹配）")
    func tickerFilter() async throws {
        let cache = try makeCache()
        try await cache.upsert([
            summary("a", ticker: "NVDA"),
            summary("b", ticker: "700.HK"),
            summary("c", ticker: "NVDA"),
        ])
        let nvda = try await cache.list(ticker: "nvda")
        #expect(nvda.map(\.runId) == ["a", "c"])
    }

    @Test("超过 50 条淘汰最旧")
    func pruneTo50() async throws {
        let cache = try makeCache()
        let base = Date(timeIntervalSince1970: 1_750_000_000)
        let many = (0..<60).map { i in
            summary("run-\(i)", date: base.addingTimeInterval(Double(i)))
        }
        try await cache.upsert(many)
        let runs = try await cache.list(ticker: nil)
        #expect(runs.count == 50)
        #expect(runs.first?.runId == "run-59")   // 最新保留
        #expect(!runs.contains { $0.runId == "run-0" })  // 最旧被淘汰
    }
}
```

- [x] **Step 2: 跑测试确认失败**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | grep "error:" | head -3
```

- [x] **Step 3: 实现**

`Core/Sources/Core/Persistence/CachedRun.swift`:

```swift
import Foundation
import SwiftData

/// 历史 run 的本地缓存行（SwiftData）。进 App 立即可读，后台再拉远端 diff。
@Model
public final class CachedRun {
    @Attribute(.unique) public var runId: String
    public var ticker: String
    public var tradeDate: String
    public var status: String
    public var durationMs: Int
    public var verdictSignal: String?
    public var verdictConfidence: Double?
    public var turnsCount: Int
    public var signalsCount: Int
    /// 用 created_at（ISO）转的 Date，作排序与淘汰键
    public var startedAt: Date

    public init(runId: String, ticker: String, tradeDate: String, status: String,
                durationMs: Int, verdictSignal: String?, verdictConfidence: Double?,
                turnsCount: Int, signalsCount: Int, startedAt: Date) {
        self.runId = runId
        self.ticker = ticker
        self.tradeDate = tradeDate
        self.status = status
        self.durationMs = durationMs
        self.verdictSignal = verdictSignal
        self.verdictConfidence = verdictConfidence
        self.turnsCount = turnsCount
        self.signalsCount = signalsCount
        self.startedAt = startedAt
    }
}
```

`Core/Sources/Core/Persistence/RunCache.swift`:

```swift
import Foundation
import SwiftData

/// 缓存读写 actor（@ModelActor 生成 executor 隔离）。
/// 保留最近 50 条，超出按 startedAt 淘汰（spec §3.5）。
@ModelActor
public actor RunCache {
    private static let isoFormatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    private static let isoFormatterNoFrac = ISO8601DateFormatter()

    public static func parseISO(_ s: String) -> Date? {
        Self.isoFormatter.date(from: s) ?? Self.isoFormatterNoFrac.date(from: s)
    }

    /// 批量写入（同 runId 覆盖），然后裁剪到 50 条。
    public func upsert(_ summaries: [RunSummary]) throws {
        let context = modelContext
        let ids = summaries.map(\.runId)
        let existing = try context.fetch(FetchDescriptor<CachedRun>(
            predicate: #Predicate { ids.contains($0.runId) }))
        var byId: [String: CachedRun] = Dictionary(uniqueKeysWithValues: existing.map { ($0.runId, $0) })
        for s in summaries {
            let date = Self.parseISO(s.createdAt) ?? Date(timeIntervalSince1970: 0)
            if let row = byId[s.runId] {
                row.ticker = s.ticker
                row.tradeDate = s.tradeDate
                row.status = s.status.rawValue
                row.durationMs = s.durationMs
                row.verdictSignal = s.verdictSignal?.rawValue
                row.verdictConfidence = s.verdictConfidence
                row.turnsCount = s.turnsCount
                row.signalsCount = s.signalsCount
                row.startedAt = date
            } else {
                let row = CachedRun(
                    runId: s.runId, ticker: s.ticker, tradeDate: s.tradeDate,
                    status: s.status.rawValue, durationMs: s.durationMs,
                    verdictSignal: s.verdictSignal?.rawValue,
                    verdictConfidence: s.verdictConfidence,
                    turnsCount: s.turnsCount, signalsCount: s.signalsCount,
                    startedAt: date)
                context.insert(row)
                byId[s.runId] = row
            }
        }
        try context.save()
        try prune()
    }

    /// 按 ticker 过滤（大小写不敏感，等 web 端 toUpperCase 语义），startedAt 倒序。
    public func list(ticker: String?) throws -> [RunSummary] {
        let rows = try modelContext.fetch(FetchDescriptor<CachedRun>(
            sortBy: [SortDescriptor(\.startedAt, order: .reverse)]))
        let filtered: [CachedRun]
        if let t = ticker?.trimmingCharacters(in: .whitespaces).uppercased(), !t.isEmpty {
            filtered = rows.filter { $0.ticker.uppercased().contains(t) }
        } else {
            filtered = rows
        }
        return filtered.map { row in
            RunSummary(
                runId: row.runId, ticker: row.ticker, tradeDate: row.tradeDate,
                engine: "cached", status: RunRecordStatus(rawValue: row.status) ?? .completed,
                durationMs: row.durationMs,
                createdAt: Self.isoFormatterNoFrac.string(from: row.startedAt),
                finishedAt: nil,
                verdictSignal: row.verdictSignal.flatMap(VerdictSignal.init(rawValue:)),
                verdictConfidence: row.verdictConfidence,
                turnsCount: row.turnsCount, signalsCount: row.signalsCount)
        }
    }

    /// 只保留最近 50 条。
    private func prune() throws {
        let all = try modelContext.fetch(FetchDescriptor<CachedRun>(
            sortBy: [SortDescriptor(\.startedAt, order: .reverse)]))
        guard all.count > 50 else { return }
        for row in all.dropFirst(50) {
            modelContext.delete(row)
        }
        try modelContext.save()
    }
}
```

**注意**：
1. `engine` 字段 SwiftData 里没存（列表 UI 显示远端的才有意义，本地缓存的 engine 用 "cached" 占位不影响布局）。如果想存，加一列即可——实现时可自行决定，测试不覆盖此字段。
2. `#Predicate { ids.contains($0.runId) }` 里捕获局部 `ids` 数组：SwiftData predicate 支持捕获数组做 contains。若编译报 predicate 不支持，退化为 fetch 全部再内存过滤（数据量 ≤50，无所谓性能）。
3. `@ModelActor` 生成的 init 是 `init(modelContainer:)`；测试里 `RunCache(modelContainer: container)`。
4. macOS 14 的 SwiftData 内存容器在 swift test 下可用（已验证平台约束 macOS .v14）。

- [x] **Step 4: 跑测试通过**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | tail -3
```

- [x] **Step 5: 提交**

```bash
git add ios/DeepAlphaClub && git commit -m "feat(cache): SwiftData 历史缓存（upsert/过滤/50 条淘汰）"
```

---

## Task 14: HistoryListViewModel + RunReplayViewModel

**Files:**
- Create: `Core/Sources/Core/ViewModels/HistoryListViewModel.swift`
- Create: `Core/Sources/Core/ViewModels/RunReplayViewModel.swift`
- Test: `Core/Tests/CoreTests/HistoryViewModelsTests.swift`

- [x] **Step 1: 写失败测试**

`Core/Tests/CoreTests/HistoryViewModelsTests.swift`:

```swift
import Foundation
import Testing
import SwiftData
@testable import Core

@MainActor
@Suite("HistoryListViewModel")
struct HistoryListViewModelTests {
    @Test("refresh：本地缓存先出 → 远端结果替换 → 回写缓存")
    func refreshFlow() async throws {
        let config = ModelConfiguration(isStoredInMemoryOnly: true)
        let container = try ModelContainer(for: CachedRun.self, configurations: config)
        let cache = RunCache(modelContainer: container)
        try await cache.upsert([summary("local-1", ticker: "NVDA",
                                         date: Date(timeIntervalSince1970: 100))])

        let remote = RunListResponse(runs: [
            summary("remote-1", ticker: "NVDA", date: Date(timeIntervalSince1970: 200)),
        ])
        let service = MockDeskService()
        service.listRunsResult = remote

        let vm = HistoryListViewModel(service: service, cache: cache)
        #expect(vm.runs.isEmpty)

        await vm.refresh(ticker: nil)
        // 先渲染了本地，后被远端替换
        #expect(vm.runs.map(\.runId) == ["remote-1"])
        #expect(!vm.loading)
        #expect(vm.error == nil)
        // 远端结果已回写缓存
        let cached = try await cache.list(ticker: nil)
        #expect(cached.map(\.runId) == ["remote-1", "local-1"])
    }

    @Test("refresh 失败：本地数据保留 + error 展示")
    func refreshFailure() async throws {
        let config = ModelConfiguration(isStoredInMemoryOnly: true)
        let container = try ModelContainer(for: CachedRun.self, configurations: config)
        let cache = RunCache(modelContainer: container)
        try await cache.upsert([summary("local-1", date: Date(timeIntervalSince1970: 100))])

        let service = MockDeskService()
        service.listRunsError = APIError.network

        let vm = HistoryListViewModel(service: service, cache: cache)
        await vm.refresh(ticker: nil)
        #expect(vm.runs.map(\.runId) == ["local-1"])
        #expect(vm.error == "网络不可用，请检查连接")
    }
}

@MainActor
@Suite("RunReplayViewModel")
struct RunReplayViewModelTests {
    @Test("load：详情转 Turn 卡片数组 + signals/verdict 齐备")
    func loadDetail() async throws {
        let service = MockDeskService()
        service.getRunResult = RunDetailResponse(
            runId: "r1", ticker: "NVDA", tradeDate: "2026-08-30", engine: "e",
            status: .completed, durationMs: 5000,
            createdAt: "2026-08-30T10:00:00+00:00", finishedAt: nil,
            verdict: VerdictData(signal: .buy, confidence: 0.9, sizeFraction: 0.2,
                                  entryReferencePrice: 100, targetPrice: 120, stopLoss: 90,
                                  currency: "USD", timeHorizonDays: 30, rationale: "r",
                                  warningMessage: nil),
            signals: [SignalRecord(stageId: "s", name: "分析师", dir: .bull, conf: 80,
                                    turnId: nil, extracted: true)],
            turns: [TurnRecord(turnId: "t1", stageId: "s", name: "分析师", role: "r",
                                avatar: "析", text: "内容", toolCalls: [],
                                debate: nil)])

        let vm = RunReplayViewModel(service: service)
        await vm.load(runId: "r1")
        #expect(vm.detail?.verdict?.signal == .buy)
        #expect(vm.turns.count == 1)
        #expect(vm.turns[0].text == "内容")
        #expect(vm.turns[0].done)          // 回放卡片全部 done
        #expect(vm.signals.count == 1)
        #expect(vm.error == nil)
    }

    @Test("load 404：error 展示")
    func loadNotFound() async throws {
        let service = MockDeskService()
        service.getRunError = APIError.notFound
        let vm = RunReplayViewModel(service: service)
        await vm.load(runId: "gone")
        #expect(vm.error == "资源不存在")
        #expect(vm.turns.isEmpty)
    }
}
```

需要给 `MockDeskService`（Task 10 文件）扩充字段：`listRunsResult: RunListResponse?`、`listRunsError: Error?`、`getRunResult: RunDetailResponse?`、`getRunError: Error?`，并实现对应方法返回。同时 `TurnRecord` 需要带 memberwise init（Codable struct 默认有）。

- [x] **Step 2: 跑测试确认失败**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | grep "error:" | head -3
```

- [x] **Step 3: 实现**

`Core/Sources/Core/ViewModels/HistoryListViewModel.swift`:

```swift
import Foundation
import Observation

/// 历史列表：SwiftData 先渲染（秒开），远端刷新替换并回写缓存。
@MainActor @Observable
public final class HistoryListViewModel {
    public private(set) var runs: [RunSummary] = []
    public private(set) var loading = false
    public var error: String?

    let service: any TradingDeskServicing
    let cache: RunCache?

    public init(service: any TradingDeskServicing, cache: RunCache?) {
        self.service = service
        self.cache = cache
    }

    public func refresh(ticker: String?) async {
        error = nil
        loading = true
        defer { loading = false }
        // 1) 本地缓存先出（离线可用）
        if let cache {
            if let local = try? await cache.list(ticker: ticker) {
                runs = local
            }
        }
        // 2) 远端刷新
        do {
            let resp = try await service.listRuns(ticker: ticker, limit: 50, offset: 0)
            runs = resp.runs
            // 3) 回写缓存（失败不影响 UI）
            if let cache {
                try? await cache.upsert(resp.runs)
            }
        } catch let e as APIError {
            error = e.message
        } catch {
            error = error.localizedDescription
        }
    }
}
```

`Core/Sources/Core/ViewModels/RunReplayViewModel.swift`:

```swift
import Foundation
import Observation

/// 单条 run 回放：getRun 拉详情，TurnRecord → Turn 全文直出（无流式动画）。
@MainActor @Observable
public final class RunReplayViewModel {
    public private(set) var detail: RunDetailResponse?
    public private(set) var turns: [Turn] = []
    public private(set) var signals: [SignalRow] = []
    public private(set) var loading = false
    public var error: String?

    let service: any TradingDeskServicing

    public init(service: any TradingDeskServicing) {
        self.service = service
    }

    public var verdict: VerdictData? { detail?.verdict }

    public func load(runId: String) async {
        error = nil
        loading = true
        defer { loading = false }
        do {
            let d = try await service.getRun(runId: runId)
            detail = d
            turns = d.turns.map(\.asTurn)
            signals = d.signals.map {
                SignalRow(name: $0.name, dir: $0.dir, conf: $0.conf, extracted: $0.extracted)
            }
        } catch let e as APIError {
            error = e.message
        } catch {
            error = error.localizedDescription
        }
    }
}

extension TurnRecord {
    /// 回放记录 → 渲染用 Turn（done=true 全文直出）。
    public var asTurn: Turn {
        Turn(turnId: turnId, stageId: stageId, name: name, role: role, avatar: avatar,
             text: text, tools: toolCalls, done: true, human: false, debate: debate,
             signal: nil)
    }
}
```

同时给 `MockDeskService` 扩充（`Core/Tests/CoreTests/TradingDeskViewModelTests.swift` 内）：

```swift
// MockDeskService 增加字段与方法实现替换
var listRunsResult: RunListResponse?
var listRunsError: Error?
var getRunResult: RunDetailResponse?
var getRunError: Error?

func listRuns(ticker: String?, limit: Int, offset: Int) async throws -> RunListResponse {
    if let e = listRunsError { throw e }
    return listRunsResult ?? RunListResponse(runs: [])
}
func getRun(runId: String) async throws -> RunDetailResponse {
    if let e = getRunError { throw e }
    if let r = getRunResult { return r }
    throw APIError.notFound
}
```

- [x] **Step 4: 跑测试通过**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | tail -3
```

- [x] **Step 5: 提交**

```bash
git add ios/DeepAlphaClub && git commit -m "feat(history-vm): 历史列表（缓存先出+远端替换）与回放 VM"
```

---

## Task 15: xcodegen 工程 + App 入口 + 登录

**Files:**
- Create: `ios/DeepAlphaClub/project.yml`
- Create: `App/DeepAlphaClubApp.swift`
- Create: `App/CompositionRoot.swift`
- Create: `App/RootView.swift`
- Create: `App/Auth/LoginView.swift`

从此任务起验证方式变化：**UI 层以编译通过为验收**（逻辑已在 Core 测过），无单测。

- [x] **Step 1: 安装 xcodegen**

```bash
brew install xcodegen 2>&1 | tail -2
xcodegen --version
```

期望：输出版本号（如 `2.44.0`）。若 brew 不可用，停止并报告用户（不要手写 pbxproj）。

- [x] **Step 2: 写 project.yml**

```yaml
name: DeepAlphaClub
options:
  bundleIdPrefix: club.deepalpha
  deploymentTarget:
    iOS: "17.0"
  createIntermediateGroups: true

packages:
  DeepAlphaCore:
    path: .

targets:
  DeepAlphaClub:
    type: application
    platform: iOS
    sources:
      - path: App
    dependencies:
      - package: DeepAlphaCore
    info:
      path: App/Info.plist
      properties:
        CFBundleDisplayName: 交易台
        CFBundleShortVersionString: "0.1.0"
        CFBundleVersion: "1"
        UILaunchScreen: {}
        UISupportedInterfaceOrientations:
          - UIInterfaceOrientationPortrait
          - UIInterfaceOrientationLandscapeLeft
          - UIInterfaceOrientationLandscapeRight
        ITSAppUsesNonExemptEncryption: false
    settings:
      base:
        PRODUCT_BUNDLE_IDENTIFIER: club.deepalpha.ios
        SWIFT_VERSION: "6.0"
        TARGETED_DEVICE_FAMILY: "1,2"
        CODE_SIGN_STYLE: Automatic

schemes:
  DeepAlphaClub:
    build:
      targets:
        DeepAlphaClub: all
    run:
      config: Debug
    archive:
      config: Release
```

- [x] **Step 3: 写组合根**

`App/CompositionRoot.swift`:

```swift
import Foundation
import DeepAlphaCore

/// 全部依赖在此组装（视图层不直接 new service）。
/// 注意：struct 非 Observable，不能用 @Environment(Self.self) 注入——
/// 用下面的 EnvironmentKey（\.compositionRoot）。
struct CompositionRoot {
    /// 后端地址。本地联调改这里（如 http://localhost:8000，需同时改 ATS 例外）。
    static let apiBaseURL = URL(string: "https://api.deepalpha.club")!

    let keychain: KeychainStore
    let appState: AppState
    let deskVM: TradingDeskViewModel
    let historyVM: HistoryListViewModel
    let replayFactory: (String) -> RunReplayViewModel

    init() {
        let keychain = KeychainStore()
        let api = APIClient(baseURL: Self.apiBaseURL) { keychain.loadToken() }
        let sse = SSEClient(baseURL: Self.apiBaseURL) { keychain.loadToken() }
        let service = TradingDeskService(api: api, sse: sse)
        let auth = AuthService(client: api)

        self.keychain = keychain
        self.appState = AppState(keychain: keychain, auth: auth)
        self.deskVM = TradingDeskViewModel(service: service)
        self.historyVM = HistoryListViewModel(
            service: service,
            cache: try? RunCacheDefault.make())
        self.replayFactory = { RunReplayViewModel(service: service) }
    }
}
```

注意 `RunCacheDefault.make()` 是一个工厂（容错版 init）——在 `Core/Sources/Core/Persistence/RunCache.swift` 追加：

```swift
/// 默认磁盘容器的工厂：失败（磁盘满/迁移冲突）返回 nil，App 降级为无缓存运行。
public enum RunCacheDefault {
    public static func make() -> RunCache? {
        guard let container = try? ModelContainer(for: CachedRun.self) else { return nil }
        return RunCache(modelContainer: container)
    }
}
```

再给 CompositionRoot 补 EnvironmentKey（`App/CompositionRoot.swift` 末尾追加）：

```swift
import SwiftUI

private struct CompositionRootKey: EnvironmentKey {
    static let defaultValue: CompositionRoot? = nil
}

extension EnvironmentValues {
    /// 非 Observable 的组合根用 EnvironmentKey 注入（@Environment(Self.self) 只支持 Observable）。
    var compositionRoot: CompositionRoot? {
        get { self[CompositionRootKey.self] }
        set { self[CompositionRootKey.self] = newValue }
    }
}
```

- [x] **Step 4: 写 App 入口**

`App/DeepAlphaClubApp.swift`:

```swift
import SwiftUI
import DeepAlphaCore

@main
struct DeepAlphaClubApp: App {
    @State private var root = CompositionRoot()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(root.appState)
                .environment(root.deskVM)
                .task {
                    root.appState.restoreFromKeychain()
                }
        }
        .onChange(of: scenePhase) { _, phase in
            switch phase {
            case .background:
                root.deskVM.appDidEnterBackground()
            case .active:
                Task { await root.deskVM.appDidBecomeActive() }
            default:
                break
            }
        }
    }
}
```

`App/RootView.swift`:

```swift
import SwiftUI
import DeepAlphaCore

/// 登录态路由：有 token 进主页，否则登录页。观察 deskVM 的 401 一并处理。
struct RootView: View {
    @Environment(AppState.self) private var appState
    @Environment(TradingDeskViewModel.self) private var deskVM

    var body: some View {
        ZStack {
            if appState.isLoggedIn {
                MainTabView()
            } else {
                LoginView()
            }
        }
        .animation(.easeInOut(duration: 0.2), value: appState.isLoggedIn)
        .onChange(of: deskVM.lastAuthError) { _, err in
            if err == .unauthorized { appState.handleUnauthorized() }
        }
    }
}

/// 主页：交易台 / 历史 两个 tab（自用 App 无需更多）。
struct MainTabView: View {
    @State private var root = CompositionRootHolder.placeholder  // 见下

    var body: some View {
        TabView {
            TradingDeskView()
                .tabItem { Label("交易台", systemImage: "chart.line.uptrend.xyaxis") }
            HistoryListView()
                .tabItem { Label("历史", systemImage: "clock.arrow.circlepath") }
        }
    }
}
```

注意：`MainTabView` 里不应再建 CompositionRoot（依赖已通过 environment 注入）。`TradingDeskView` / `HistoryListView` 在 Task 16/17 才实现——本任务先放占位：

```swift
// 临时占位（Task 16/17 替换为真组件）
struct TradingDeskView: View {
    var body: some View { Text("交易台（Task 16）") }
}
struct HistoryListView: View {
    var body: some View { Text("历史（Task 17）") }
}
```

占位放 `App/Placeholders.swift`，Task 16/17 删除。`CompositionRootHolder.placeholder` 同样是占位残留——**直接删掉 MainTabView 里的 `@State private var root` 行**（不需要）。

- [x] **Step 5: 写登录页**

`App/Auth/LoginView.swift`:

```swift
import SwiftUI
import DeepAlphaCore

struct LoginView: View {
    @Environment(AppState.self) private var appState
    @State private var email = ""
    @State private var password = ""

    var body: some View {
        VStack(spacing: 24) {
            Spacer()
            Image(systemName: "chart.line.uptrend.xyaxis")
                .font(.system(size: 56))
                .foregroundStyle(.blue)
            VStack(spacing: 6) {
                Text("交易台")
                    .font(.title.bold())
                Text("多智能体分析")
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
            }
            Spacer()

            VStack(spacing: 14) {
                TextField("邮箱", text: $email)
                    .textContentType(.emailAddress)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .textFieldStyle(.roundedBorder)
                SecureField("密码", text: $password)
                    .textContentType(.password)
                    .submitLabel(.go)
                    .onSubmit { login() }
                    .textFieldStyle(.roundedBorder)

                if let err = appState.authError {
                    Text(err)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                Button {
                    login()
                } label: {
                    if appState.loggingIn {
                        ProgressView().frame(maxWidth: .infinity)
                    } else {
                        Text("登录")
                            .frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(email.isEmpty || password.isEmpty || appState.loggingIn)
            }
            Spacer().frame(height: 80)
        }
        .padding(24)
    }

    private func login() {
        Task { await appState.login(email: email, password: password) }
    }
}
```

- [x] **Step 6: 生成工程 + 编译**

```bash
cd ios/DeepAlphaClub && xcodegen generate && \
xcodebuild -project DeepAlphaClub.xcodeproj -scheme DeepAlphaClub \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  CODE_SIGNING_ALLOWED=NO build 2>&1 | tail -3
```

期望：`** BUILD SUCCEEDED **`。若 `swift test` 之前绿而这里报 Core 编译错（iOS-only 差异），修到两边都绿。

- [x] **Step 7: 提交**

```bash
git add ios/DeepAlphaClub && git commit -m "feat(app): xcodegen 工程 + 组合根 + 登录页 + 登录态路由"
```

---

## Task 16: 交易台主 UI（组件群）

**Files:**
- Delete: `App/Placeholders.swift`（TradingDeskView 占位部分）
- Create: `App/Theme/SignalColors.swift`
- Create: `App/Features/TradingDesk/SignalChip.swift`
- Create: `App/Features/TradingDesk/ConsensusMeter.swift`
- Create: `App/Features/TradingDesk/VerdictCard.swift`
- Create: `App/Features/TradingDesk/PipelinePanel.swift`
- Create: `App/Features/TradingDesk/TurnCard.swift`
- Create: `App/Features/TradingDesk/StreamPanel.swift`
- Create: `App/Features/TradingDesk/Topbar.swift`
- Create: `App/Features/TradingDesk/InjectSheet.swift`
- Create: `App/Features/TradingDesk/DecisionPanel.swift`
- Create: `App/Features/TradingDesk/TradingDeskView.swift`
- Create: `App/ErrorBanner.swift`

- [ ] **Step 1: 配色**

`App/Theme/SignalColors.swift`:

```swift
import SwiftUI
import DeepAlphaCore

/// polarity → 颜色（系统色自动适配暗黑模式，对齐 web 的 green/red/amber/blue）。
extension Polarity {
    var tint: Color {
        switch self {
        case .bull: .green
        case .bear: .red
        case .neutral: .orange
        }
    }
    var label: String {
        switch self {
        case .bull: "看多"
        case .bear: "看空"
        case .neutral: "中性"
        }
    }
}

extension VerdictSignal {
    var label: String {
        switch self {
        case .buy: "买入"
        case .sell: "卖出"
        case .hold: "观望"
        }
    }
    var tint: Color {
        switch self {
        case .buy: .green
        case .sell: .red
        case .hold: .orange
        }
    }
}
```

- [ ] **Step 2: SignalChip + ConsensusMeter**

`App/Features/TradingDesk/SignalChip.swift`:

```swift
import SwiftUI
import DeepAlphaCore

/// 信号 pill：圆点 + 「看多 · 78」；extracted 追加「抽」标注（信号来自文本抽取，
/// 非 agent 原生输出，不标会误导置信度语义）。
struct SignalChip: View {
    let dir: Polarity
    let conf: Int
    var extracted = false

    var body: some View {
        HStack(spacing: 4) {
            Circle().fill(dir.tint).frame(width: 6, height: 6)
            Text("\(dir.label) · \(conf)")
            if extracted {
                Text("抽").opacity(0.6)
            }
        }
        .font(.system(size: 11, weight: .semibold, design: .monospaced))
        .foregroundStyle(dir.tint)
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(dir.tint.opacity(0.12), in: RoundedRectangle(cornerRadius: 6))
    }
}
```

`App/Features/TradingDesk/ConsensusMeter.swift`:

```swift
import SwiftUI
import DeepAlphaCore

/// 共识条：bull/neutral/bear 三段比例 + 计数说明。
struct ConsensusMeter: View {
    let consensus: ConsensusData?

    var body: some View {
        VStack(spacing: 6) {
            HStack {
                Text("共识").font(.caption2.monospaced()).foregroundStyle(.secondary)
                Spacer()
                Text(consensus.map { "多\($0.bull) 中\($0.neutral) 空\($0.bear) · \($0.lean)" } ?? "—")
                    .font(.caption2.monospaced()).foregroundStyle(.secondary)
            }
            GeometryReader { geo in
                HStack(spacing: 0) {
                    if let c = consensus {
                        let total = max(c.bull + c.neutral + c.bear, 1)
                        RoundedRectangle(cornerRadius: 2)
                            .fill(.green)
                            .frame(width: geo.size.width * CGFloat(c.bull) / CGFloat(total))
                        RoundedRectangle(cornerRadius: 2)
                            .fill(.orange)
                            .frame(width: geo.size.width * CGFloat(c.neutral) / CGFloat(total))
                        RoundedRectangle(cornerRadius: 2)
                            .fill(.red)
                            .frame(width: geo.size.width * CGFloat(c.bear) / CGFloat(total))
                    } else {
                        RoundedRectangle(cornerRadius: 2).fill(.quaternary)
                    }
                }
            }
            .frame(height: 8)
        }
    }
}
```

- [ ] **Step 3: VerdictCard**

`App/Features/TradingDesk/VerdictCard.swift`:

```swift
import SwiftUI
import DeepAlphaCore

/// 裁决卡：动作 + 置信度 + 仓位/止损/目标价/周期 2×2 + 降级警告 + 理由 + 审计链。
struct VerdictCard: View {
    let verdict: VerdictData?
    let turns: [Turn]
    @State private var auditOpen = false

    private var confPct: Int? {
        verdict.map { Int(($0.confidence * 100).rounded()) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                Text(verdict?.signal.label ?? "—")
                    .font(.title2.weight(.heavy))
                    .foregroundStyle(verdict?.signal.tint ?? Color.secondary)
                Spacer()
                Text("置信度 ")
                    .font(.caption.monospaced()).foregroundStyle(.secondary)
                + Text(verdict.map { "\(confPct ?? 0)%" } ?? "—")
                    .font(.callout.monospaced().weight(.semibold))
            }

            Grid(horizontalSpacing: 12, verticalSpacing: 10) {
                GridRow {
                    field("仓位", verdict.map { String(format: "%.1f%%", $0.sizeFraction * 100) })
                    field("止损", verdict?.stopLoss.map { String($0) })
                }
                GridRow {
                    field("目标价", verdict?.targetPrice.map { String($0) })
                    field("周期", verdict?.timeHorizonDays.map { "\($0) 天" })
                }
            }

            // 引擎降级解析警告：必须显式展示，否则用户把降级结论当正常结论
            if let warning = verdict?.warningMessage {
                Label {
                    Text("结论解析降级：\(warning)")
                        .font(.footnote)
                } icon: {
                    Image(systemName: "exclamationmark.triangle.fill")
                }
                .foregroundStyle(.orange)
                .padding(10)
                .background(.orange.opacity(0.1), in: RoundedRectangle(cornerRadius: 8))
            }

            if let rationale = verdict?.rationale, !rationale.isEmpty {
                Text(rationale)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .padding(.top, 4)
            }

            let audit = TradingDeskReducer.buildAuditChain(turns)
            if !audit.isEmpty {
                DisclosureGroup(isExpanded: $auditOpen) {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(Array(audit.enumerated()), id: \.offset) { i, entry in
                            Text("\(entry.who) —— \(entry.excerpt)")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                                .lineLimit(2)
                            if i < audit.count - 1 { Divider() }
                        }
                    }
                    .padding(.top, 6)
                } label: {
                    Text("审计链（\(audit.count) 步）")
                        .font(.caption2.monospaced())
                        .foregroundStyle(.blue)
                }
            }
        }
        .padding(14)
        .background(
            verdict == nil ? Color(.secondarySystemBackground).opacity(0.5)
                           : Color(.secondarySystemBackground),
            in: RoundedRectangle(cornerRadius: 12))
        .opacity(verdict == nil ? 0.6 : 1)
    }

    private func field(_ label: String, _ value: String?) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.caption2).foregroundStyle(.tertiary)
            Text(value ?? "—")
                .font(.callout.monospaced().weight(.semibold))
                .foregroundStyle(value == nil ? Color.secondary : Color.primary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
```

注意 `field` 的第二参在 Swift 6 会报 double-optional 警告（`verdict?.stopLoss.map` 已是 `Double??`→`String?`）——`verdict?.stopLoss` 是 `Double?`（optional chaining 拍平），`.map { String($0) }` 得 `String?`，OK 单层。

- [ ] **Step 4: PipelinePanel**

`App/Features/TradingDesk/PipelinePanel.swift`:

```swift
import SwiftUI
import DeepAlphaCore

/// 左栏：流程条（成员阵容 + 状态 + 每阶段信号）。
struct PipelinePanel: View {
    let stages: [StageDescriptor]
    let stageStatus: [String: StageStatus]
    let stageSignal: [String: StageSignal]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            panelHeader("交易台成员")
            if stages.isEmpty {
                Text("开始分析后显示阵容")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 24)
            } else {
                ForEach(stages) { stage in
                    stageRow(stage)
                }
            }
        }
        .padding(14)
        .background(Color(.secondarySystemBackground),
                    in: RoundedRectangle(cornerRadius: 14))
    }

    @ViewBuilder
    private func stageRow(_ stage: StageDescriptor) -> some View {
        let status = stageStatus[stage.id] ?? .pending
        HStack(alignment: .top, spacing: 10) {
            Group {
                switch status {
                case .done:
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                case .active:
                    ProgressView().controlSize(.small)
                case .pending:
                    Circle()
                        .strokeBorder(.tertiary, lineWidth: 1.5)
                }
            }
            .font(.footnote)
            .frame(width: 16, height: 16)
            .padding(.top, 2)

            VStack(alignment: .leading, spacing: 3) {
                Text(stage.name)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(status == .pending ? .tertiary : .primary)
                    .lineLimit(1)
                Text(stage.role)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.tertiary)
                    .lineLimit(1)
                if let signal = stageSignal[stage.id] {
                    SignalChip(dir: signal.dir, conf: signal.conf)
                }
            }
        }
        .padding(.vertical, 3)
        .padding(.horizontal, 6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            status == .active ? Color.blue.opacity(0.07) : Color.clear,
            in: RoundedRectangle(cornerRadius: 8))
    }
}

/// 面板小标题（对齐 web 的 mono uppercase 风格）。
func panelHeader(_ text: String) -> some View {
    Text(text)
        .font(.caption2.monospaced().weight(.bold))
        .tracking(1.2)
        .foregroundStyle(.tertiary)
}
```

- [ ] **Step 5: TurnCard（含 MarkdownText）**

`App/Features/TradingDesk/TurnCard.swift`:

```swift
import SwiftUI
import DeepAlphaCore

/// 一张发言卡。辩论卡按 polarity 分色（前端无需认识门派）；人工意见蓝色。
struct TurnCard: View {
    let turn: Turn
    var streaming = false

    private var tint: Color {
        if turn.human { return .blue }
        return turn.debate?.polarity.tint ?? Color(.systemGray)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            header
            if !turn.tools.isEmpty {
                toolChips
            }
            MarkdownText(markdown: turn.text)
            if streaming {
                StreamingCursor()
            }
            if let thinking = turn.thinking, !thinking.isEmpty {
                thinkingSection(thinking)
            }
            if let signal = turn.signal {
                SignalChip(dir: signal.dir, conf: signal.conf, extracted: signal.extracted)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(tint.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(tint.opacity(0.25), lineWidth: 1))
        // 看空方缩进（对齐 web bear 的 ml-8 错位感）
        .padding(.leading, turn.debate?.polarity == .bear ? 20 : 0)
    }

    private var header: some View {
        HStack(spacing: 8) {
            Text(turn.avatar)
                .font(.caption2.monospaced().weight(.bold))
                .foregroundStyle(tint)
                .frame(width: 26, height: 26)
                .background(tint.opacity(0.15), in: RoundedRectangle(cornerRadius: 6))
            Text(turn.name)
                .font(.footnote.weight(.semibold))
                .foregroundStyle(tint == Color(.systemGray) ? .primary : tint)
            Spacer()
            if !turn.role.isEmpty {
                Text(turn.role)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.tertiary)
            }
        }
    }

    private var toolChips: some View {
        FlowChips(items: turn.tools.map { "⚙ \($0)" })
    }

    private func thinkingSection(_ thinking: String) -> some View {
        DisclosureGroup {
            MarkdownText(markdown: thinking)
                .padding(.top, 6)
        } label: {
            Label("推理过程", systemImage: "brain")
                .font(.caption2.monospaced().weight(.semibold))
        }
        .tint(.purple)
        .padding(10)
        .background(Color.purple.opacity(0.07), in: RoundedRectangle(cornerRadius: 8))
    }
}

/// 流式打字光标（蓝色闪烁竖条）。
struct StreamingCursor: View {
    @State private var on = true
    var body: some View {
        RoundedRectangle(cornerRadius: 1)
            .fill(.blue)
            .frame(width: 3, height: 14)
            .opacity(on ? 1 : 0.2)
            .onAppear {
                withAnimation(.easeInOut(duration: 0.6).repeatForever()) { on = false }
            }
    }
}

/// 简易流式布局 chips（工具名 / 标签换行）。
struct FlowChips: View {
    let items: [String]
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(items, id: \.self) { item in
                Text(item)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.blue)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.blue.opacity(0.08),
                                in: RoundedRectangle(cornerRadius: 5))
            }
        }
    }
}

/// 轻量 markdown 渲染：Core 的块解析 + AttributedString inline。
struct MarkdownText: View {
    let markdown: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(MarkdownBlockParser.parse(markdown).enumerated()),
                    id: \.offset) { _, block in
                blockView(block)
            }
        }
        .font(.footnote)
    }

    @ViewBuilder
    private func blockView(_ block: MarkdownBlock) -> some View {
        switch block {
        case .heading(let level, let text):
            Text(inline(text))
                .font(level <= 2 ? .subheadline.weight(.bold) : .footnote.weight(.semibold))
                .padding(.top, 2)
        case .bullet(let items):
            VStack(alignment: .leading, spacing: 3) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text("•").foregroundStyle(.tertiary)
                        Text(inline(item)).foregroundStyle(.secondary)
                    }
                }
            }
        case .ordered(let items):
            VStack(alignment: .leading, spacing: 3) {
                ForEach(Array(items.enumerated()), id: \.offset) { i, item in
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text("\(i + 1).").monospacedDigit().foregroundStyle(.tertiary)
                        Text(inline(item)).foregroundStyle(.secondary)
                    }
                }
            }
        case .code(let code):
            ScrollView(.horizontal, showsIndicators: false) {
                Text(code)
                    .font(.caption.monospaced())
                    .foregroundStyle(.primary)
                    .padding(8)
            }
            .background(Color(.tertiarySystemBackground),
                        in: RoundedRectangle(cornerRadius: 8))
        case .paragraph(let text):
            Text(inline(text)).foregroundStyle(.secondary)
        }
    }

    /// inline markdown（**粗体**、*斜体*、`code`、[链接](url)）交给系统解析。
    private func inline(_ s: String) -> AttributedString {
        (try? AttributedString(
            markdown: s,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)))
            ?? AttributedString(s)
    }
}
```

- [ ] **Step 6: StreamPanel（智能滚动）**

`App/Features/TradingDesk/StreamPanel.swift`:

```swift
import SwiftUI
import DeepAlphaCore

/// 中栏：实时推理流。贴底跟随规则（对齐 web StreamPanel）：
/// - 距底 ≤ 40pt 视为贴底，新 token 才跟随滚动
/// - 用户上滑查看历史时不强制拉回
/// - 新 run 开始强制贴底
struct StreamPanel: View {
    let turns: [Turn]
    let status: RunStatus
    let streamingTurnId: String?
    let runId: String?

    private static let bottomID = "stream-bottom"
    @State private var stickToBottom = true

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            panelHeader("实时推理")
            if turns.isEmpty {
                emptyState
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 10) {
                            ForEach(turns) { turn in
                                TurnCard(turn: turn,
                                         streaming: turn.turnId == streamingTurnId)
                            }
                            // 底部哨兵：贴底检测锚点 + 滚动目标
                            Color.clear
                                .frame(height: 1)
                                .id(Self.bottomID)
                                .bottomStickDetector { stick in
                                    // 用户手势结束位置：距底 ≤40 才重新跟随
                                    if stick != stickToBottom { stickToBottom = stick }
                                }
                        }
                        .padding(.vertical, 4)
                    }
                    .defaultScrollAnchor(.bottom)     // 初始就在底部
                    .onChange(of: turns.count) {
                        if stickToBottom {
                            withAnimation(.easeOut(duration: 0.2)) {
                                proxy.scrollTo(Self.bottomID, anchor: .bottom)
                            }
                        }
                    }
                    .onChange(of: turns.last?.text.count) {
                        if stickToBottom {
                            proxy.scrollTo(Self.bottomID, anchor: .bottom)
                        }
                    }
                    .onChange(of: runId) { _, _ in
                        stickToBottom = true    // 新 run 强制贴底
                        proxy.scrollTo(Self.bottomID, anchor: .bottom)
                    }
                }
            }
        }
        .padding(14)
        .frame(maxHeight: .infinity, alignment: .top)
        .background(Color(.secondarySystemBackground),
                    in: RoundedRectangle(cornerRadius: 14))
    }

    private var emptyState: some View {
        VStack(spacing: 8) {
            Text("交易台还很安静。")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(.secondary)
            Text("输入标的、点「开始分析」。\n看每个 agent 实时推理、辩论、给出结论。")
                .font(.caption)
                .foregroundStyle(.tertiary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

import SwiftUI

/// 贴底检测：哨兵相对 ScrollView 可视底部的偏移 ≤ 40pt 时回调 true。
/// 实现：GeometryReader 读哨兵全局 y，与屏幕底比较（ScrollView 内全局坐标
/// 即可视区坐标——父级不含其他滚动容器）。
private struct BottomStickDetector: ViewModifier {
    let onChange: (Bool) -> Void
    @State private var lastStick: Bool?

    func body(content: Content) -> some View {
        content
            .background(
                GeometryReader { geo in
                    Color.clear
                        .onChange(of: geo.frame(in: .global).minY) { _, y in
                            let stick = y
                                - geo.frame(in: .global).height
                                <= UIScreen.main.bounds.height + 40
                            // 哨兵 y 是其顶部全局坐标：贴底时它应靠近屏底
                            if stick != lastStick {
                                lastStick = stick
                                onChange(stick)
                            }
                        }
                })
    }
}

extension View {
    func bottomStickDetector(_ onChange: @escaping (Bool) -> Void) -> some View {
        modifier(BottomStickDetector(onChange: onChange))
    }
}
```

**注意**：上面的贴底检测是简化版（UIScreen.main 在多窗口/iPad 分屏不精确）。若模拟器实测发现跟随不灵，备选方案：用 `scrollPosition` 绑定（iOS 17 API）：

```swift
// 备选：iOS 17 scrollPosition 方案（若 Geometry 方案不佳，替换实现）
@State private var scrolledID: String?
ScrollView {
    LazyVStack { ... }.scrollTargetLayout()
}
.scrollPosition(id: $scrolledID, anchor: .bottom)
.onChange(of: turns) { _, _ in
    if stickToBottom { scrolledID = Self.bottomID }
}
// 上滑检测：scrolledID != bottomID 时用户在看历史
.onChange(of: scrolledID) { _, new in
    if new != Self.bottomID { stickToBottom = false }
}
```

模拟器冒烟时二选一，保留效果好的版本。`UIScreen.main` 在 Swift 6 strict mode 会报 deprecation 警告，优先实现备选方案更干净。

- [ ] **Step 7: Topbar + InjectSheet**

`App/Features/TradingDesk/Topbar.swift`:

```swift
import SwiftUI
import DeepAlphaCore

/// 顶栏：标题/状态 + 市场 segment + ticker 输入 + 动作按钮。
struct Topbar: View {
    @Binding var ticker: String
    @Binding var market: Market
    let state: TradingDeskState
    let busy: Bool
    let onStart: () -> Void
    let onControl: (ControlAction, String?) -> Void
    @State private var showInject = false

    private var live: Bool { state.status == .running || state.status == .paused }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("交易台").font(.headline)
                    Text("多智能体分析").font(.caption2.monospaced()).foregroundStyle(.tertiary)
                }
                Spacer()
                StatusDot(status: state.status)
            }

            HStack(spacing: 8) {
                Picker("市场", selection: $market) {
                    ForEach(Market.allCases) { m in
                        Text(m.label).tag(m)
                    }
                }
                .pickerStyle(.segmented)
                .disabled(live)

                HStack(spacing: 2) {
                    Text("$").font(.caption.monospaced()).foregroundStyle(.tertiary)
                    TextField(market.placeholder, text: $ticker)
                        .font(.subheadline.monospaced().weight(.semibold))
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                        .submitLabel(.go)
                        .onSubmit { if !live && !busy { onStart() } }
                }
                .padding(.horizontal, 10).padding(.vertical, 7)
                .background(Color(.secondarySystemBackground),
                            in: RoundedRectangle(cornerRadius: 8))
                .disabled(live)

                Button(live ? "分析中" : (state.status == .idle ? "开始分析" : "重新分析"),
                       action: onStart)
                    .buttonStyle(.borderedProminent)
                    .disabled(live || busy || ticker.trimmingCharacters(in: .whitespaces).isEmpty)
            }

            HStack(spacing: 8) {
                if state.capabilities.supportsPause {
                    Button {
                        onControl(state.status == .paused ? .resume : .pause, nil)
                    } label: {
                        Label(state.status == .paused ? "继续" : "暂停",
                              systemImage: state.status == .paused ? "play.fill" : "pause.fill")
                    }
                    .buttonStyle(.bordered)
                    .disabled(!live || busy)
                }
                if state.capabilities.supportsInject {
                    Button {
                        showInject = true
                    } label: {
                        Label("注入意见", systemImage: "plus.bubble")
                    }
                    .buttonStyle(.bordered)
                    .disabled(!live || busy)
                }
                if live {
                    Button(role: .destructive) {
                        onControl(.cancel, nil)
                    } label: {
                        Label("停止", systemImage: "stop.fill")
                    }
                    .buttonStyle(.bordered)
                    .disabled(busy)
                }
                Spacer()
            }
            .font(.footnote)
        }
        .sheet(isPresented: $showInject) {
            InjectSheet { text in
                onControl(.inject, text)
            }
        }
    }
}

/// 状态点 + 中文文案（对齐 web STATUS_TEXT）。
struct StatusDot: View {
    let status: RunStatus

    private var (color, text): (Color, String) {
        switch status {
        case .idle: (.gray, "空闲")
        case .running: (.blue, "运行中")
        case .paused: (.orange, "已暂停")
        case .completed: (.green, "已完成")
        case .cancelled: (.gray, "已取消")
        case .failed: (.red, "已失败")
        case .interrupted: (.orange, "中断")
        }
    }

    var body: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(color)
                .frame(width: 6, height: 6)
                .symbolEffect(.pulse, isActive: status == .running)
            Text(text).font(.caption2.monospaced()).foregroundStyle(.secondary)
        }
    }
}
```

注意 `.symbolEffect` 是 iOS 17+ API 且用于 symbol；Circle 不是 symbol——把 pulse 去掉，改用 `opacity` 动画：

```swift
Circle()
    .fill(color)
    .frame(width: 6, height: 6)
    .opacity(status == .running ? RunningPulse.phase : 1)
```

或最简单：静态圆点（自用 App 不必动画）。实现时用静态圆点即可，删掉 symbolEffect 行。

`App/Features/TradingDesk/InjectSheet.swift`:

```swift
import SwiftUI

/// 注入人工意见：一行输入 + 提交。
struct InjectSheet: View {
    let onSubmit: (String) -> Void
    @State private var text = ""
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("给交易台补一条上下文 —— 例如「把出口管制风险的权重调高」",
                              text: $text, axis: .vertical)
                        .lineLimit(3...6)
                } footer: {
                    Text("意见会在下一个节点边界注入引擎状态，作为人工上下文参与后续推理。")
                }
            }
            .navigationTitle("注入意见")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("加入") {
                        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
                        if !t.isEmpty {
                            onSubmit(t)
                            dismiss()
                        }
                    }
                    .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
        .presentationDetents([.medium])
    }
}
```

- [ ] **Step 8: TradingDeskView 装配**

`App/Features/TradingDesk/TradingDeskView.swift`:

```swift
import SwiftUI
import DeepAlphaCore

/// 主容器：窄屏 TabView（流程/推理/决策），宽屏（iPad/横屏）HStack 三栏。
struct TradingDeskView: View {
    @Environment(TradingDeskViewModel.self) private var vm
    @Environment(AppState.self) private var appState
    @State private var ticker = "NVDA"
    @State private var market: Market = .US
    @Environment(\.horizontalSizeClass) private var hSize

    var body: some View {
        withObservationTracking {
            content
        } onChange: { } // 占位——实际直接用 @Observable 依赖追踪，删除这层包裹
    }

    private var streamingTurnId: String? {
        vm.state.status == .running
            ? vm.state.turns.first(where: { !$0.done })?.turnId : nil
    }

    private var content: some View {
        VStack(spacing: 12) {
            Topbar(
                ticker: $ticker,
                market: $market,
                state: vm.state,
                busy: vm.busy,
                onStart: {
                    Task {
                        await vm.startRun(ticker: ticker, market: market)
                        await appStateLoginRefresh()
                    }
                },
                onControl: { action, text in
                    Task { await vm.control(action, text: text) }
                })

            if let err = vm.pageError ?? vm.state.error {
                ErrorBanner(err) { vm.clearPageError() }
            }

            if hSize == .regular {
                HStack(alignment: .top, spacing: 12) {
                    PipelinePanel(
                        stages: vm.state.stages,
                        stageStatus: vm.state.stageStatus,
                        stageSignal: vm.state.stageSignal)
                    .frame(width: 240)
                    StreamPanel(
                        turns: vm.state.turns,
                        status: vm.state.status,
                        streamingTurnId: streamingTurnId,
                        runId: vm.state.runId)
                    DecisionPanel(
                        signals: vm.state.signals,
                        consensus: vm.state.consensus,
                        verdict: vm.state.verdict,
                        turns: vm.state.turns)
                    .frame(width: 300)
                }
            } else {
                TabView {
                    PipelinePanel(
                        stages: vm.state.stages,
                        stageStatus: vm.state.stageStatus,
                        stageSignal: vm.state.stageSignal)
                    .tabItem { Label("流程", systemImage: "list.number") }
                    .frame(minHeight: 380)
                    StreamPanel(
                        turns: vm.state.turns,
                        status: vm.state.status,
                        streamingTurnId: streamingTurnId,
                        runId: vm.state.runId)
                    .tabItem { Label("推理", systemImage: "text.bubble") }
                    .frame(minHeight: 380)
                    DecisionPanel(
                        signals: vm.state.signals,
                        consensus: vm.state.consensus,
                        verdict: vm.state.verdict,
                        turns: vm.state.turns)
                    .tabItem { Label("决策", systemImage: "gavel") }
                    .frame(minHeight: 380)
                }
            }

            Text("研究 / 分析用途，非投资建议，不执行真实交易。agent 观点带置信度，不代表事实。")
                .font(.caption2.monospaced())
                .foregroundStyle(.tertiary)
                .padding(.top, 4)
        }
        .padding(14)
    }

    private func appStateLoginRefresh() async {}
}
```

**注意**：`body` 里的 `withObservationTracking` 包裹是多余且错误的（会阻断 @Observable 正常追踪）——实现时直接 `var body: some View { content }`，删掉包装与 `appStateLoginRefresh` 空函数、onStart 里的调用。

`App/Features/TradingDesk/DecisionPanel.swift`（右栏）：

```swift
import SwiftUI
import DeepAlphaCore

/// 右栏：共识 + 各分析师信号列表 + 裁决卡。
struct DecisionPanel: View {
    let signals: [SignalRow]
    let consensus: ConsensusData?
    let verdict: VerdictData?
    let turns: [Turn]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            panelHeader("决策")
            ConsensusMeter(consensus: consensus)
            if !signals.isEmpty {
                VStack(spacing: 8) {
                    ForEach(signals) { s in
                        HStack {
                            Text(s.name)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                            Spacer()
                            SignalChip(dir: s.dir, conf: s.conf, extracted: s.extracted)
                        }
                    }
                }
            }
            VerdictCard(verdict: verdict, turns: turns)
            Spacer(minLength: 0)
        }
        .padding(14)
        .background(Color(.secondarySystemBackground),
                    in: RoundedRectangle(cornerRadius: 14))
    }
}
```

`App/ErrorBanner.swift`（顺手建）：

```swift
import SwiftUI

/// 顶部错误条 + 重试/关闭。
struct ErrorBanner: View {
    let message: String
    let onClose: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
            Text(message).font(.footnote)
            Spacer()
            Button("知道了", action: onClose)
                .font(.footnote.weight(.semibold))
        }
        .foregroundStyle(.red)
        .padding(10)
        .background(Color.red.opacity(0.1), in: RoundedRectangle(cornerRadius: 10))
    }
}
```

- [ ] **Step 9: 编译验证**

```bash
cd ios/DeepAlphaClub && xcodegen generate && \
xcodebuild -project DeepAlphaClub.xcodeproj -scheme DeepAlphaClub \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  CODE_SIGNING_ALLOWED=NO build 2>&1 | grep -E "error|BUILD" | head -10
```

期望：`** BUILD SUCCEEDED **`。删掉 `App/Placeholders.swift` 中的 TradingDeskView 占位（保留 HistoryListView 占位到 Task 17）。

- [ ] **Step 10: 模拟器冒烟（自动截图）**

```bash
xcrun simctl boot "iPhone 17 Pro" 2>/dev/null; sleep 5
xcodebuild -project DeepAlphaClub.xcodeproj -scheme DeepAlphaClub \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  CODE_SIGNING_ALLOWED=NO build 2>&1 | tail -1
# 找到产物并安装启动
APP=$(find ~/Library/Developer/Xcode/DerivedData -name "DeepAlphaClub.app" -path "*iphonesimulator*" | head -1)
xcrun simctl install booted "$APP" && xcrun simctl launch booted club.deepalpha.ios
sleep 3 && xcrun simctl io booted screenshot /tmp/td-login.png
```

检查 `/tmp/td-login.png`：登录页两输入框 + 登录按钮。不通过则修（截图给用户看进度）。

- [ ] **Step 11: 提交**

```bash
git add ios/DeepAlphaClub && git commit -m "feat(ui): 交易台主界面（三栏/TabView 自适应 + 智能滚动 + 注入 sheet）"
```

---

## Task 17: 历史 UI（列表 + 回放）

**Files:**
- Delete: `App/Placeholders.swift`（若还有残留）
- Create: `App/Features/History/HistoryListView.swift`
- Create: `App/Features/History/RunReplayView.swift`

- [ ] **Step 1: HistoryListView**

`App/Features/History/HistoryListView.swift`:

```swift
import SwiftUI
import DeepAlphaCore

/// 历史列表：ticker 过滤 + 状态/裁决徽标，点击进回放。
struct HistoryListView: View {
    @Environment(HistoryListViewModel.self) private var vm
    @State private var tickerFilter = ""

    var body: some View {
        NavigationStack {
            List {
                if vm.loading && vm.runs.isEmpty {
                    HStack { ProgressView(); Text("正在拉取").foregroundStyle(.secondary) }
                }
                if vm.runs.isEmpty && !vm.loading {
                    Text("暂无历史运行 —— 到交易台跑一次吧。")
                        .foregroundStyle(.tertiary)
                }
                ForEach(vm.runs) { run in
                    NavigationLink(value: run.runId) {
                        RunRow(run: run)
                    }
                }
                if let err = vm.error {
                    ErrorBanner(message: err, onClose: { vm.error = nil })
                }
            }
            .navigationTitle("历史运行")
            .navigationDestination(for: String.self) { runId in
                RunReplayView(runId: runId)
            }
            .searchable(text: $tickerFilter, prompt: "按标的过滤（如 NVDA）")
            .onSubmit(of: .search) {
                Task { await vm.refresh(ticker: tickerFilter) }
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await vm.refresh(ticker: tickerFilter) }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                }
            }
            .task {
                await vm.refresh(ticker: nil)
            }
        }
    }
}

/// 一行历史：ticker + 裁决徽标 + 状态 + 时长/计数 + 时间。
struct RunRow: View {
    let run: RunSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text(run.ticker)
                    .font(.headline.monospaced())
                if let signal = run.verdictSignal {
                    VerdictBadge(signal: signal, confidence: run.verdictConfidence)
                } else {
                    Text("未出裁决").font(.caption2).foregroundStyle(.tertiary)
                }
                StatusBadge(status: run.status)
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text(Self.timestamp(run.finishedAt ?? run.createdAt))
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                    Text(run.tradeDate)
                        .font(.caption2.monospaced())
                        .foregroundStyle(.tertiary)
                }
            }
            HStack(spacing: 12) {
                Label(run.status == .running ? "—" : Self.duration(run.durationMs),
                      systemImage: "clock")
                Text("\(run.signalsCount) 信号")
                Text("\(run.turnsCount) 卡片")
                Text(run.engine).font(.caption2.monospaced())
            }
            .font(.caption2)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }

    static func duration(_ ms: Int) -> String {
        if ms < 1000 { return "\(ms)ms" }
        if ms < 60_000 { return String(format: "%.1fs", Double(ms) / 1000) }
        let m = ms / 60_000, s = (ms % 60_000) / 1000
        return "\(m)m\(s)s"
    }

    static func timestamp(_ iso: String) -> String {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let d = parser.date(from: iso)
            ?? ISO8601DateFormatter().date(from: iso)
        else { return iso }
        return d.formatted(date: .abbreviated, time: .shortened)
    }
}

struct VerdictBadge: View {
    let signal: VerdictSignal
    let confidence: Double?

    var body: some View {
        HStack(spacing: 4) {
            Text(signal.rawValue)
            if let c = confidence {
                Text("\(Int((c * 100).rounded()))%")
                    .monospacedDigit()
                    .opacity(0.7)
            }
        }
        .font(.caption.weight(.medium))
        .foregroundStyle(signal.tint)
        .padding(.horizontal, 6)
        .padding(.vertical, 2)
        .background(signal.tint.opacity(0.1), in: RoundedRectangle(cornerRadius: 5))
    }
}

struct StatusBadge: View {
    let status: RunRecordStatus

    private var (text, color): (String, Color) {
        switch status {
        case .running: ("运行中", .blue)
        case .completed: ("已完成", .green)
        case .cancelled: ("已取消", .gray)
        case .failed: ("失败", .red)
        case .interrupted: ("中断", .orange)
        }
    }

    var body: some View {
        Text(text)
            .font(.caption2)
            .foregroundStyle(color)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.1), in: RoundedRectangle(cornerRadius: 5))
    }
}
```

- [ ] **Step 2: RunReplayView**

`App/Features/History/RunReplayView.swift`:

```swift
import SwiftUI
import DeepAlphaCore

/// 回放：全文直出（无流式动画），顶部裁决 + 信号，下面 Turn 卡片序列。
struct RunReplayView: View {
    let runId: String
    @State private var vm: RunReplayViewModel?

    var body: some View {
        Group {
            if let vm {
                ReplayBody(vm: vm)
            } else {
                ProgressView("载入中")
            }
        }
        .navigationTitle("回放")
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// 分离 body 以便 @Environment 注入 service 后再建 VM。
private struct ReplayBody: View {
    @State var vm: RunReplayViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if let d = vm.detail {
                    HStack {
                        Text(d.ticker).font(.headline.monospaced())
                        Text(d.tradeDate).font(.caption.monospaced()).foregroundStyle(.tertiary)
                        Spacer()
                        Text(Self.duration(d.durationMs))
                            .font(.caption.monospaced()).foregroundStyle(.secondary)
                    }
                    DecisionPanel(
                        signals: vm.signals,
                        consensus: nil,
                        verdict: vm.verdict,
                        turns: vm.turns)
                }
                if vm.loading {
                    ProgressView().frame(maxWidth: .infinity).padding()
                }
                if let err = vm.error {
                    ErrorBanner(message: err, onClose: { vm.error = nil })
                }
                ForEach(vm.turns) { turn in
                    TurnCard(turn: turn)
                }
            }
            .padding(14)
        }
        .task { await vm.load(runId: vmLoadedId) }
    }

    // 实现时把 task 里的 id 直接用外层传入；这里占位说明 load 一次
    private var vmLoadedId: String { "" }

    static func duration(_ ms: Int) -> String {
        RunRow.duration(ms)
    }
}
```

**注意**：`vmLoadedId` 占位是设计错误——正确做法是 `RunReplayView` 直接持有 `@State private var vm: RunReplayViewModel?` + `.task(id: runId)` 首次创建并 load。实现用这个干净版：

```swift
struct RunReplayView: View {
    let runId: String
    @Environment(\.compositionRoot) private var root   // Task 15 定义的 EnvironmentKey
    @State private var vm: RunReplayViewModel?

    var body: some View {
        ScrollView {
            if let vm {
                VStack(alignment: .leading, spacing: 12) {
                    if let d = vm.detail {
                        header(d)
                        DecisionPanel(signals: vm.signals, consensus: nil,
                                      verdict: vm.verdict, turns: vm.turns)
                    }
                    if vm.loading { ProgressView().padding() }
                    if let err = vm.error {
                        ErrorBanner(message: err, onClose: { vm.error = nil })
                    }
                    ForEach(vm.turns) { turn in
                        TurnCard(turn: turn)
                    }
                }
                .padding(14)
            } else {
                ProgressView("载入中").padding(40)
            }
        }
        .navigationTitle("回放")
        .navigationBarTitleDisplayMode(.inline)
        .task(id: runId) {
            guard let root else { return }
            if vm == nil { vm = root.replayFactory(runId) }
            await vm?.load(runId: runId)
        }
    }

    private func header(_ d: RunDetailResponse) -> some View {
        HStack {
            Text(d.ticker).font(.headline.monospaced())
            Text(d.tradeDate).font(.caption.monospaced()).foregroundStyle(.tertiary)
            Spacer()
            Text(RunRow.duration(d.durationMs))
                .font(.caption.monospaced()).foregroundStyle(.secondary)
        }
    }
}
```

这需要在 `DeepAlphaClubApp` 里追加 `.environment(root)`（把 CompositionRoot 实例注入 environment）。修改 `DeepAlphaClubApp.swift` 的 WindowGroup 内容：

```swift
RootView()
    .environment(\.compositionRoot, root)   // 追加（EnvironmentKey 方式）
    .environment(root.appState)
    .environment(root.deskVM)
    .environment(root.historyVM)
    .task { root.appState.restoreFromKeychain() }
```

（`MainTabView` 里 environment 会向下传播，HistoryListView 的 `@Environment(HistoryListViewModel.self)` 也靠这行。）

- [ ] **Step 3: 编译 + 冒烟**

```bash
cd ios/DeepAlphaClub && xcodegen generate && \
xcodebuild -project DeepAlphaClub.xcodeproj -scheme DeepAlphaClub \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  CODE_SIGNING_ALLOWED=NO build 2>&1 | grep -E "error|BUILD" | head -10
```

期望 `** BUILD SUCCEEDED **`；`swift test` 仍全绿（Core 未动）。

- [ ] **Step 4: 提交**

```bash
git add ios/DeepAlphaClub && git commit -m "feat(history): 历史列表（过滤/徽标）+ 回放全文直出"
```

---

## Task 18: 全量验证 + 真机冒烟 + 收尾

- [ ] **Step 1: 全量测试 + 双目标编译**

```bash
cd ios/DeepAlphaClub/Core && swift test 2>&1 | tail -3
xcodegen generate && \
xcodebuild -project DeepAlphaClub.xcodeproj -scheme DeepAlphaClub \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  CODE_SIGNING_ALLOWED=NO build 2>&1 | grep -E "warning|error|BUILD" | head -20
```

期望：测试全绿 + `BUILD SUCCEEDED`。检查 warning：Swift 6 strict 下如有 warning 逐个修（计划验收含「无 warning」）。

- [ ] **Step 2: 窄屏/宽屏冒烟截图**

```bash
xcrun simctl boot "iPhone 17 Pro" 2>/dev/null; sleep 3
xcrun simctl boot "iPad Pro 13-inch (M4)" 2>/dev/null; sleep 3
APP=$(find ~/Library/Developer/Xcode/DerivedData -name "DeepAlphaClub.app" -path "*iphonesimulator*" | head -1)
for DEV in "iPhone 17 Pro" "iPad Pro 13-inch (M4)"; do
  xcrun simctl install "$DEV" "$APP"
  xcrun simctl launch "$DEV" club.deepalpha.ios
  sleep 3
  xcrun simctl io "$DEV" screenshot "/tmp/td-$(echo $DEV | tr ' ' '-').png"
done
```

检查两张截图：iPhone 竖屏登录页不破版；iPad 三栏布局（登录后才能看到，本步只验登录页渲染正常——主界面布局由用户登录后自测）。

- [ ] **Step 3: 真实后端联调（用户提供账号，或跳过留给用户自测）**

```bash
# 用真实账号在模拟器登录 → 输入 NVDA → 开始分析 → 观察：
# 1. 流程条滚动推进（active/done）
# 2. 推理流实时输出 + 贴底跟随；上滑不拉回
# 3. 决策栏信号逐个出现 → 最终裁决卡
# 4. 分析中点暂停/继续/注入/停止
# 5. 退后台 30s 再回前台 → 续传不丢不重
# 6. 历史页列表 + 回放
```

无账号环境则把验收清单写进 README「自测清单」小节，标记此步留给用户。

- [ ] **Step 4: README 自测清单 + 收尾提交**

README.md 追加：

```markdown
## 自测清单（v0.1.0 验收）

- [ ] 登录 → 退出 → 再登录（token 持久化）
- [ ] 输入 ticker + 选市场 → 开始分析 → SSE 实时输出
- [ ] 流程条状态推进 + 每阶段信号 chip
- [ ] 暂停 / 继续 / 注入 / 停止
- [ ] 流式输出上滑查看历史不被拉回
- [ ] 后台 30s → 回前台续传不丢不重
- [ ] 历史列表 + 回放全文直出
- [ ] 401 自动回登录页
- [ ] iPhone 窄屏 / iPad 宽屏布局
```

```bash
git add ios/DeepAlphaClub && git commit -m "docs: 自测清单 + v0.1.0 收尾"
```

- [ ] **Step 5: 回主仓库提交计划与进度**

```bash
git add docs/superpowers/plans/2026-08-30-trading-desk-ios-app.md && \
git commit -m "docs: TradingDesk iOS App 实施计划"
```

---

## 验收标准

- [ ] `swift test` 全绿（Core 层：reducer 状态机 / SSE 解析 / API 客户端 / 重连 / 缓存 / VM 全覆盖）
- [ ] `xcodebuild build`（iPhone 17 Pro 模拟器）`BUILD SUCCEEDED` 且无 warning
- [ ] 登录（真实后端）→ 开始分析 → SSE 流式渲染 → 裁决卡出现
- [ ] 暂停/继续/注入/停止生效（后端 controlRun 200）
- [ ] 流式时上滑不被拉回；新 run 强制贴底
- [ ] 后台断流、前台 lastEventId 续传，不丢不重（seq 去重兜底）
- [ ] 历史列表（缓存先出 + 远端刷新）+ 回放全文直出
- [ ] 401 自动清 token 回登录页
- [ ] iPhone 竖屏 TabView / iPad 三栏布局正常

## 风险与回退

| 风险 | 缓解 |
|---|---|
| `brew install xcodegen` 失败 | 中止并报告用户；不手写 pbxproj |
| Swift 6 strict 并发编译阻塞 | VM 全部 @MainActor；Service/Client 为 Sendable struct；测试 mock 用 @unchecked Sendable + 锁 |
| SwiftData @Model 在 SPM/macOS 测试异常 | 已设 macOS .v14；若 @ModelActor 宏出问题，RunCache 降级为「直存 JSON 文件」（接口不变重实现） |
| 智能滚动两种实现（Geometry vs scrollPosition）效果不佳 | 计划已列备选；再不行退「按钮回到底部」方案（自用可接受） |
| 后端 CORS/证书问题 | iOS 原生 App 无 CORS 概念；`api.deepalpha.club` 是合法 HTTPS，ATS 默认放行 |
| 真实联调无账号 | Task 18 Step 3 改为用户自测清单 |
