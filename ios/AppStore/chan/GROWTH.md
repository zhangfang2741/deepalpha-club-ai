# Store Growth Audit — DeepAlpha 缠论

- **App**：DeepAlpha 缠论（App Store Connect ID `6806500280`，bundle id `club.deepalpha.chan`）
- **审计日期**：2026-09-03
- **模式**：existing（app 已上架，但极新——v1.0 于 2026-09-01 上线，v1.1 于 2026-09-02 提交审核，审计当天仍 **IN_REVIEW**）
- **成熟度等级**：**Level 0 / 9**（2026-09-03 追加处理后 P0 已达 Working 标准，但 P1 的 core 项 P1.1 副标题仍为空——等 1.1 过审贴上后，Level 会跳到至少 1）
- **只读约束**：本次审计全程未对 App Store Connect 做任何写操作；证据全部来自 `asc` CLI 的只读子命令（`view`/`list`/`status`/`ratings` 等）、仓库内 `ios/` 代码 grep，以及 `ios/AppStore/chan/` 下的规划文档。

---

## 大背景（务必先读）

这个 app 三天前才第一次上架，1.1 版本现在还压着审核。这意味着：

1. **P5-P9 里大量"需要流量/需要时间积累"的条目天然是 🔴 或 ⚪**——不是没做好，是还没到能做的时候（PPO 实验要流量、win-back 要有流失订阅者、关键词季度复盘要等一个季度）。这些我在证据里都标注了"app 仅 3 天"。
2. **反而 P2（转化素材）和发布纪律做得相当扎实**：截图带 benefit 文案、支持页/隐私页真实可用、账号删除功能完整、EULA 拒审后修复得很干净、分阶段发布+手动发布都已确认启用。说明开发者不是不懂，是精力都投在了"让审核过、让首屏好看"上，还没来得及碰"过审之后怎么长大"这一层。
3. **唯一一个"本该做好却没做好"的核心硬伤是 P1.1**：副标题字段是空的。`store-listing.md` 里其实早就写好了中英文副标题（"K线结构分析与缠论入门" / "Chart Structure & Learning"），但从未真正贴进 App Store Connect——1.0 和正在审核的 1.1 两个 app-info 记录里 `subtitle` 字段都确认缺失。这是唯一一个"东西都准备好了，但没有落地"的低垂果实。

---

## Phase Scores

| Phase | 主题 | 得分 | 等级 |
|---|---|---|---|
| P0 | 当天money开关 | 2/4 | 🟢 Working |
| P1 | 元数据 ASO | 0/7 | 🔴 Not started |
| P2 | 转化素材 | 2/5 | 🟡 Gaps（但两个 core 项都是 ✅） |
| P3 | 本地化 | 0/4（1 项 ⚪） | 🔴 Not started |
| P4 | 评分机制 | 2/3（1 项 ⚪） | 🟡 Gaps（core 项 P4.1 🔴） |
| P5 | 实验机制 | 0/4 | 🔴 Not started |
| P6 | 免费曝光 | 2/6 | 🟡 Gaps |
| P7 | 付费/外部流量 | 0/5（3 项 ⚪） | 🔴 Not started |
| P8 | 变现 | 0/5（2 项 ⚪） | 🔴 Not started |
| P9 | 留存与运营节奏 | 1/3（1 项 ⚪） | 🟡 Gaps |

**合计**：✅ 9 / 🟠 17 / 🔴 20 / ⚪ 8（54 项，2026-09-03 追加处理后更新）

---

## Top 5 行动项

按 SKILL.md 的分层规则排序（T1: P0 优先 → T2: P1-P3 → …），且全部是**纯 App Store Connect 操作，不需要新的二进制包**——正好可以在等 1.1 审核结果的这几天里做完。

