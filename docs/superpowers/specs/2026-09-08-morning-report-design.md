# 每日分析师晨报（美股 / A股 / 港股）设计文档

- 日期：2026-09-08
- 状态：已确认（用户逐节评审通过）
- 范围：缠论 App（DeepAlphaChan）新增「晨报」功能 + 后端 morning_report 模块

## 1. 背景与目标

用户在 ChatGPT 上运行着一个「每日美股分析师晨报」定时任务（参考 prompt 存于
`/Users/zhangfang/Desktop/每日美股分析师晨报`），以邮件形式发送。目标是将该能力
产品化进缠论 App：三市场（美股/A股/港股）、每日定时预生成、分析师视角的结构化
晨报，作为 App 的高频日活内容。

核心质量要求（从参考 prompt 继承，不可妥协）：

- 分析师视角：判断新闻是否改变**盈利预期、估值倍数、资金流向、风险溢价**，
  不做新闻罗列。
- 四层信息结构：每个模块必须含「事实依据 / 细节洞察 / 未来预测 / 验证或反证信号」。
- 细节颗粒度军规：落到公司名、产品名、具体指标数字、时间窗口、可跟踪口径；
  禁止「风险偏好改善」「估值重估」类抽象话（除非紧跟具体证据与可监控指标）。
- 预测必须带时间范围（24-72h / 1-2 周 / 财报季 / 6-12 个月）。

## 2. 已确认的产品决策

| 决策点 | 结论 |
| -------- | ------ |
| 入口形态 | 新增 Tab，且**排第一位**：晨报 / 分析 / 学习 / 我的；启动默认落在晨报页 |
| 市场组织 | 美股 / A股 / 港股 **三份独立晨报**（各自完整生成、独立存储） |
| 生成时机 | 后端 **Celery beat 定时预生成**：美股 06:30、A股 07:10、港股 07:10（北京时间） |
| 事实数据来源 | **Agentic 生成**：LLM 带工具（搜索 + 行情）自主查实时数据，再生成结构化 JSON |
| 内容格式 | 结构化 JSON，iOS **原生 SwiftUI 渲染**（非 Markdown/HTML/WebView） |
| 付费策略 | 登录即可免费，不接 Paywall |
| 模块结构 | 参考 prompt 11 模块精简为 **7 个 LLM 模块 + 1 个固定风险提示** |
| 推送通知 | **APNs 远程推送**：晨报生成成功后通知，点击通知跳转晨报页（详见第 7 节） |

## 3. 总体架构与数据流

```text
Celery Beat（每日定时，三市场三个任务）
   ▼
morning_report 生成任务（app/tasks/morning_report.py）
   1. 幂等检查（当天已 success 则跳过）
   2. 写入/更新 status=generating
   3. LLM Agent 工具循环：
      · duckduckgo_search（现有）── 隔夜新闻、事件、催化剂
      · fmp_data 系列工具（现有）── 美股指数/个股/财报硬数字
      · akshare 工具（新增 data_tools.py）── A股/港股指数、北向/南向资金、两市成交额
   4. with_structured_output(schema) 强制 JSON
   5. 校验失败自动重试（tenacity，最多 2 次）
   ▼
PostgreSQL（morning_report 表，market+trade_date 唯一）
   ▼
GET /api/v1/morning-report?market=us[&date=...]（登录可访问）
   ▼
iOS 晨报 Tab：市场切换 → 卡片化原生渲染 → 个股点击跳缠论分析页
```

关键架构决策：

- 生成任务在 Celery 任务里手写 tool-calling 循环，**不复用 chatbot 的完整
  LangGraph 图**——晨报是单轮批处理，图的对话/记忆能力用不上，手写循环更简单可控。
- 一套 Pydantic schema 三用：LLM 结构化输出约束、存库 content 校验、API 返回体。

## 4. Prompt 与内容结构设计

### 4.1 Prompt 模板

