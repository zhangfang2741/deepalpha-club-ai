# TradingDesk iOS App 设计

**日期**：2026-08-30
**范围**：MVP — 仅 TradingDesk 能力（启动分析 / 流式 / 控制 / 历史回放）
**后端**：复用现有 FastAPI（`https://api.deepalpha.club`），后端**零改动**

## 1. 高层架构

**产品边界**：独立 SwiftUI 工程，仅承载 TradingDesk 能力；不复用 deepalpha.club 现有任何前端代码。

**部署形态**：
- iOS 17+（SwiftData、Observation framework、Swift 6 Concurrency）
- 自用 TestFlight 渠道，bundle id 独立于现有 web 域名
- 不发 App Store（无需审核、隐私政策、APNs 证书）

**进程内部分层**（MVVM + Service）：

```
Views (SwiftUI) ── ViewModels (@Observable) ── Services (Protocol) ── Models (Codable)
```

**持久化**：SwiftData 缓存历史 runs（runId + 摘要 JSON），进入 App 立即可用。

**后台策略**：`scenePhase` 监听 → 后台时取消 SSE；前台恢复时用 `lastEventId` 重连（复用 web 的无限重连机制）。

## 2. 模块 / 组件

### Models（Codable，镜像后端 schemas）

| Model | 镜像 |
|---|---|
| `TradingDeskEvent<T>` | 通用 SSE 事件壳（`{event, data}` 解析后分发） |
| `RunSummary` / `RunDetail` | `TradingDeskRun` SQLModel 字段 |
| `Verdict` | `VerdictData` |
| `Signal` | `SignalData` |
| `Consensus` | `ConsensusData` |
| `EngineCapabilities` | `EngineCapabilities` |

### Services（protocol-first，方便 mock 测试）

- `APIClient` — 通用 HTTP 客户端（URLSession 实现），处理 auth header、超时、JSON 解析
- `SSEClient` — 流式订阅（`streamRun(id, lastEventId) → AsyncThrowingStream<TradingDeskEvent, Error>`，断线指数退避重连）
- `TradingDeskAPI` — 封装业务端点（`createRun` / `controlRun` / `listRuns` / `getRun`），依赖 `APIClient`
- `AuthService` — `login(username, password)` 调 `POST /api/v1/auth/sessions`，session token 存 Keychain
- `KeychainStore` — session token 安全存取
- `RunCache`（SwiftData）— 历史 runs 持久化层

### ViewModels（`@Observable`）

- `AppState` — session token + `engineCapabilities`
- `TradingDeskViewModel` — 当前 run + 流事件序列 + 滚动状态 + 控制动作
- `HistoryListViewModel` — 历史列表 + 分页
- `RunReplayViewModel` — 单次 run 回放（从 `getRun` 拉详细流）

### Views（SwiftUI，对照 Web 组件重写）

| iOS View | 对照 Web 组件 | 备注 |
|---|---|---|
| `TradingDeskView` | `page.tsx` | 主容器 + 顶栏 + 三栏布局（iOS 自适应：紧凑宽度 TabView，宽屏 HStack 三栏） |
| `MarketSegmentedControl` | Topbar 4 段 segment | iOS `Picker(segmented)` |
| `TickerInputBar` | Topbar 输入框 + Start | 复用 `resolveTicker` 逻辑（移植到 Swift） |
| `ControlToolbar` | 暂停/继续/取消/注入 | iOS `ToolbarItem` |
| `PipelinePanel` | Web PipelinePanel | 纵向列表（同 Web） |
| `StreamPanel` | Web StreamPanel | `List + .scrollPosition` 实现智能滚动（仅贴底跟随） |
| `TurnCard` | Web TurnCard | 含流式 markdown 渲染（`AttributedString` 解析 markdown） |
| `DecisionPanel` | Web DecisionPanel | 折叠成 iOS 卡片列表 |
| `ConsensusMeter` | Web ConsensusMeter | 进度条 + 数字 |
| `SignalChip` | Web SignalChip | 圆角 pill，按 polarity 着色 |
| `VerdictCard` | Web VerdictCard | 信号 + 仓位 + 止损 + 目标价网格 |
| `HistoryListView` / `RunReplayView` | Web `/trading-desk/history` | 列表 + 详情 |

### App 入口

- `DeepAlphaClubApp`（`@main`）— 启动时检查 Keychain 有无 session token → 有则进主页，否则进入登录页
- 路由用 `NavigationStack`

## 3. 数据流

### 3.1 启动 + 登录

```
App 启动
  └─→ AppState.init: 读 Keychain
       ├─ 有 token: 进入主页，listRuns (本地缓存先渲染，后台 fetch 远端)
       └─ 无 token:  NavigationStack push LoginView
            └─→ AuthService.login → POST /api/v1/auth/sessions
                └─→ session.token.access_token → KeychainStore.save
                    └─→ pop LoginView, push TradingDeskView
```

### 3.2 启动一次 Run（核心流）