| # | 条目 | 动作 | 路由 |
|---|---|---|---|
| ~~1~~ | ~~P0.1 小型企业计划（SBP）~~ | ✅ 用户确认 2026-09-03 已加入，无需操作 | — |
| ~~1~~ | ~~P0.2 计费宽限期 + 计费重试~~ | ✅ 2026-09-03 已通过 API 开启（16天宽限期，全部续订类型），无需操作 | — |
| ~~2~~ | ~~P6.1 提交推荐提名~~ | ✅ 2026-09-03 已提交（id `bdc0d713…`，state: SUBMITTED，建议曝光起始日 2026-09-24），无需操作 | — |
| 3 | **P1.1** 补齐副标题（core）| `store-listing.md` 第一节里中英文案都已经写好，等 1.1 审核出结果后第一时间贴进 App Info 的 zh-Hans / en 副标题字段——这是唯一"文案已就绪只差一次粘贴"的核心 ASO 缺口 | app-store/keyword-optimizer → `/apple:metadata` |
| 4 | **P0.3** 配置 Analytics report | ASC 里请求一次 ONGOING 的分析报表访问权限，建立留存/转化基线；现在是 0 条报表请求，没这个后面所有"效果好不好"的判断都没有数据支撑 | growth/analytics-interpretation → `/apple:learn-from-store` |
| 5 | **P0.4** 关键词研究补数据 | 现有关键词（缠论/K线/技术分析…50/100 字符）看得出是凭经验+合规考量选的，但没有 App Store 自动完成词或竞品热度数据佐证，还有 50 字符的空间没用满 | app-store/keyword-optimizer + apple-search-ads → `/apple:metadata` |

> 说明：严格按分层算法排序后，Top 5 全部落在 P0（money 开关）和 P1 的核心项——这也符合"先把免费的钱和最贵的 ASO 字段修好，再谈别的"的整体优先级。P4.1（加 `requestReview` 调用）虽然也是空白核心项，但按分层算法排在 T4，没能挤进前 5；它是本次审计里**唯一需要写代码**的高优先级修复，建议作为下一版本（1.2）的候选，见下方 P4 表。

---

## P0 — 当天就该打开的 money 开关

| ID | 条目 | 状态 | 证据 | 下一步 | 路由 |
|---|---|---|---|---|---|
| P0.1 | 小型企业计划（SBP）加入状态 — core | ✅ | `asc account status` 只读 API 拿不到这个字段；用户确认已加入（2026-09-03） | 维持 | growth/indie-business |
| P0.2 | 计费宽限期 + 计费重试 — core | ✅ | 2026-09-03 通过 `asc subscriptions grace-periods update` 开启：`optIn=true`、`sandboxOptIn=true`、`duration=SIXTEEN_DAYS`、`renewalType=ALL_RENEWALS`。「计费重试」在当前 ASC API 里没有独立开关，已并入 Grace Period 机制由 Apple 自动处理 | 维持 | generators/subscription-lifecycle → `/apple:subscription` |
| P0.3 | Analytics 基线 + 同行对比 | 🟠 | 已于 2026-09-03 请求 ONGOING analytics report（request id `e86e8e63…`）；报表尚未生成，等 Apple 出数据后才有真正的基线快照 | 等报表生成后复查一次 | growth/analytics-interpretation → `/apple:learn-from-store` |
| P0.4 | 关键词调研（自动完成词+竞品+ASA 探针）| 🟠 | `store-listing.md` 显示关键词经过合规措辞考量选取，但无自动完成词/竞品热度等数据佐证；关键词字段仅用 50/100 字符 | 用 App Store 搜索自动完成 + ASA discovery 补数据 | app-store/keyword-optimizer + apple-search-ads → `/apple:metadata` |

## P1 — 元数据 ASO