`app/services/morning_report/prompts/` 下三个市场模板：`us.md` / `cn.md` / `hk.md`。

基于参考 prompt 改造：

- **保留**：四层结构要求、细节颗粒度军规、预测时间范围要求、分析师视角总原则、
  「先用工具查证、再下判断」的工作流指令（替代 ChatGPT 的联网搜索）。
- **App 化精简**：11 模块 → 7 个 LLM 模块；输出为 JSON（schema 约束），不再有
  纯文本/HTML 双版本与邮件指令。
- **市场适配**（结构相同、文案侧重不同）：
  - 美股版：直接迁移参考 prompt（财报季/期权/美元流动性视角）。
  - A股版：政策面/北向资金/两市成交额/两融余额；涨跌语义按 A 股语境。
  - 港股版：南向资金/AH 溢价/流动性折价与修复；催化剂含美联储路径。

### 4.2 模块结构（7 LLM 模块 + 1 固定）

| # | 模块 | 来源（参考 prompt） |
| --- | ------ | -------------------- |
| 1 | 今日核心判断（总判断 + 3 个关键指标卡） | 原 1 |
| 2 | 定价与预期差 | 原 2+3 合并 |
| 3 | 盈利修正与估值影响 | 原 4 |
| 4 | 行业 / 产业链传导（具体环节 + 代表公司） | 原 5 |
| 5 | 重点个股 Bull/Base/Bear（2-3 只） | 原 6+7 合并（财报电话会克制并入） |
| 6 | 资金拥挤度与风险 | 原 8 |
| 7 | 未来催化剂日历（带日期） | 原 9+10 合并（模型变量并入各模块验证信号） |
| — | 风险提示 | 原 11，**App 内固定文案，不走 LLM** |

### 4.3 内容 Schema（要点）

- 每个分析模块的条目固定四字段：`fact` / `insight` / `prediction` / `verification`。
- 核心判断模块附 `metrics[]`（名称、数值、方向 up/down、说明），App 渲染指标小卡。
- 个股模块每只含 `symbol`（NVDA / 0700 / 600519 等，供跳转分析页）、涨跌幅、
  Bull/Base/Bear 三档（观点 + 关键价格或条件）。
- 催化剂条目含日期、事件、为什么重要、市场标签（美/中/港）。
- 顶层含 `market`、`trade_date`、`generated_at`、`summary`（一句话，供列表/推送用）。

## 5. 后端模块设计

按项目「新增模块五处落地」惯例：

| 文件 | 职责 |
| ------ | ------ |
| `app/models/morning_report.py` | SQLModel 表：`UUIDModel` 基类；`market`(us/cn/hk)、`trade_date`、`status`(generating/success/failed)、`content`(JSON)、`generated_at`、`model_name`、`duration_ms`、`error`；UniqueConstraint(market, trade_date) |
| `app/services/morning_report/schema.py` | 4.3 的内容 schema（三用） |
| `app/services/morning_report/prompts/` | 三市场 prompt 模板 |
| `app/services/morning_report/generator.py` | 生成循环：工具调用 → 结构化输出 → 校验重试 |
| `app/services/morning_report/data_tools.py` | akshare 行情工具封装（A股/港股指数、北向/南向、成交额），`@tool` 形式供 Agent 调用 |
| `app/tasks/morning_report.py` | Celery 任务（幂等）+ beat 定时注册 |
| `app/api/v1/morning_report.py` | 路由，`api.py` 注册 |

### API

```http
GET /api/v1/morning-report?market=us              # 当日；无成功版本时回退最近一期
GET /api/v1/morning-report?market=us&date=2026-09-08
GET /api/v1/morning-report/dates?market=us        # 历史日期列表（倒序）
```

- 认证：`get_current_user`，登录即可，免费。
- 响应 `meta`：`status`（success/generating）、`stale`（是否回退旧期）、`trade_date`。

### 生成任务细节