```
TradingDeskViewModel.startRun(ticker, market)
  ├─→ resolveTicker(ticker, market)   // 复用 web 端规则（HK strip 前导零）
  ├─→ TradingDeskAPI.createRun(symbol)
  │     └─→ POST /api/v1/trading_desk/runs { ticker }
  │         └─→ { run_id, capabilities, stages[] } → 写入 @Observable state
  ├─→ SSEClient.subscribe(runId, lastEventId: nil)
  │     └─→ GET /api/v1/chatbot/langgraph/stream (Accept: text/event-stream)
  │         └─→ AsyncThrowingStream<TradingDeskEvent>
  │             └─→ 每个 event → state.apply(event)
  │                 ├─ run.started     → status = running
  │                 ├─ stage.started   → stageStatus[stageId] = active
  │                 ├─ token           → turns[currentTurn].text += delta
  │                 ├─ agent.signal    → stageSignal[stageId] = signal
  │                 ├─ consensus.update → state.consensus = newConsensus
  │                 ├─ verdict         → state.verdict = verdict
  │                 ├─ run.finished    → status = completed, 关闭 SSE
  │                 └─ run.failed      → status = failed
  └─→ runTask 持有 Task<SSEHandle>，可 cancel
```

### 3.3 控制动作

- `controlRun("pause" | "resume" | "cancel" | "inject", text?)` → `POST /api/v1/trading_desk/runs/{id}/control`
- 取消时本地同时 `SSEClient.unsubscribe()`
- 注入：body 带 text，后端 engine 在节点边界注入到 state

### 3.4 后台 / 前台切换

```
scenePhase 变化
  ├─ .background → SSEClient.unsubscribe()
  │               state.lastEventId = 最后收到 event 的 id
  │               state.lastSnapshot = 本地缓存的 turns / signals / verdict
  └─ .active     → SSEClient.subscribe(runId, lastEventId: state.lastEventId)
                   后端从 lastEventId 之后的事件续传
```

### 3.5 历史缓存（SwiftData）

- `CachedRun { runId, ticker, market, status, startedAt, finishedAt, summaryJson }`
- 写入时机：`run.finished` 事件到达
- 读取时机：`HistoryListViewModel.init` 立即从 SwiftData 拉 → 同步渲染 → 后台 fetch `/api/v1/trading_desk/runs` → diff 更新
- 过期策略：保留最近 50 条，超出按 `startedAt` 淘汰

## 4. 错误处理 + 测试

### 4.1 错误处理

| 错误来源 | 处理 |
|---|---|
| SSE 断开 / 网络抖动 | `SSEClient` 内指数退避（800ms ×2，cap 30s）；status 仍 running/paused 则重连；多次失败 → 顶部红色 banner |
| API 4xx/5xx | ViewModel 抛 typed error（`.authExpired` / `.notFound` / `.serverError`） |
| 401 | 清 Keychain → push LoginView |
| 其他 4xx/5xx | 顶部 banner + 重试按钮 |
| URLSession 无网络 / ATS | 顶部 banner "网络不可用"，后台重连 |
| Keychain access denied | 退到登录页 |
| Token 过期 | 401 自动处理 |

### 4.2 测试策略

**单元测试**（必须）：
- Service 协议 + mock URLProtocol（APIClient / SSEClient）
- ViewModel 状态机（`TradingDeskViewModel` / `HistoryListViewModel` / `RunReplayViewModel`）
- `resolveTicker` 4 市场全覆盖（US / HK / SH / SZ，带不带后缀都覆盖）
- `KeychainStore` mock

**Snapshot 测试**（推荐）：
- `PipelinePanel` / `DecisionPanel` / `VerdictCard` / `SignalChip` / `ConsensusMeter` / `TurnCard` 关键状态
- 用 `swift-snapshot-testing` SPM 依赖

**集成测试**（推荐）：
- 本地 Python mock server 模拟 SSE 流（用 fastapi 起一个 30 行的 mock，输出合成 event 流）
- 验证重连 / 断点续传 / 错误重试

**跳过**：
- XCUITest（成本高，价值低）
- 后端变更相关测试（后端零改动）

## 5. 工程化 / 项目结构

### 5.1 仓库位置

**独立 git 仓库**：`deepalpha-club-ios/`（不在 `deepalpha-club-ai` 子目录）。理由：
- iOS 工程是 Xcode project，有自己的 `.xcodeproj` / `.xcworkspace` 配置，与 Python 后端 monorepo 工具链不兼容
- iOS release tag 与后端 tag 解耦
- 避免污染 `deepalpha-club-ai` 仓库

### 5.2 项目结构