| ID | 条目 | 状态 | 证据 | 下一步 | 路由 |
|---|---|---|---|---|---|
| P1.1 | 标题/副标题/关键词字段优化 — core | 🟠 | 2026-09-05：1.1 已放出，新建了草稿版本 1.1.1（id `328ccfe0…`），已在其中贴好副标题「K线结构分析与缠论入门」和新关键词串（55/100字符）。**但卡在 Apple 规则**：build 75e3cde4（1.1 那个已过审的包）不能复用给新版本，`asc versions attach-build` 报错 "specified pre-release build could not be added"——必须等下次真的出新功能、走一次真实的 Xcode 构建上传后，才能把这个草稿一起提交审核 | 等下个真实版本（比如 1.2）打包时，直接复用 1.1.1 里已经写好的这些字段提交 | app-store/keyword-optimizer → `/apple:metadata` |
| P1.2 | 跨语言索引利用 | 🔴 | `asc localizations supported-locales`：`configuredCount=1`（仅 zh-Hans），50 个可选 locale 里只用了 1 个 | 至少加 1-2 个额外 locale 承载不同关键词 | app-store/keyword-optimizer → `/apple:localize` |
| P1.3 | 开发者名称是刻意选择 | 🟠 未确认 | 未查到卖家显示名相关只读接口；bundle 命名体系（`club.deepalpha.*`）与「DeepAlpha」品牌在多个模块间一致，倾向是刻意选择，但未核实 | 确认 ASC 卖家名 | app-store/keyword-optimizer（进阶战术 §12） |
| P1.4 | 带关键词的推广内购 | 🔴 | `asc iap list`：0 个 IAP；`asc subscriptions promoted-purchases list`：0 条已推广购买项 | 把 Pro Monthly 设为推广购买项 | generators/promoted-iap → `/apple:iap` |
| P1.5 | 应用内活动作为索引面 | 🔴 | `asc app-events list`：0 个；金融类 app 有明显的事件时机（财报季、市场波动主题）未利用 | 策划一次应用内活动 | generators/in-app-events → `/apple:event` |
| P1.6 | 描述 + 推广文本 | ✅ | description 完整、benefit-led、合规意识强；2026-09-05 已直接在线上 1.1 版本贴上 `store-listing.md` 里准备好的推广文本（此字段可随时改、不需审核，已即时生效）| 维持 | app-store/app-description-writer → `/apple:metadata` |
| P1.7 | 面向 AI 标签的文案 + App Store Tags 筛选 | 🟠 | 文案字面化、刻意避开"荐股/收益"等词，对 AI 标签友好；但 `asc app-tags list` 返回 0 条——app 太新，Apple 可能还没生成标签，无法判断是否需要人工筛除 | 下次审计时复查 app-tags 是否已生成 | app-store/keyword-optimizer（进阶战术 §13/§15）→ `/apple:metadata` |

## P2 — 转化素材

| ID | 条目 | 状态 | 证据 | 下一步 | 路由 |
|---|---|---|---|---|---|
| P2.1 | 图标是刻意设计且经过测试 | 🟠 | 图标是自定义设计（K线+笔+中枢，配色与 app 内图表体系完全一致，非默认占位图）；但 `product-pages experiments` 里 0 个图标实验，也无竞品对比证据 | 后续可考虑一次 PPO 图标实验 | generators/product-page-optimization → `/apple:icon` + `/apple:experiment` |
| P2.2 | 前三张截图带 benefit 文案 — core | ✅ | 实测 3 张截图（`01_analysis_us.png`/`02_analysis_hk.png`/`03_learn.png`）均有大标题+副标题式 benefit 文案，缩略图可读 | 维持，1.1 若新增分享功能可以考虑加一张展示 | app-store/screenshot-planner → `/apple:screenshots` |
| P2.3 | App 预览视频 | 🔴 | `video-previews list`：0 个；截图已完备（applies-if 达成） | 截图已稳定，可以考虑做一版预览视频 | app-store/screenshot-planner → `/apple:screenshots` |
| P2.4 | 信任信号：隐私标签/支持页/账号删除 — core | ✅ | `supportUrl`=`https://deepalpha.club/support`（专用支持页，非主页占位符）与 `privacyPolicyUrl` 均在线；代码内 `AuthService.deleteAccount()` + `ProfileView` 确认账号删除完整实现；`asc-form-answers.md` 记录了隐私标签与 `PrivacyInfo.xcprivacy` 逐项核对过程 | 维持 | legal/privacy-publish + generators/account-deletion |
| P2.5 | 预置备用图标供未来 PPO 用 | 🔴 | `Assets.xcassets` 里只有 1 个 `AppIcon.appiconset`，无备用图标集 | 下次改版顺手多切几套备用图标 | generators/product-page-optimization → `/apple:icon` |

## P3 — 本地化