- 定时（celery beat，Asia/Shanghai）：美股 06:30（隔夜收盘后）、A股 07:10、
  港股 07:10（均在开盘前、用户通勤阅读窗口前）。
- 幂等：任务开头检查当天 `success` 记录，存在即跳过；唯一约束兜底并发。
- LLM：走 `llm_registry.get_default()`（生产 Claude Sonnet 或 GPT-4o），
  `llm_service.call()` 统一重试。

## 6. iOS 端设计

UI 高保真设计稿：`/Users/zhangfang/Desktop/晨报UI设计稿.html`（已评审通过）。

### 6.1 界面结构

- **Tab**：`MainTabView` 晨报排第一（晨报/分析/学习/我的），晨报 Tab 带红点。
- **主页面**：顶部三市场 pill 切换（主题蓝选中态）→ 标题行（日期、星期、生成时间、
  「历史」入口）→ 卡片流：
  - 核心判断大卡：总判断文案 + 3 个关键指标小卡（涨跌用 Theme.up/down）。
  - 分析模块卡：四层结构彩色小标签——事实(蓝)/洞察(紫)/预测(橙)/验证(绿)，
    颜色与后端 JSON 字段一一对应。
  - 重点个股卡：symbol + 名称 + 涨跌 + Bull/Base/Bear 三色分段（红/黄/绿）；
    **整卡可点，跳转该 symbol 的缠论分析页**（晨报与工具闭环）。
  - 催化剂日历卡：日期块 + 事件 + 市场 flag。
  - 底部固定风险提示文案（不走 LLM）。
- **交互**：下拉刷新；历史晨报（日期列表 sheet）；未登录显示登录引导。
- **状态**：
  - 生成中（06:30-07:30 窗口）：骨架屏 + 「晨报生成中，通常 07:30 前就绪」。
  - 生成失败/回退：展示最近一期，顶部黄条「今日晨报暂不可用，以下为 X月X日 内容」。

### 6.2 文件落点（新增 5 改 2）

| 文件 | 职责 |
| ------ | ------ |
| `Views/MorningReport/MorningReportTabView.swift` | Tab 主页 + 市场切换 + 状态管理 |
| `Views/MorningReport/ReportSectionCard.swift` | 四层结构通用卡片 + 各模块卡片 |
| `Views/MorningReport/StockCard.swift` | 个股 Bull/Base/Bear 卡 |
| `Models/MorningReportModels.swift` | 后端 JSON 的 Decodable 映射 |
| `Networking/MorningReportService.swift` | API 封装（走 APIClient） |
| `MainTabView.swift`（改） | 晨报 Tab 置首 |
| `Localization.swift`（改） | 新文案 |

## 7. 推送通知设计

生成成功的晨报通过 **APNs 远程推送**通知用户，点击通知直达晨报页。

### 7.1 前置条件（部署配置，一次性）

- Apple Developer 后台创建 **APNs Auth Key（.p8，Token-Based 认证）**。
- Railway 环境变量：`APNS_KEY_ID` / `APNS_TEAM_ID` / `APNS_BUNDLE_ID` / `APNS_PRIVATE_KEY`（p8 内容或路径）；`.env.example` 同步。
- Xcode 工程开启 **Push Notifications capability**（Signing & Capabilities）。

### 7.2 后端

| 文件 | 职责 |
| --- | --- |
| `app/models/device_token.py` | 设备 token 表：`UUIDModel`，`user_id`(FK)、`token`（唯一）、`platform`、`updated_at`；一个用户可多设备 |
| `app/services/push/apns_client.py` | APNs 发送封装（asyncio 库如 `aioapns`，JWT ES256 认证，`uv add` 引入） |
| `app/services/push/notifier.py` | 推送编排：查全部 token → 逐设备发送 → 失败仅记日志（不影响生成任务结果） |
| `app/api/v1/morning_report.py` 内新增 | `POST /api/v1/morning-report/device-token`：登录态注册/心跳刷新 token |

