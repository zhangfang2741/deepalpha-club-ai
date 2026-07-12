# DeepAlpha 缠论 · App Store 上架手册（个人开发者）

> 面向：中国个人开发者，卖到美区 + 海外（首发不含中国大陆）。
> 代码侧已全部就绪，本文件是你要**一步步手动操作**的部分 + 可直接复制的文案。

---

## 0. 先决认知（个人账号两点）

1. **卖家名会显示你的真实法定姓名**（个人账号无法用公司名）。介意就注册公司账号（需 D-U-N-S）。
2. **账号注册区 = 你的居住地（中国）**，不是美区。一个中国个人账号即可上架到美区/全球——
   在 App Store Connect 的「可售区域」里勾选即可。
3. **卖订阅要填 W-8BEN 税表 + 收款卡**，否则内购收不到钱、也上不了架。

---

## 1. 分步清单（按顺序做）

### 阶段 A · 注册账号（当天可完成）
- [ ] developer.apple.com/programs 注册 **Apple Developer Program（个人）**，$99/年，用中国区 Apple ID，即时开通
- [ ] Xcode → Settings → Accounts 登录 Apple ID，确认能看到你的 Team

### 阶段 B · 本地验证（不用等账号）
- [ ] Xcode 打开 `ios/DeepAlphaChan.xcodeproj`，模拟器 `Cmd+R` 跑通，登录测试
- [ ] Edit Scheme → Run → Options → StoreKit Configuration 选 `Configuration.storekit`，测付费墙/试用/恢复
- [ ] 反馈任何报错或体验问题

### 阶段 C · App Store Connect 配置（有账号后）
- [ ] 新建 App：Bundle ID `club.deepalpha.chan`，主语言 **简体中文**，分类 **财务(Finance)**
- [ ] 协议/税务：签 **Paid Applications Agreement** + 填 **W-8BEN** + 收款卡
- [ ] 建订阅：群组「DeepAlpha Pro」→ 自动续订订阅
      - 商品 ID：`club.deepalpha.chan.pro.monthly`
      - 价格：**$9.99/月**（美元基准，Apple 自动换算各区）
      - 入门优惠：**免费试用 → 1 周**
- [ ] App 隐私标签：勾「联系信息-邮箱地址」，用途「App 功能/账号」，**不**用于追踪
- [ ] **可售区域**：勾 美国 + 港澳台 + 海外英文区，**先不勾中国大陆**（避开国区金融资质审查）
- [ ] Xcode：Signing & Capabilities → + Capability → **Sign in with Apple**

### 阶段 D · 官网（隐私/条款要公网可访问）
- [ ] 前端部署到 Vercel，确认 `https://deepalpha.club/privacy`、`/terms` 能打开
- [ ] 两个 URL 填进 App Store Connect（App 隐私政策 URL、订阅的服务条款 URL）

### 阶段 E · 素材
- [ ] App 图标（工程内已有占位图，建议换正式设计）
- [ ] 截图：至少一组 **6.7"（iPhone 15 Pro Max）**，5–8 张核心界面
- [ ] 填入下方文案

### 阶段 F · 提交
- [ ] Xcode Product → Archive → Distribute App → App Store Connect 上传
- [ ] 填「App 审核信息」：**测试账号**（下方模板）+ 备注
- [ ] 提交审核（订阅一并审），首审通常 24–48 小时

**最短关键路径**：A → C → D → F（B、E 并行）。个人账号最大时间变量是 W-8BEN + 收款审核，阶段 C 一上来先填。

---

## 2. App Store 文案（可直接复制）

### 2.1 简体中文（zh-Hans，主语言）

**App 名称**（≤30 字）
```
DeepAlpha 缠论
```

**副标题**（≤30 字）
```
美股缠论技术分析与买卖点
```

**促销文本**（≤170 字，可随时改，不需重新审核）
```
自动识别美股的分型、笔、线段、中枢与背驰，标注一二三类买卖点，配 MACD 与结构 GAP 分析。免费每日分析 3 支股票。
```

**关键词**（≤100 字符，逗号分隔无空格）
```
缠论,缠中说禅,美股,技术分析,K线,买卖点,中枢,背驰,分型,线段,MACD,趋势,选股,股票,盘面
```

