# DeepAlphaBaZi iOS App 设计

**日期**：2026-09-05
**范围**：MVP — 仅「八字」+「我的」两个 Tab，消费已上线的后端八字排盘引擎（`/api/v1/bazi/chart`、`/api/v1/bazi/interpretation`）
**不包含**：紫微斗数 Tab（后端尚未实现）、推送通知（APNs）、家人命盘管理、AI 自由问答对话

## 1. 与产品设计 spec 的落差修正

这是子项目设计，衍生自 [2026-09-05-deepalpha-bazi-app-design.md](2026-09-05-deepalpha-bazi-app-design.md)。brainstorming 过程中发现两处需要修正的落差，均已确认：

1. **"问 AI 悬浮聊天面板"简化为内嵌展示**：原产品设计设想的是自由提问的聊天界面（输入框 + 猜你想问 + 多轮对话），但已实现的后端 `POST /api/v1/bazi/interpretation` 只支持两种固定文案（`section=daily` 今日运势 / `section=deep` 深度解读），不支持自由文本提问。本轮 iOS 去掉独立的聊天式悬浮面板，"今日运势"变成首页一张自动加载的卡片，"深度解读"变成分段控制里的一段（与"大运流年"一样需要订阅）。自由问答对话能力留给未来的后端子项目。
2. **免费额度模型简化**：原设想是"AI 对话每日限次"，现在没有对话了，改为：`daily` 每天自动拉取一次并本地按日期缓存（避免同一天内重复调用付费 LLM 接口）；`deep` 与大运流年展开完全由订阅状态门控，不涉及次数限制。

## 2. 工程搭建

- **`xcodegen` + 本地 SPM 包 `Core`**，比照 `ios/DeepAlphaClub` 的结构（而非 `ios/DeepAlphaChan` 的纯手动 `.xcodeproj`），业务逻辑（网络/持久化/StoreKit/ViewModel）放进 `Core` 包以便写 XCTest，App target 只放 SwiftUI 视图。
- iOS 17.0 部署目标，Swift 6.0（严格并发模式），bundle id `club.deepalpha.bazi`。
- 后端固定为生产地址 `https://api.deepalpha.club`（不做多环境配置，MVP 阶段够用）。

## 3. 目录结构

```
ios/DeepAlphaBaZi/
├── DeepAlphaBaZi.xcodeproj          # xcodegen 生成，不手动改
├── project.yml
├── DeepAlphaBaZi/                    # App target
│   ├── App/
│   │   ├── DeepAlphaBaZiApp.swift    # @main，注入 Core 的依赖
│   │   ├── RootView.swift            # TabView(八字 / 我的)
│   │   └── Theme.swift
│   ├── Features/
│   │   ├── Bazi/
│   │   │   ├── BirthInfoFormView.swift   # 新用户：填生辰
│   │   │   ├── ChartHomeView.swift       # 已有本地记录：四柱+五行+今日运势+分段控制
│   │   │   ├── DaYunSectionView.swift    # 付费墙：大运流年
│   │   │   └── DeepInterpretationView.swift  # 付费墙：深度解读长文
│   │   └── Profile/
│   │       ├── ProfileView.swift         # 我的 Tab 主页
│   │       ├── LoginView.swift           # 可选登录（复用现有 auth）
│   │       └── SubscriptionView.swift    # 订阅付费墙 + 已订阅状态
│   ├── Resources/
│   │   └── Assets.xcassets
│   └── Info.plist
├── Core/                              # 本地 SPM 包
│   ├── Package.swift
│   ├── Sources/DeepAlphaBaZiCore/
│   │   ├── Networking/
│   │   │   ├── APIClient.swift        # actor，纯 URLSession
│   │   │   ├── BaziService.swift      # POST /chart、POST /interpretation
│   │   │   ├── AuthService.swift      # 复用现有 /api/v1/auth
│   │   │   └── KeychainStore.swift    # 可选登录的 token 存储
│   │   ├── Models/
│   │   │   ├── BaziModels.swift       # 镜像 app/schemas/bazi.py
│   │   │   └── AuthModels.swift
│   │   ├── Persistence/               # SwiftData
│   │   │   ├── BirthProfile.swift     # @Model：用户自己的生辰
│   │   │   └── DailyFortuneCache.swift # @Model：今日运势缓存(按日期去重)
│   │   ├── Store/
│   │   │   └── StoreManager.swift     # StoreKit 2 订阅
│   │   └── ViewModels/
│   │       ├── BaziViewModel.swift
│   │       ├── AuthViewModel.swift
│   │       └── SubscriptionViewModel.swift
│   └── Tests/DeepAlphaBaZiCoreTests/
│       ├── APIClientTests.swift
│       ├── BaziServiceTests.swift
│       ├── BaziViewModelTests.swift
│       └── AuthServiceTests.swift
```

## 4. 数据流

### 4.1 首次使用

