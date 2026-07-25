# 拍照背单词 iOS App（WordLens）设计

> 日期：2026-07-25
> 状态：设计稿（待 review）

## 1. 背景与目标

做一个独立的 iOS App：用户用相机拍摄含英语单词的文档/书页，调用大模型识别出图中的英语单词，生成可供记忆的生词列表（含音标、释义），提供发音朗读帮助记忆；用户对生词按「认识 / 模糊 / 不认识」三档打标，App 用间隔重复算法（SM-2）驱动持续循环复习，直到用户记住为止。

MVP 定位为**个人自用工具**，不考虑上架 App Store 的合规细节（隐私政策、订阅、多语言等），优先做通核心闭环：拍照 → 识别 → 生词库 → 复习循环。

## 2. 关键决策（已与用户确认）

| 维度 | 决策 |
|------|------|
| 项目定位 | 新建独立 Xcode 工程（`ios/WordLens`，与 `DeepAlphaChan.xcodeproj` 平级），复用本仓库现有 FastAPI 后端基础设施（LLM 调用封装、Postgres、部署环境） |
| 账户体系 | **完全独立**，新建用户表和登录接口，不复用现有 `User`/`/auth` |
| 记忆算法 | SM-2 间隔重复算法，三档评分（不认识/模糊/认识）驱动 |
| 发音 | 系统 TTS（`AVSpeechSynthesizer`），默认美式（`en-US`），设置里可切换英式（`en-GB`） |
| 音标来源 | LLM 识别单词的同一次调用中一并生成国际音标（IPA） |
| 数据存储 | 后端 Postgres 云端存储（新建独立表），支持多设备同步 |
| 拍照流程 | 拍一张图 → 一次性识别全部单词 → 候选列表勾选 → 批量加入生词库（不支持连拍/批量导入，MVP 从简） |
| 原图存储 | **不保存**，仅用于一次性识别，识别完即丢弃 |
| 标记粒度 | 三档：不认识 / 模糊 / 认识 |
| 复习提醒 | MVP 不做推送通知，用户自行打开 App 复习 |
| App 定位 | 个人自用工具，暂不考虑上架 App Store |

## 3. 总体架构

- **后端**：复用现有 FastAPI 服务，新增独立业务域 `vocabulary`，遵循项目分层规则：
  - `app/api/v1/vocabulary.py`（路由，仅做参数校验+调用 service）
  - `app/services/vocabulary/`（业务逻辑：`recognizer.py` LLM 识别、`sm2.py` 间隔重复算法、其余 CRUD）
  - `app/schemas/vocabulary.py`（Pydantic request/response）
  - `app/models/vocabulary.py`（SQLModel 表，继承 `UUIDModel`）
  - 迁移走 `alembic revision --autogenerate`
  - LLM 调用统一走 `llm_service.call()`（复用多供应商 fallback）
  - 日志走 `structlog`
- **iOS**：`ios/WordLens/` 新 SwiftUI 工程，参考 `DeepAlphaChan/Networking/APIClient.swift` 的模式重新实现网络层（新账户体系、新接口），不共享 DeepAlphaChan 的登录态。
- **部署**：新路由挂载在现有 FastAPI 进程下（`/api/v1/vocabulary/*`），随现有服务一起部署到 Railway，无需新起服务。

## 4. 数据模型（新增表，均继承 `app.db.base.UUIDModel`）

**`VocabularyUser`**（独立账户体系）
- `id`(UUID) / `email`(unique) / `password_hash` / `created_at`

**`VocabularyWord`**（生词库条目，核心表）
- `id`(UUID) / `user_id`(FK) / `word`(str) / `phonetic_ipa`(str) / `part_of_speech`(str) / `definition_zh`(str)
- `status`：`new` / `fuzzy` / `known`（当前标记状态，用于列表筛选与统计）
- SM-2 字段：`repetition_count`(int, 默认 0) / `easiness_factor`(float, 默认 2.5) / `interval_days`(int, 默认 0) / `next_review_at`(datetime, 插入时设为立即到期) / `last_reviewed_at`(datetime, nullable)
- `created_at`
- 唯一约束：`(user_id, lower(word))`，插入时大小写不敏感去重