- 触发点：Celery 生成任务 `status=success` 落库后调用 `notifier`。
- 推送内容：标题「{市场}晨报已生成」，正文用当期 `summary`（核心判断一句话），
  `payload` 带 `{"market": "us"}` 供 App 直达对应市场页。
- 每个市场各推一条；A股/港股 07:10 同时完成时由 notifier 合并为一分钟内一条（去抖动，避免连续打扰）。

### 7.3 iOS

- **权限**：登录成功后或首次进入晨报页时请求通知权限（`UNUserNotificationCenter`）。
- **注册**：`UIApplicationDelegateAdaptor` + `didRegisterForRemoteNotificationsWithDeviceToken`
  拿到 token 后上报后端（`MorningReportService.registerDeviceToken`），登录时刷新。
- **点击跳转**：`UNUserNotificationCenterDelegate.didReceive` 解析 `payload.market`
  → 切换到晨报 Tab 并选中对应市场（`MainTabView` selection 绑定 + 通知路由）；冷启动同样处理。
- **前台展示**：App 在前台收到通知时仍展示系统横幅。
- 文件落点新增：`App/PushNotificationManager.swift`（权限 + token + 路由），
  `DeepAlphaChanApp.swift`（改，挂 adapter）。

> 注：远程推送需真机验证（模拟器不支持 APNs），联调阶段列入清单。

## 8. 错误处理

| 场景 | 处理 |
| ------ | ------ |
| LLM 超时/失败 | tenacity 重试 2 次；仍失败标记 `failed` + error |
| Celery 重试/重复触发 | 幂等检查 + market+trade_date 唯一约束 |
| API 请求当日不存在/失败 | 回退最近一期 success，`meta.stale=true` + 原日期（HTTP 200，避免客户端报错） |
| 生成中请求 | 返回 `status=generating`，App 骨架屏 |
| akshare 接口抖动 | 工具层捕获异常、错误信息作为工具结果返回，LLM 自行换搜索兜底 |
| JSON 校验失败 | 重试时把校验错误附给 LLM 修正（repair loop，最多 2 次） |
| APNs 推送失败 | notifier 仅记日志（structlog），不影响生成任务 success 状态；无效 token（410）时清理该 token 记录 |

## 9. 测试策略

- **单测（pytest，`tests/services/morning_report/`）**：
  - schema 校验（合法/非法样例）
  - prompt 渲染（三市场、日期注入）
  - API 路由（mock service）：当日命中、回退、generating、dates 列表
  - 任务幂等：已有 success 跳过
  - device-token 注册/心跳刷新（mock APNs client，不发真实推送）
  - 推送触发：success 后调用 notifier（mock）；去抖动合并逻辑
- **冒烟（`@pytest.mark.slow`）**：真实 LLM 生成一份完整美股晨报并通过 schema 校验；
  上线前手动跑。
- **iOS**：`MorningReportModels` JSON 解码单测；UI 不强制。

## 10. 明确不做（YAGNI）

- 邮件发送（ChatGPT 版保留原样，App 版不做）
- 用户自定义订阅市场/时段、推送开关设置页（后续可加 UserDefaults 开关）
- 晨报评论/分享卡片（后续可复用 Share 模块迭代）
- 港股/A股财报电话会模块（美股版已克制并入个股模块）

## 11. 实施顺序（供 writing-plans 展开）

1. 后端：模型 + 迁移 → schema → prompts → data_tools → generator → Celery 任务/beat → API → 单测
2. 推送：device_token 模型 + APNs client/notifier → 注册端点 → 接入生成任务 → 单测（mock）
3. iOS：Models → Service（含 token 上报）→ UI（卡片组件 → 主页面）→ Tab 置首 → 通知权限/注册/点击路由 → 解析单测
4. 联调：本地跑通三市场生成 → 模拟器验证 UI/状态 → **真机验证 APNs 推送与点击跳转** → 冒烟测试