```
App 启动 → RootView 查 SwiftData 里有没有 BirthProfile
  ├─ 没有 → BirthInfoFormView（日期/时辰选择器含"不确定"开关、
  │         城市选择器——限定在后端内置的 38 城市列表里选，不开放自由输入，
  │         避免真太阳时校正因城市名不匹配而静默不生效、性别选择）
  │         └─ 提交 → BaziService.getChart(request)
  │              └─ POST /api/v1/bazi/chart
  │                  └─ 成功：写入 BirthProfile + 缓存的 BaziChartResponse
  │                      → 进入 ChartHomeView
  └─ 有 → 直接读本地缓存的 BaziChartResponse → ChartHomeView
```

### 4.2 ChartHomeView

```
ChartHomeView 加载
  ├─ 四柱卡片 + 五行分布：直接渲染本地缓存的 BaziChartResponse（免费，无需网络）
  ├─ "今日运势"卡片：
  │    查 DailyFortuneCache 有没有"今天"的记录
  │    ├─ 有 → 直接展示缓存文本
  │    └─ 没有 → BaziService.getInterpretation(section: .daily)
  │              └─ POST /api/v1/bazi/interpretation { section: "daily", ... }
  │                  └─ 成功 → 写入 DailyFortuneCache(date: today) → 展示
  └─ 分段控制：概览(已在上面) / 大运流年🔒 / 深度解读🔒
       ├─ 未订阅：模糊预览 + "订阅解锁"按钮 → 跳转 SubscriptionView
       └─ 已订阅：
            ├─ 大运流年：直接渲染本地缓存的 BaziChartResponse.daYun（免费计算，一直都有，只是 UI 门控）
            └─ 深度解读：BaziService.getInterpretation(section: .deep) → 展示长文（不做本地缓存，允许重新生成）
```

### 4.3 订阅（StoreKit 2）

```
SubscriptionView
  ├─ StoreManager.products：Product.products(for: [productID])
  ├─ 购买：product.purchase() → Transaction.updates 监听 → 写入本地"已订阅"状态
  ├─ 恢复购买：AppStore.sync() → 重新校验 Transaction.currentEntitlements
  └─ 全部是设备本地判断（服务端不做订阅校验，参照后端设计文档的既定决策）
```

### 4.4 登录（可选，不阻塞主流程）

```
"我的" Tab → 未登录时显示"登录/注册"入口（非强制）
  └─ LoginView → AuthService.login(...) → POST /api/v1/auth/... （复用现有账号体系）
       └─ 成功 → token 存 KeychainStore → 我的 Tab 显示已登录状态
（八字 Tab 的排盘/今日运势/订阅全程不检查登录状态）
```

## 5. 错误处理

| 场景 | 处理 |
|---|---|
| `/chart` 网络失败 | 表单页顶部 banner + 重试按钮，不清空用户已填的表单内容 |
| `/interpretation` 网络失败或超时 | 卡片内展示"生成失败，点击重试"，不阻塞四柱/五行等本地数据的展示 |
| 城市选择器里找不到用户所在城市 | 选择器本身只允许选内置的 38 个城市，不存在"找不到"的情况；若后端后续放开自由输入，则由 `true_solar_time_applied=false` 驱动 UI 显示"未做精确时差校正"提示 |
| StoreKit 购买失败/取消 | 展示系统级错误信息，不做额外包装 |
| 登录失败（401/密码错误等） | LoginView 内联错误提示，不影响八字主流程 |

## 6. 测试策略

**Core 包 XCTest**（mock `URLProtocol`）：
- `APIClientTests`：请求编码、响应解码、错误处理
- `BaziServiceTests`：`/chart`、`/interpretation` 两个端点的请求体/响应体映射
- `BaziViewModelTests`：新用户态→已排盘态的状态机、今日运势缓存命中/未命中逻辑
- `AuthServiceTests`：登录成功/失败、token 存取

**不做**：XCUITest（成本高，价值低，参照 `DeepAlphaClub` 的既有决策）

## 7. 依赖

- 无第三方网络库（纯 `URLSession`，同 `DeepAlphaChan` 惯例）
- `SwiftData`（系统框架）
- `StoreKit 2`（系统框架）
- 无 SPM 第三方依赖

## 8. 验收标准

- [ ] 首次打开 App，无本地记录时展示生辰填写表单，城市限定从内置 38 城市选择
- [ ] 提交生辰后成功调用 `/chart`，四柱/五行数据正确渲染，且被 SwiftData 持久化（杀进程重开不用重填）
- [ ] "今日运势"卡片自动加载，同一天内多次打开 App 不重复调用 `/interpretation`（本地缓存生效）
- [ ] 未订阅时，"大运流年"和"深度解读"两个分段显示模糊预览 + 订阅 CTA
- [ ] 完成 StoreKit 沙盒购买后，两个付费分段解锁，"深度解读"能成功调用 `/interpretation?section=deep` 并渲染长文
- [ ] "我的" Tab 可选登录/注册（复用现有 `/api/v1/auth`），不登录不影响八字 Tab 任何功能
- [ ] Core 包所有 XCTest 通过
- [ ] Xcode 编译无 warning（Swift 6 严格并发模式）
