# DeepAlpha 缠论 · 原生 iOS App

把 deepalpha-club-ai 的**缠论分析**功能移植到原生 iOS（SwiftUI）。后端**零改动**，
App 直连线上 API（`https://api.deepalpha.club`）消费现有 `/api/v1/chan/*` 接口。

## 功能

- **登录**：复用后端 JWT 账号密码（`POST /api/v1/auth/login`），token 存 Keychain。
- **缠论主图**：原生 Canvas 自绘 K 线 + 缠论结构叠加（分型 / 笔 / 线段 / 中枢 / 买卖点），
  支持**双指缩放、单指横向平移、十字光标**看单根 OHLC。
- **MACD 副图**：与主图 x 轴联动（柱 + DIF/DEA）。
- **图层开关**：分型 / 笔 / 线段 / 中枢 / 买卖点 逐项开关。
- **结论面板**：当前结构摘要、操作倾向（含依据与风险提示）、买卖点列表、待确认结构。
- **结构 GAP 分析**：填写产业结构判断 → 异步 LLM 任务（`POST /api/v1/chan/gap` + 轮询）。
- **免责声明**：登录页、主图顶部、我的页均有醒目声明（金融类过审必备）。

## 目录结构

```
ios/
├── DeepAlphaChan.xcodeproj/       # Xcode 工程（文件系统同步，增删 .swift 无需改工程）
└── DeepAlphaChan/
    ├── App/                       # 入口、配置、主题
    ├── Models/                    # Codable（严格对齐后端 schema）
    ├── Networking/                # APIClient / Keychain / ChanService / AuthService
    ├── ViewModels/                # AuthViewModel / ChanViewModel
    ├── Views/                     # 登录 / 主界面 / 面板 / GAP / 我的
    │   └── Chart/                 # ChanChartView（自绘图表核心）
    └── Resources/                 # Info.plist / Assets（图标、强调色）
```

## 本地运行

要求 **macOS + Xcode 16 或更高**（用到了 iOS 17 的 `MagnifyGesture`、`onChange` 新签名）。

1. 双击 `ios/DeepAlphaChan.xcodeproj` 打开。
2. 选一个 iOS 17+ 模拟器（如 iPhone 15）。
3. `Cmd + R` 运行。
4. 用你在 deepalpha.club 的账号登录，输入代码（默认 AAPL）即可分析。

> 本地联调后端：把 `DeepAlphaChan/App/AppConfig.swift` 的 `baseURL` 改为
> `http://localhost:8000`（Info.plist 已对 localhost 放开明文 ATS）。

## 上架 App Store 待办清单

> 你目前：有 Mac，**尚无** Apple Developer 账号。按顺序推进：

### A. 账号与证书（必须先做）
- [ ] 注册 **Apple Developer Program**（$99/年）：https://developer.apple.com/programs/
      公司主体需 D-U-N-S 编码（申请约 1–5 个工作日）；个人主体即时可用。
- [ ] 在 Xcode `Settings → Accounts` 登录 Apple ID，勾选 **Automatically manage signing**，
      选择你的 Team。Bundle ID 已设为 `club.deepalpha.chan`（如被占用可改）。

### B. App Store Connect 配置
- [ ] https://appstoreconnect.apple.com 新建 App，绑定同一 Bundle ID。
- [ ] 填写 App 名称、副标题、关键词、描述、分类（**财务 / Finance**）。
- [ ] **App 隐私（Privacy Nutrition Label）**：如实勾选收集的数据
      （本 App 仅收集登录邮箱做账号认证，不做广告追踪）。
- [ ] 上传 **隐私政策 URL** 与 **服务条款 URL**（我的页已链到 `deepalpha.club/privacy`、
      `/terms`，需你在官网补上这两个页面）。

### C. 素材
- [ ] App 图标：工程已内置 1024×1024 占位图标（`Assets.xcassets/AppIcon`），
      上架前建议替换为正式设计稿。
- [ ] 截图：至少 6.7"（iPhone 15 Pro Max）一组；iPad 若支持需另出一组。
- [ ] 可选：预览视频。

### D. 合规重点（金融类审核严，务必满足）
- [ ] **投资免责声明**：已在多处落地，勿删除。审核指南 3.1.1 / 5.x 高频卡点。
- [x] **删除账号入口**：指南 5.1.1(v) 强制要求。**已实现**：后端 `DELETE /api/v1/auth/me`
      + 「我的」页「删除账号」入口（二次确认，删除后自动登出）。
- [ ] **测试账号**：提交审核时在「App 审核信息」里填一个可登录看全功能的账号密码。
- [ ] 若日后接入第三方登录（Google 等），**必须**同时提供 Sign in with Apple（指南 4.8）。

### E. 构建与提交
- [ ] Xcode `Product → Archive` → `Distribute App → App Store Connect` 上传。
- [ ] 在 App Store Connect 选择该构建版本，提交审核。
- [ ] 首次审核通常 24–48 小时。

## 后续 TODO（本 MVP 未含，上架前建议补齐）

1. **注册页**：当前仅登录；可加 `POST /api/v1/auth/register` 对应的注册页。
2. **Sign in with Apple**：提升转化，若未来加三方登录则为强制项。
3. **自选股 / 历史记录**：本地收藏常看标的，提升留存。
4. **图表增强**：成交量副图、更多周期（60min 等，依后端支持）。

## 与后端的对接契约

| 用途 | 方法 | 路径 |
|------|------|------|
| 登录 | POST（form-urlencoded：email/password/grant_type） | `/api/v1/auth/login` |
| 当前用户 | GET | `/api/v1/auth/me` |
| 删除账号 | DELETE | `/api/v1/auth/me` |
| 缠论分析 | GET（symbol/start_date/end_date/freq） | `/api/v1/chan/analysis` |
| 提交 GAP | POST（JSON） | `/api/v1/chan/gap` |
| 轮询 GAP | GET | `/api/v1/chan/gap/{job_id}` |

所有请求带 `Authorization: Bearer <token>`。字段命名与 `app/schemas/chan.py` 严格一致。