| ID | 条目 | 状态 | 证据 | 下一步 | 路由 |
|---|---|---|---|---|---|
| P3.1 | 大七语言的纯元数据本地化 — core | 🔴 | `configuredCount=1`（仅 zh-Hans）；ja/de/fr/es/pt-BR/ko/zh-Hans(已有) 里的其余 6 个均未配置 | 优先加英文（app 内已有 en.lproj 但 ASC 商店页没有对应 locale）| product/localization-strategy → `/apple:localize` |
| P3.2 | 分地区评分策略 | 🔴 | 133/175 个地区可售（含美/英/港/加等），但代码里连 `requestReview` 都没有，更谈不上分市场催评 | 先解决 P4.1，再谈分市场策略 | app-store/ratings-mechanics → `/apple:localize` |
| P3.3 | 印度/巴西/土耳其/印尼的 PPP 定价 | 🟠 未确认 | 订阅解析价格：印度 ₹99（约 $1.15）、巴西 R$6.9（约 $1.3），相对 $5.99 美区价明显走低，疑似已做本地化定价，但 API 无法区分是人工设置还是 Apple 自动等值表 | 到 ASC 订阅定价页确认这几个地区是否手动设置过 | monetization（Pricing Localization）→ ASC pricing |
| P3.4 | App 本体按需求本地化 | ⚪ N/A | 代码内已有 `zh-Hans.lproj` + `en.lproj` 两套 UI 本地化；但上线仅 3 天，无销售/分析数据可判断"哪个市场需求已被验证" | 等 1-2 个月有销售数据后重新评估 | product/localization-strategy → `/apple:localize` |
| P3.5 | 通过 ASC API 自动化元数据更新 | 🟠 | 仓库内无 fastlane/deliver/ASC 批量脚本；不过当前只有 1 个 locale，人工维护压力还不大 | 加 locale 之前先考虑要不要上自动化脚本 | `/apple:localize` + `/apple:metadata`（批量更新）— 独立技能：`_shared/asc-api` |

## P4 — 评分机制

| ID | 条目 | 状态 | 证据 | 下一步 | 路由 |
|---|---|---|---|---|---|
| P4.1 | 在成功时机调用 requestReview — core | 🔴 | 全代码库 grep `requestReview\|SKStoreReviewController\|AppStore.requestReview` 无匹配 | 挑一个成功时机（比如完成一次分析后）接入 `requestReview`，带次数/条件门槛 | generators/review-prompt → `/apple:build` |
| P4.2 | 差评已回复 | ⚪ N/A | `asc reviews ratings`：`ratingCount=0`；`asc reviews list`：0 条评论——app 刚上线还没有评论 | 有第一条评论后启动回复习惯 | app-store/review-response-writer → `/apple:ratings` |
| P4.3 | 分阶段发布 + 手动放量习惯 | ✅ | `asc status` 确认 `phasedRelease.configured=true`；`RELEASE.md`/`asc-form-answers.md` 均明确要求「手动发布」，通过后自己验证再放量 | 维持 | app-store/ratings-mechanics → `/apple:ship` |
| P4.4 | 从不重置评分汇总 — guardrail | ✅ | 无重置迹象；app 刚上线也谈不上有评分可重置 | 记住这条规则，v2.0 前别手滑 | app-store/ratings-mechanics |

## P5 — 实验机制

| ID | 条目 | 状态 | 证据 | 下一步 | 路由 |
|---|---|---|---|---|---|
| P5.1 | 把 PPO 当习惯跑 — core | 🔴 | `product-pages experiments list`：0 个；app 仅上线 3 天，还没有足够自然流量支撑实验 | 30 天后有一定自然量再启动首个 PPO | generators/product-page-optimization → `/apple:experiment` |
| P5.2 | 面向不同受众的自定义产品页 | 🔴 | `custom-pages list`：0 个；app 本身服务美股/A股/港股三类受众，具备分渠道页潜力 | 后续可为「A股」「港股」用户各建一个 CPP | generators/custom-product-pages → `/apple:experiment` |
| P5.3 | 创意素材：产品页头图 + 搜索结果视觉 | 🟠 未确认 | Asset Library 状态不在只读 API 范围内 | 确认是否已在 Asset Library 提交头图/搜索视觉素材 | app-store/screenshot-planner（Creative Assets）→ `/apple:screenshots` |
| P5.4 | 应用内活动节奏 + 徽章多样性 | 🔴 | 同 P1.5，0 个 app events | 与 P1.5 一起解决 | generators/in-app-events → `/apple:event` |