**`VocabularyReviewLog`**（复习历史，用于统计/排查算法问题）
- `id`(UUID) / `word_id`(FK) / `rating`(int: 0=不认识/1=模糊/2=认识) / `reviewed_at` / `interval_before`(int) / `interval_after`(int)

## 5. 后端 API（`/api/v1/vocabulary/*`）

| 用途 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 独立注册 | POST | `/vocabulary/auth/register` | 邮箱+密码，独立 JWT |
| 独立登录 | POST | `/vocabulary/auth/login` | |
| 拍照识别 | POST | `/vocabulary/recognize` | 上传图片 → LLM 识别 → 返回候选词（word/phonetic_ipa/part_of_speech/definition_zh），**不落库、不存图** |
| 批量加入生词库 | POST | `/vocabulary/words/batch` | 前端勾选后提交；按 `(user_id, word)` 去重，冲突项跳过并在响应中返回「已存在」列表 |
| 生词库列表 | GET | `/vocabulary/words?status=&q=` | 按状态筛选、关键词搜索 |
| 单词详情 | GET | `/vocabulary/words/{id}` | |
| 删除单词 | DELETE | `/vocabulary/words/{id}` | |
| 待复习队列 | GET | `/vocabulary/review/queue` | 返回 `next_review_at <= now` 的单词，按到期时间升序 |
| 提交复习结果 | POST | `/vocabulary/words/{id}/review` | body: `rating`；后端跑 SM-2 更新 `easiness_factor`/`interval_days`/`next_review_at`/`status`，写一条 `VocabularyReviewLog` |

`recognize` 是唯一直接调 LLM 的端点，prompt 要求模型输出结构化 JSON 数组 `[{word, phonetic_ipa, part_of_speech, definition_zh}]`，并过滤掉冠词/介词等虚词。返回前用 Pydantic 校验结构。

### SM-2 算法要点（`app/services/vocabulary/sm2.py`）

- 输入：当前 `repetition_count`/`easiness_factor`/`interval_days` + 本次 `rating`（0/1/2）
- `rating=0`（不认识）：`repetition_count` 重置为 0，`interval_days=1`，`easiness_factor` 不变
- `rating=1`（模糊）：`repetition_count` 不递增，`interval_days` 取较短固定间隔（如 1 天），`easiness_factor` 略微下调
- `rating=2`（认识）：`repetition_count += 1`，按标准 SM-2 公式递增 `interval_days`（第 1 次 1 天、第 2 次 6 天，之后 `interval_days *= easiness_factor`），`easiness_factor` 按标准公式上调
- `easiness_factor` 下限钳制在 2.13（SM-2 标准下限），避免越答越难
- `status` 联动：`rating=2` 且 `interval_days` 超过阈值（如 21 天）后置为 `known`；`rating=0` 置为 `new`；`rating=1` 置为 `fuzzy`

## 6. iOS 端设计

### 6.1 页面结构（Tab Bar 三栏）

```
📖 生词库   📷 拍照   🔁 复习
```

### 6.2 首页
```
┌─────────────────────────┐
│  WordLens          ⚙️   │
├─────────────────────────┤
│  今日待复习: 12 个        │
│  ┌─────────────────┐    │
│  │  开始复习 →       │    │
│  └─────────────────┘    │
│  生词库统计               │
│  ● 不认识 34  ● 模糊 18   │
│  ● 认识   56             │
├─────────────────────────┤
│  📖 生词库   📷 拍照   🔁 复习 │
└─────────────────────────┘
```