```
deepalpha-club-ios/
├── DeepAlphaClub.xcodeproj
├── DeepAlphaClub/
│   ├── App/
│   │   └── DeepAlphaClubApp.swift
│   ├── Core/
│   │   ├── APIClient.swift
│   │   ├── SSEClient.swift
│   │   ├── KeychainStore.swift
│   │   └── BrandColors.swift
│   ├── Auth/
│   │   ├── AuthService.swift
│   │   ├── LoginView.swift
│   │   └── AppState.swift
│   ├── Models/
│   │   ├── TradingDeskEvent.swift
│   │   ├── Run.swift
│   │   ├── Verdict.swift
│   │   ├── Signal.swift
│   │   └── Consensus.swift
│   ├── Persistence/
│   │   ├── RunCache.swift
│   │   └── CachedRun.swift
│   ├── Services/
│   │   └── TradingDeskAPI.swift
│   ├── Features/
│   │   ├── TradingDesk/
│   │   │   ├── TradingDeskView.swift
│   │   │   ├── TradingDeskViewModel.swift
│   │   │   ├── MarketSegmentedControl.swift
│   │   │   ├── TickerInputBar.swift
│   │   │   ├── ControlToolbar.swift
│   │   │   ├── PipelinePanel.swift
│   │   │   ├── StreamPanel.swift
│   │   │   ├── TurnCard.swift
│   │   │   ├── DecisionPanel.swift
│   │   │   ├── ConsensusMeter.swift
│   │   │   ├── SignalChip.swift
│   │   │   └── VerdictCard.swift
│   │   └── History/
│   │       ├── HistoryListView.swift
│   │       ├── HistoryListViewModel.swift
│   │       ├── RunReplayView.swift
│   │       └── RunReplayViewModel.swift
│   ├── Resources/
│   │   └── Assets.xcassets
│   └── Info.plist
├── DeepAlphaClubTests/
│   ├── APIClientTests.swift
│   ├── SSEClientTests.swift
│   ├── TradingDeskViewModelTests.swift
│   ├── HistoryListViewModelTests.swift
│   ├── ResolveTickerTests.swift
│   └── SnapshotTests/
│       ├── PipelinePanelSnapshotTests.swift
│       └── VerdictCardSnapshotTests.swift
├── DeepAlphaClubUITests/
│   └── (空，先不做 XCUITest)
├── Tools/
│   └── mock_server.py        # 测试用 SSE mock server
├── Package.swift             # SPM 依赖
└── README.md
```

### 5.3 依赖

**SPM**：
- `swift-snapshot-testing`（Point-Free，~1.0.0+，iOS 17 支持）— snapshot 测试

**无其他外部依赖**：
- `URLSession` 自带（SSE 流式订阅）
- `SwiftData` 自带（持久化）
- `Keychain Services` 系统框架
- `Observation` 自带
- markdown 渲染用 `AttributedString`（系统 API，iOS 15+ 支持基础 markdown）

### 5.4 配置

- **App Transport Security**：默认即可（`api.deepalpha.club` 是 HTTPS）
- **Bundle ID**：`club.deepalpha.ios`
- **Deployment Target**：iOS 17.0
- **Swift Version**：6.0（Concurrency 严格模式）
- **Code Signing**：自用 Personal Team（自用 TestFlight 不需要付费 Apple Developer）

### 5.5 后端契约（iOS App 依赖的接口）

| Endpoint | 用途 |
|---|---|
| `POST /api/v1/auth/sessions` | 登录拿 chat session token |
| `POST /api/v1/trading_desk/runs` | 创建 Run |
| `GET /api/v1/trading_desk/runs` | 历史列表 |
| `GET /api/v1/trading_desk/runs/{id}` | Run 详情（回放） |
| `POST /api/v1/trading_desk/runs/{id}/control` | 控制（pause/resume/cancel/inject） |
| `GET /api/v1/chatbot/langgraph/stream?run_id=X&last_event_id=Y` | SSE 流式订阅 |

后端**零改动**——所有这些接口已在 deepalpha-club-ai 主仓库实现并部署。

### 5.6 开发顺序

按 writing-plans skill 输出的实施计划，从项目脚手架开始，逐步实现：
1. Xcode 项目脚手架（`xcodegen` 或手工）
2. SPM 依赖 + 模型定义
3. Core Services（APIClient / SSEClient / KeychainStore）
4. Auth 流
5. TradingDeskViewModel + SSE 流状态机
6. 主 UI（TradingDeskView + 子组件）
7. SwiftData 历史缓存
8. History 页
9. Snapshot 测试 + 集成测试
10. 自用 TestFlight 打包

## 6. 验收标准

- [ ] 输入 ticker + 选 market → 点 Start → SSE 流式输出实时显示
- [ ] PipelinePanel 展示 stages 与状态（active / done / pending）+ SignalChip
- [ ] 暂停 / 继续 / 取消按钮生效（后端 controlRun 200）
- [ ] 注入意见功能可用（输入框 + 提交）
- [ ] 流式输出时用户上滑不被强制拉回底部（智能滚动）
- [ ] App 进后台 → SSE 断开；回前台 → 自动续传不丢不重
- [ ] 历史列表可看历史 runs + 详情回放
- [ ] 401 自动跳登录；session token 存 Keychain
- [ ] iPhone SE（窄屏）布局不破；iPad Pro（宽屏）三栏正常
- [ ] 关键组件 snapshot 测试通过
- [ ] ViewModel 状态机单元测试通过
- [ ] 模拟断网 → 自动重连；恢复 → 续传不丢
- [ ] 项目在 Xcode 16+ 编译通过、无 warning（Swift 6 Concurrency strict mode）