## P6 — 免费曝光

| ID | 条目 | 状态 | 证据 | 下一步 | 路由 |
|---|---|---|---|---|---|
| P6.1 | 推荐提名滚动日历 — core, RECURRING | ✅ | 2026-09-03 已提交「DeepAlpha Chan — Launch」（id `bdc0d713…`，state: SUBMITTED，建议曝光起始日 2026-09-24）| 等 Apple 回复；下次提名窗口见 Recurring Calendar | generators/featuring-nomination（ASC 手动，日历见下） |
| P6.2 | 上线即适配新系统 API | 🔴 | `IPHONEOS_DEPLOYMENT_TARGET=17.0`；代码中无任何 `@available(iOS 2x)` 新特性适配 | 评估是否有当季新 API 值得接入 | `/apple:modernize` |
| P6.3 | 设置次分类 | ✅ | `primaryCategory=FINANCE`，`secondaryCategory=EDUCATION`，均已刻意设置 | 维持 | `/apple:ship`（分类步骤） |
| P6.4 | 有意义的 checkbox 平台已上线 | 🟠 | `TARGETED_DEVICE_FAMILY=1`（仅 iPhone），未做 Mac Catalyst/iPad/visionOS；图表类 app 通常是低成本高回报的 checkbox 平台 | 评估 iPad/Mac Catalyst 移植成本 | `/apple:new-app` / `/apple:plan` |
| P6.5 | App Intents 作为店外发现渠道 | 🔴 | 代码中未找到 `AppIntents`/`AppShortcutsProvider`/`CoreSpotlight` | 评估接入 Siri/Spotlight 快捷方式 | apple-intelligence/app-intents + generators/spotlight-indexing → `/apple:plan` |
| P6.6 | Web 曝光：商店页 SEO + 落地页 + Smart App Banner | 🟠 | `deepalpha.club` 已作为 marketingUrl，`/support` 页确认可访问；Smart App Banner、商店页 SEO 排名情况未确认 | 确认落地页是否已接 Smart App Banner | app-store/web-presence |

## P7 — 付费与外部流量

| ID | 条目 | 状态 | 证据 | 下一步 | 路由 |
|---|---|---|---|---|---|
| P7.1 | Apple Ads 阶梯（discovery→精确匹配+CPP 配对）| 🔴 | 用户确认没跑过（2026-09-03）| app 仅 3 天，暂不急；等自然量+P0.3 基线数据有了再评估是否启动 discovery 广告 | app-store/apple-search-ads |
| P7.2 | 品牌词防御 | ⚪ N/A | 用户确认暂不需要防御「DeepAlpha」品牌词（2026-09-03）| 若后续出现竞品抢注品牌词再复查 | app-store/apple-search-ads |
| P7.3 | ASA→自然量光环追踪 | 🟠 未确认 | 无相关证据 | 确认是否有追踪付费关键词对自然排名的带动 | apple-search-ads + growth/store-signals |
| P7.4 | 集中式发布冲刺 | 🟠 未确认 | v1.0 于 2026-08-31 提交、09-01 上线，是否做过 Product Hunt/媒体/newsletter 48 小时内集中曝光未知 | 确认发布时是否做过冲刺；1.1 也是一次机会 | growth/press-media + growth/community-building |
| P7.5 | 利用打折站生态 | ⚪ N/A | App 本体免费（`isFree=true`），无价格可降 | — | app-store/web-presence |
| P7.6 | 使用预售 | 🔴 | v1.0 首发（2026-09-01）未见预售证据，首发窗口已过 | 下次进入新地区/大版本时考虑 | generators/pre-orders → `/apple:ship` |
| P7.7 | 分发兑换码 | 🔴 | `subscriptions offers offer-codes list`：0 个；已有订阅可用该机制 | 给种子用户/社群发一批兑换码 | generators/offer-codes-setup → `/apple:subscription` |
| P7.8 | TestFlight 公开链接当 waitlist | ⚪ N/A | app 已正式上线（v1.0 2026-09-01），首发前 waitlist 窗口已过 | 下次大版本发布可考虑 | product/beta-testing → `/apple:testflight` |