### 6.3 拍照识别 → 候选列表
```
┌─────────────────────────┐
│  ← 取消        识别结果   │
├─────────────────────────┤
│ ☑ apple 🔊    /ˈæp.əl/   │
│   n. 苹果                │
│ ☑ resilient 🔊 /rɪˈzɪl.iənt/│
│   adj. 有韧性的            │
│ ☐ the 🔊      /ðə/       │
│   （已在生词库中，默认不选）│
├─────────────────────────┤
│      加入生词库 (2)       │
└─────────────────────────┘
```
- 识别中：图片下方 loading + "正在识别单词..."
- 识别失败（无单词/超时）：提示"未识别到单词，请重新拍摄"，可重试
- 已在库中的词默认不勾选，但可展开显示
- 每个候选词旁有发音图标 🔊，加入前可先听发音确认

### 6.4 生词库列表
```
┌─────────────────────────┐
│  生词库          🔍搜索   │
│  [全部][不认识][模糊][认识]│
├─────────────────────────┤
│ resilient  /rɪˈzɪl.iənt/ │
│ adj. 有韧性的      🔴不认识 │
│ ────────────────────────│
│ paradigm  /ˈpær.ə.daɪm/  │
│ n. 范式           🟡模糊  │
└─────────────────────────┘
```
点击进入单词详情页：单词 + 音标 + 释义 + 大号发音按钮 + 手动调整标记 + 下次复习时间。

### 6.5 复习卡片流（核心循环）
```
正面：                       背面（点击/上滑翻转）：
┌─────────────────────┐    ┌─────────────────────┐
│      8 / 12          │    │      8 / 12          │
│    resilient          │    │   resilient           │
│    /rɪˈzɪl.iənt/ 🔊   │    │   /rɪˈzɪl.iənt/ 🔊   │
│   （点击翻转看释义）     │    │   adj. 有韧性的、能快速恢复的│
├─────────────────────┤    ├─────────────────────┤
│                       │    │ 😵不认识 😐模糊 😊认识  │
└─────────────────────┘    └─────────────────────┘
```
- 待复习队列 = `GET /vocabulary/review/queue` 返回结果，按到期时间排序
- 三档按钮提交 `POST /vocabulary/words/{id}/review`，成功后自动切下一张
- 队列清空后显示"今日复习完成"

### 6.6 设置页
- 发音口音切换：美式 `en-US` / 英式 `en-GB`（全局设置，存 `UserDefaults`）
- 登出

## 7. 错误处理

- **LLM 识别失败**（图片模糊/无英语单词/接口超时）：`recognize` 返回明确错误码，不写任何数据；iOS 提示重新拍摄。
- **LLM 返回格式异常**：后端 Pydantic 校验，解析失败记录 `structlog` 错误日志（脱敏后原始返回）并返回 500，不让脏数据入库。
- **重复单词**：`words/batch` 按 `(user_id, word)` 去重，冲突项跳过，响应里返回"已存在"列表，前端提示。
- **SM-2 边界**：`easiness_factor` 下限 2.13，`interval_days` 最小为 1，连续两次"不认识"重置 `repetition_count` 为 0。
- **网络/鉴权失败**：iOS 端统一拦截 401（跳转登录）和网络错误（toast + 重试）。

## 8. 测试策略（遵循项目 TDD 规则，先写 failing test）

- `tests/services/vocabulary/test_sm2.py`：SM-2 算法单元测试，覆盖三档评分下 `interval_days`/`easiness_factor`/`next_review_at` 的计算及边界（EF 下限、连续不认识重置）。
- `tests/services/vocabulary/test_recognizer.py`：mock `llm_service.call()`，测试 prompt 构造、JSON 解析成功/失败路径。
- `tests/api/v1/test_vocabulary.py`：集成测试核心端点（注册登录、recognize、batch 去重、review queue 排序、review 提交后状态更新）。
- iOS 端 MVP 阶段以手动测试为主，核心是跑通拍照→识别→加入→复习完整链路。

## 9. 非目标（MVP 不做）

- App Store 上架相关合规（隐私政策页、订阅内购、审核素材）
- 推送通知复习提醒
- 原图保存与回看语境
- 连拍/多图批量导入
- 例句、词根词缀等扩展学习内容
- 多语言/多语种支持（仅英语单词 + 中文释义）
