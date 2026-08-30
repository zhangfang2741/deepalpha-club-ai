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
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' CODE_SIGNING_ALLOWED=NO build
```

## 结构

- `Core/` — 本地 SPM 包 `DeepAlphaCore`，全部业务逻辑（可 macOS 测试）
- `App/` — SwiftUI 视图层（xcodegen target）
- 协议契约见仓库根的 `app/schemas/trading_desk.py`

## 无账号时看界面

DEBUG 构建支持跳过登录页，直接进主界面看布局（假 token 对后端无效，任何请求都会报错）：

```bash
SIMCTL_CHILD_DEBUG_FAKE_LOGIN=1 xcrun simctl launch booted club.deepalpha.ios
```

## 自测清单（v0.1.0 验收）

Core 层逻辑已由 82 个单测覆盖（reducer / SSE / API / 重连 / 缓存 / VM），
UI 与真实后端的联调需要账号，下列项目请登录后手动过一遍：

- [ ] 登录 → 杀进程重开（token 从 Keychain 恢复，不用重登）
- [ ] 输入 ticker + 选市场 → 开始分析 → SSE 实时输出
- [ ] 流程条状态推进（待办 / 进行中 / 完成）+ 每阶段信号 chip
- [ ] 暂停 / 继续 / 注入意见 / 停止
- [ ] 流式输出时上滑查看历史不被拉回；新 run 强制贴底
- [ ] 退后台 30s → 回前台续传，不丢事件也不重复
- [ ] 历史列表（缓存先出 + 远端刷新）+ 按标的过滤 + 回放全文直出
- [ ] token 过期后自动清 token 回登录页
- [x] iPhone 窄屏（分段切换单栏）/ iPad 宽屏（三栏并排）布局