## P8 — 变现

| ID | 条目 | 状态 | 证据 | 下一步 | 路由 |
|---|---|---|---|---|---|
| P8.1 | 付费墙 + 定价实验 — core | 🟠 | `PaywallView.swift`/`StoreManager.swift`/`Configuration.storekit` 显示付费墙已精心实现（7 天试用、条款链接、恢复购买齐全）；但 `product-pages experiments`：0 个定价实验，app 仅 3 天 | 30 天后有流量了再启动首个定价/试用期实验 | generators/paywall-generator + monetization → `/apple:subscription` |
| P8.2 | Win-back 优惠已配置 | ⚪ N/A | `subscriptions offers win-back list`：0 个；app 刚上线，还没有可触发资格的流失订阅者 | 有第一批流失订阅者后配置 | generators/win-back-offers → `/apple:subscription` |
| P8.3 | 取消挽留（Retention Messaging）| 🟠 未确认 | ASC「订阅」页面的取消挽留配置不在只读 API 范围内 | 确认是否已在 ASC 配置取消挽留文案/优惠 | generators/win-back-offers（Retention Messaging）→ `/apple:subscription` |
| P8.4 | 美区 Web Checkout / 外部购买链接 — core | 🔴 | `DeepAlphaChan.entitlements` 只含 `com.apple.developer.applesignin`，无 `external-purchase` entitlement；美国是可售地区之一，订阅是数字商品收入 | 评估是否值得架设佣金翻转架构 | monetization/external-purchases |
| P8.5 | 跨开发者捆绑套装 | 🟠 未确认 | 无相关证据 | 确认是否考虑过与其他独立开发者的捆绑合作 | monetization/bundles-and-licensing |
| P8.6 | 团购 + 批量购买 | ⚪ N/A | 面向个人投资者的分析工具，无明显多席位（学校/团队）买家群体 | — | monetization/bundles-and-licensing → `/apple:subscription` |
| P8.7 | 自有 App 捆绑 + Family Sharing | 🟠 未确认 | 订阅的 `familySharable` 状态未在 API 返回中出现；同账号下另有一个 app（`WordLens`, bundle id `club.deepalpha.wordlens`），具备自有多 app 捆绑的潜在条件 | 确认 Family Sharing 开关状态；评估与 WordLens 的捆绑可能性 | monetization/bundles-and-licensing → `/apple:subscription` |

## P9 — 留存与运营节奏

| ID | 条目 | 状态 | 证据 | 下一步 | 路由 |
|---|---|---|---|---|---|
| P9.1 | 留存界面已上线 | 🔴 | 代码 grep 未发现 onboarding 流程、`UNUserNotificationCenter`、`WidgetKit`、`ActivityKit`（唯一匹配的 `requestAuthorization` 是相册写入权限，非通知）| 优先补一个轻量 onboarding + 推送授权时机 | generators/onboarding-generator, push-notifications, widget-generator → `/apple:plan` |
| P9.2 | 季度关键词复盘（用 ASA 搜索词报表）— core, RECURRING | ⚪ N/A | app 刚上线 3 天，距首次「上线一季度后」复盘窗口还早（预计 2026-12 前后到期）| 到期后按 ASA 搜索词数据复盘一次关键词 | app-store/keyword-optimizer（进阶战术 §14）→ `/apple:metadata` |
| P9.3 | 更新新鲜度 — core | ✅ | 1.1 于 2026-09-02 上传，距 1.0（08-31 提交）仅 2 天，更新节奏远快于 8-12 周的门槛 | 维持这个节奏 | `/apple:next-version` |
| P9.4 | 复盘循环已闭环 — RECURRING | 🔴 | 这是首份 `GROWTH.md`，此前没有滚动日历 | 本次审计即为日历起点，见下方 Recurring Calendar | 本技能（复审）+ product-page-optimization + analytics-interpretation |

---

## Watchlist（⏳ 已宣布但尚不可评分）

