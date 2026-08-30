# DeepAlphaClub iOS

交易台（TradingDesk）自用 App：多智能体分析 / SSE 流式 / 控制 / 历史回放。
后端复用 [deepalpha-club-ai](../deepalpha-club-ai)（`https://api.deepalpha.club`），零改动。

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
- 协议契约见主仓库 `app/schemas/trading_desk.py`
