# DeepAlphaClub iOS

交易台（TradingDesk）自用 App：多智能体分析 / SSE 流式 / 控制 / 历史回放。
后端复用本仓库的 FastAPI 服务（`https://api.deepalpha.club`），零改动。

## 开发

```bash
brew install xcodegen          # 首次
xcodegen generate              # 生成 .xcodeproj（改 project.yml 后重跑）
(cd Core && swift test)        # Core 包单测（macOS，秒级）
open DeepAlphaClub.xcodeproj   # Xcode 里 Cmd+R 跑模拟器
```

命令行编译 App：

```bash
xcodebuild -project DeepAlphaClub.xcodeproj -scheme DeepAlphaClub \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build
```

## 结构

- `Core/` — 本地 SPM 包 `DeepAlphaCore`，全部业务逻辑（可 macOS 测试）
- `App/` — SwiftUI 视图层（xcodegen target）
- `Tools/make_icon.py` — App 图标是代码画的（三路观点汇聚成一条裁决），
  改设计后重跑：`uv run --with pillow python Tools/make_icon.py`，
  再把 `/tmp/iconwork/icon-1024.png`、`icon-tinted.png` 拷回
  `App/Assets.xcassets/AppIcon.appiconset/`
- 协议契约见仓库根的 `app/schemas/trading_desk.py`

## 认证

手机号 / 邮箱 + 密码登录，服务端判别账号类型（`POST /auth/login/account`）。
注册与找回密码都是双通道（邮箱验证码 / 短信验证码），密码规则与后端
`validate_password_strength` 对齐：8–64 位、含字母和数字。

token 存 Keychain。「保持登录」默认开；关掉后下次启动会清 token。

> Keychain 需要 `keychain-access-groups` entitlement（`App/DeepAlphaClub.entitlements`，
> 由 project.yml 生成）。缺了它 `SecItemAdd` 会返回 -34018，模拟器上必现。
> 构建时**不要**加 `CODE_SIGNING_ALLOWED=NO`，否则 entitlement 不会被注入。

### 冒烟时跳过手工登录

DEBUG 构建支持用环境变量自动登录（Release 恒不生效，凭据不进二进制）：

```bash
SIMCTL_CHILD_DEBUG_ACCOUNT=you@example.com \
SIMCTL_CHILD_DEBUG_PASSWORD=yourpassword \
  xcrun simctl launch booted club.deepalpha.ios
```

## 自测清单（v0.1.0 验收）

Core 层逻辑已由 104 个单测覆盖（认证 / reducer / SSE / API / 重连 / 缓存 / VM），
UI 与真实后端的联调需要账号，下列项目请登录后手动过一遍：

- [x] 登录 → 杀进程重开（token 从 Keychain 恢复，不用重登）
- [ ] 注册：邮箱收验证码 → 注册即登录
- [ ] 注册：手机号收短信验证码 → 注册即登录
- [ ] 找回密码：验证码 → 设新密码 → 用新密码登录
- [ ] 关掉「保持登录」→ 杀进程重开需要重新登录
- [ ] 输入 ticker + 选市场 → 开始分析 → SSE 实时输出
- [ ] 流程条状态推进（待办 / 进行中 / 完成）+ 每阶段信号 chip
- [ ] 暂停 / 继续 / 注入意见 / 停止
- [ ] 流式输出时上滑查看历史不被拉回；新 run 强制贴底
- [ ] 退后台 30s → 回前台续传，不丢事件也不重复
- [ ] 历史列表（缓存先出 + 远端刷新）+ 按标的过滤 + 回放全文直出
- [ ] token 过期后自动清 token 回登录页
- [x] iPhone 窄屏（分段切换单栏）/ iPad 宽屏（三栏并排）布局