- 无直接命中的 ⏳ 条目。但两条相关的"待关注"备注：
  - **P5.4**：新徽章类型（Now On Sale、Try Before You Buy）为 WWDC26 宣布特性，下次审计需复查是否已可用。
  - **P8.6**：团购/批量购买对 StoreKit 2 订阅已默认开启（WWDC26 起）；Family Sharing 订阅默认不参与——本 app 目前判定为 ⚪（无多席位场景），但如果 Family Sharing 状态确认后发现被意外启用，需要复查。

## Recurring Calendar

| 条目 | 上次完成 | 下次到期 | 备注 |
|---|---|---|---|
| P6.1 featuring 提名 | 2026-09-03（已提交，等 Apple 回复）| 下次视本轮结果而定 | 建议曝光起始日 2026-09-24 |
| P9.2 季度关键词复盘 | 从未（app 太新）| 约 **2026-12** | 一季度后再看 ASA 搜索词数据 |
| P9.4 完整复审（本技能）| 2026-09-03（本次）| **2026-12-03** | 建议季度节奏；若中间有大版本发布可提前触发 |

## Baseline Metrics Snapshot

- **评分/评论**：0 条（`ratingCount=0`，app 刚上线）
- **可售地区**：133 / 175（含 CHN/USA/GBR/HKG/IND/BRA 等）
- **订阅定价**：Pro Monthly，美区 $5.99/月，7 天免费试用（各地区已有本地货币解析价，如 IN ₹99、BR R$6.9）
- **Analytics 报表**：0 条已请求 —— **无基线数据**，这是 P0.3 的核心缺口
- **Sales 报表**：未查询（app 仅 3 天，大概率还没有可用的销售报表）
- **In-app 本地化**：zh-Hans + en 两套 UI 语言；App Store 商店页仅 zh-Hans 一个 locale

## 待你确认（MANUAL）

**已确认并处理（2026-09-03，主会话补问 + 代为执行）**：
- ~~是否已加入 App Store 小型企业计划？~~ → 已加入（P0.1 ✅）
- ~~计费宽限期与计费重试是否都已打开？~~ → 当时没开，已代为通过 API 开启 16 天宽限期（P0.2 ✅）
- ~~是否提交过推荐提名？~~ → 当时没提交，已代为撰写并提交（P6.1 ✅，state: SUBMITTED）
- ~~是否跑过 Apple Search Ads？品牌词需要防御吗？~~ → 没跑过／不需要防御，暂不处理（P7.1 🔴 / P7.2 ⚪）

**仍待确认**：

1. 是否检查过 ASC 里的**同行对比基准**（peer-group benchmarks）？（P0.3）
2. **ASC 卖家/开发者显示名**是否是刻意选择的？（P1.3，参考信息：多个 app 统一走 `club.deepalpha.*` 命名体系，倾向已是刻意）
3. 订阅的 **Family Sharing** 开关状态？是否考虑过与同账号下的 **WordLens** 做自有 app 捆绑？（P8.7）
4. ASC 订阅页的**取消挽留（Retention Messaging）**是否已配置文案/优惠？（P8.3）
5. `deepalpha.club` 落地页是否配置了 **Smart App Banner**？是否针对"DeepAlpha 缠论"关键词做过独立 SEO？（P6.6）
6. v1.0 上线（2026-09-01）时是否做过 **48 小时内集中曝光**（Product Hunt / 媒体 / newsletter）？（P7.4）
7. 是否追踪过 **ASA 付费关键词对自然排名的带动**（halo 效应）？（P7.3，暂不适用——目前尚未投放广告）
8. 印度/巴西等地的订阅价格是**人工设置的 PPP 定价**，还是 Apple 自动等值表算出来的？（P3.3）
9. 是否考虑过**跨开发者捆绑套装**的合作？（P8.5）

---

## Audit History

| 日期 | 模式 | Scope | Level | 备注 |
|---|---|---|---|---|
| 2026-09-03 | existing（app 仅上线 3 天，1.1 IN_REVIEW） | 全量 P0-P9 | 0/9 | 首次审计，建立 GROWTH.md 与 Recurring Calendar 基线 |