**描述**（≤4000 字）
```
DeepAlpha 缠论把「缠中说禅」的技术分析框架自动化，帮你用结构化的方式看盘。输入美股代码，即刻得到完整的缠论结构与买卖点标注。

【核心功能】
· 自动缠论结构：分型、笔、线段、中枢、背驰一键识别，叠加在 K 线上
· 买卖点标注：一、二、三类买卖点，含强弱与判断依据
· MACD 副图：与主图联动，辅助判断背驰
· 结构 GAP 分析（会员）：用 AI 对比技术面结构与你的产业判断，找出背离点
· 原生流畅图表：双指缩放、单指平移、十字光标看单根 OHLC
· 图层自由开关：分型/笔/线段/中枢/买卖点按需显示

【适合谁】
· 学习和实践缠论的美股投资者
· 想用结构化方式复盘、而非凭感觉看盘的人

【订阅说明】
DeepAlpha Pro（自动续订订阅）
· 价格：US$9.99/月，含 7 天免费试用
· 权益：无限次缠论分析、解锁结构 GAP 分析、全部买卖点
· 免费用户每日可分析 3 支股票
· 订阅在确认购买时向你的 Apple ID 账户收费；免费试用结束后自动按月续订，除非在当前周期结束前至少 24 小时关闭。可随时在 系统设置 → Apple ID → 订阅 中管理或取消。
· 服务条款：https://deepalpha.club/terms
· 隐私政策：https://deepalpha.club/privacy

【重要声明】
本 App 提供的缠论结构、买卖点及操作倾向均由算法自动生成，仅供技术研究与学习参考，不构成任何投资建议或买卖要约。证券投资有风险，决策请自主判断并自负盈亏。
```

**「What's New」更新说明（首版）**
```
首个版本上线：
· 完整缠论结构自动识别（分型/笔/线段/中枢/背驰）
· 一二三类买卖点 + MACD
· 结构 GAP AI 分析
· 支持账号密码、注册与 Sign in with Apple
```

---

### 2.2 English（en-US，次要本地化）

**Name**（≤30）
```
DeepAlpha - Chan Analysis
```

**Subtitle**（≤30）
```
Chan theory for US stocks
```

**Promotional Text**（≤170）
```
Auto-detect fractals, strokes, segments, pivots and divergence on US stocks. Chan-theory buy/sell signals with MACD. Analyze 3 stocks free daily.
```

**Keywords**（≤100 chars）
```
chan theory,stock,technical analysis,candlestick,MACD,trading,US stocks,pivot,trend,signal,charting
```

**Description**（≤4000）
```
DeepAlpha automates Chan Theory (缠论) technical analysis for US stocks. Enter a ticker and instantly get the full Chan structure with annotated buy/sell points.

KEY FEATURES
· Automatic Chan structure: fractals, strokes, segments, pivots (zhongshu) and divergence, drawn over candlesticks
· Buy/sell signals: type 1/2/3 points with strength and rationale
· MACD subchart synced with the main chart to spot divergence
· Structure GAP analysis (Pro): AI compares the technical structure with your industry view to surface gaps
· Fluent native chart: pinch to zoom, drag to pan, crosshair for single-bar OHLC
· Toggle layers: fractals / strokes / segments / pivots / signals

SUBSCRIPTION
DeepAlpha Pro (auto-renewable)
· US$9.99/month with a 7-day free trial
· Unlimited analysis, unlock Structure GAP, all buy/sell points
· Free users can analyze 3 stocks per day
· Payment is charged to your Apple ID at confirmation of purchase. After the free trial, the subscription auto-renews monthly unless canceled at least 24 hours before the end of the period. Manage or cancel anytime in Settings → Apple ID → Subscriptions.
· Terms: https://deepalpha.club/terms
· Privacy: https://deepalpha.club/privacy

DISCLAIMER
All Chan structures, buy/sell points and suggestions are generated algorithmically for technical research and educational reference only, and do not constitute investment advice or any offer to buy or sell securities. Investing involves risk; make your own decisions.
```

---

## 3. App 审核信息（提交时填）

**测试账号**（给审核员，需真实可登录看全功能）
```
邮箱：<建一个测试账号>@example.com
密码：<设一个>
```

**备注（Notes）建议填**
```
本 App 是缠论（Chan Theory）技术分析工具，面向学习该方法的美股投资者。
所有分析均为算法生成，App 内多处标注“不构成投资建议”，仅供研究学习。
订阅（Pro）解锁无限次分析与结构 GAP；免费用户每日可分析 3 支股票。
可用上方测试账号登录体验全部功能；订阅可用沙盒账号测试。
```

---

## 4. 定价与可售区域备忘

- **基准货币**：美元，Pro = US$9.99/月（你想要的 9.9，Apple 最接近档位是 9.99）。
- **可售区域**：美国 + 港澳台 + 海外英文区；**首发不含中国大陆**（国区金融/证券信息类需 ICP 备案等额外资质）。
- 以后要覆盖中国大陆，再单独走国区资质流程。

---

## 5. 已在代码/仓库中就绪（无需你再做）

- 免责声明（登录页/主图/我的页/描述）
- 删除账号（`DELETE /auth/me` + 我的页入口）
- 隐私政策 / 服务条款页面（`frontend/app/privacy`、`/terms`）
- 注册、Sign in with Apple、订阅内购（StoreKit 2，7 天试用）
- 付费墙含自动续订披露 + 条款/隐私链接 + 恢复购买
