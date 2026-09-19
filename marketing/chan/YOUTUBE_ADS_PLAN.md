# 缠论 App 付费获客广告投放方案

状态：规划稿。目标地域：**中国、美国、香港**。两个地域用完全不同的广告体系，分两条轨道并行推进。

## 0. 为什么要分两条轨道

**Google 全家桶（搜索/YouTube/展示广告/Discover）在中国大陆被墙**，大陆用户默认触达不到（除非本身已翻墙，那部分人不能作为付费广告的可控增长来源）。所以：

| 地域 | 渠道 | 原因 |
|------|------|------|
| 美国 + 香港 | **Google Ads App Campaign** | Google 服务在这两个地区正常可用 |
| 中国大陆 | **Apple Search Ads（苹果自己的搜索广告）** | 广告位在 App Store 搜索结果内部展示，不经过 Google 基础设施，不受 GFW 影响 |

两条轨道账号体系、素材形式、计费方式都不同，下面分别说明。

## 1. App 侧归因：已实现（两条轨道共用）

不接第三方 MMP，只用 Apple 原生 SKAdNetwork（够用、免费、无需额外账号）。这部分只对 **Google Ads 轨道**有意义——Apple Search Ads 走的是 Apple 自己的 Attribution API，不依赖 SKAdNetwork。

- `ios/DeepAlphaChan/Resources/Info.plist`：新增 `SKAdNetworkItems`，声明 Google 的网络 ID `cstr6suwn9.skadnetwork`（Apple 只把归因 postback 发给 Info.plist 里声明过的网络，不加这个 Google Ads 后台永远看不到安装数据）。
- `ios/DeepAlphaChan/App/SKAdNetworkAttribution.swift`：新增转化值上报，三档单调递增：
  - `1` 注册/登录成功（`AuthViewModel.register()`）
  - `2` 完成一次缠论分析（`ChanViewModel.runAnalysis()` 成功后）
  - `3` 订阅 Pro（`StoreManager.purchase()` 成功后，命中即锁定归因窗口提前发送 postback）
- 已在模拟器 Debug 配置下跑通 `xcodebuild` 编译验证，逻辑本身不需要新版本发布也能工作——**但要让线上用户的安装真正携带这份 Info.plist 变更，仍然需要走一次正常的新版本发布**（改 Info.plist 属于要重新签名打包的改动，不是纯元数据，不能像 promotionalText 那样单独热更）。

**下一步动作**：下次发新版本（不用专门为这个改动发版，但下次发版必须包含这次改动）时确认 build 里带着这份 Info.plist。

---

## 轨道 A：美国 + 香港 → Google Ads App Campaign

### A1. 账号与 Campaign 结构

账户还没开，落地清单：

1. 用主邮箱在 [ads.google.com](https://ads.google.com) 开户，选"应用推广"目标，链接 App Store 上的「DeepAlpha 缠论」（`club.deepalpha.chan`，App ID `6806500280`）。
2. 检查账号是否被要求做 **金融服务广告商认证**（Google Ads 政策对"投资建议/交易分析"类目有专项认证要求）——开户后进 Ads 后台「政策管理」页确认，缠论分析属于技术分析工具而非投资建议，多数情况下不需要认证，但需要在广告文案里避免"稳赚""保证收益"这类措辞，避免被判定为需要认证或直接被拒。
3. Campaign 类型：**App Campaign（应用广告系列）**，目标选"应用安装"，出价策略"每次安装目标费用（tCPI）"。这个类型会自动把广告投到 Google 全渠道（搜索结果、YouTube 视频前贴/信息流、Google Play、Discover、Gmail、数百万展示广告联盟网站），机器学习自动分配预算到转化最好的渠道，不需要也不建议手动只选某一个渠道。
4. 地域：**美国 + 香港**分别开两个 Campaign（不要合并成一个），因为两地用户语言习惯不同（美国华人以简体中文/英文混合为主，香港用户默认繁体中文），文案和出价基准也不同。
5. 语言：香港 Campaign 用繁体中文；美国 Campaign 建议简体中文 + 英文各出一版素材分开测试，因为美国目标用户可能是留学生/华人移民（简体中文）也可能是本地投资者（英文），两者获客成本和转化率差异会很大，合并测容易得出误导性结论。
6. 预算：建议每个 Campaign 起始每日 $15-20，先各自跑满 1-2 周（App Campaign 机器学习需要至少 ~50 次安装的学习期才能稳定优化，预算太低学习期会拖很久）。
7. iOS 版本要求：`IPHONEOS_DEPLOYMENT_TARGET = 17.0`，Google Ads 后台链接 App 时会自动读取，无需额外配置，只是会自动排除 iOS 17 以下设备。

### A2. 广告素材：复用现有自动化产出的短视频

App Campaign 的素材组只**强制要求文本（标题/描述）+ 图片 + 图标**，视频是可选加分项而非必需——最快路径是先只用文案+App Store 截图起量，视频作为第二步补充。

**视频不需要从零拍。** `marketing/chan/` 下已有一套每日自动生产的教学短视频闭环（见 `RUNBOOK.md`），产出真实录屏 + AI 配音的竖版 720×1280 视频，發布到 YouTube 頻道 `DeepAlpha` 和 TikTok。这些视频已经满足 App Campaign 素材的核心要求，可以直接复用最近表现好的几条：

- 从 `marketing/chan/runs/*/production.json` 里挑最近 14 天审核通过（`review.json` 里 `visual/audio/creative_brief_match` 全部 `passed`）且发布后互动数据较好的几条。
- 提交给 App Campaign 前需要先发布到 YouTube 频道（可设为不公开链接，只要能被 Google Ads 读取到即可）。
- 竖版视频可以直接提交，Google 系统会自动为不同版位裁切适配；后续想要更好展示效果可以再补剪 16:9/1:1 版本，不是上线阻塞项。

### A3. 广告文案草稿

**香港（繁体中文）标题（≤30 字符 × 5）**：
1. 缠论分析 秒懂买卖點
2. 免費睇美股港股分型走勢
3. 自動畫中樞 不用手數
4. 技術分析新手都睇得明
5. DeepAlpha 缠论 App

**香港（繁体中文）描述（≤90 字符 × 5）**：
1. 分型、筆、線段、中樞、背馳，一鍵自動標註，美股港股 A 股都支援。
2. 睇得明缠論結構先識得判斷買賣點，新手都可以一步步學。
3. 免費試用，每日 3 次分析額度，訂閱解鎖無限次數。
4. 支援日線、周線切換，走勢圖表隨手放大縮小。
5. 立即下載 DeepAlpha 缠论，App Store 搜尋即可安裝。

**美国（简体中文）标题/描述**：与 ASO 关键词串（分型/笔/线段/中枢/背驰/买卖点/MACD/美股/港股/A股）保持一致的简体版本，上线前再产一版，同时补一版英文素材做 A/B（英文文案后续单独产出，需要先看简体中文素材的初步数据再决定要不要投入英文这条线）。

> 注意：文案避免"保證""穩賺""必漲"等触发金融广告审核的措辞，符合 Google Ads 金融产品政策安全边界，正式提交前再过一遍政策页确认。

---

## 轨道 B：中国大陆 → Apple Search Ads

### B1. 为什么选它、怎么落地

Apple Search Ads 的广告位直接嵌在 App Store 搜索结果里（用户搜"缠论""技术分析"这类词时，你的 App 可以出现在搜索结果第一位并标注"广告"），走的是 App Store 自己的基础设施，中国大陆用户正常可见，不受 GFW 影响。

**关键信息：`asc` CLI 已经内置完整的 Apple Ads API 支持**（`asc ads campaigns/ad-groups/creatives/targeting-keywords/geo/budget-orders` 等子命令），一旦账号凭证配置好，campaign 的创建、关键词定向、预算调整都可以直接用 CLI 代做，不需要你手动点后台。

### B2. 阻塞项：Apple Search Ads 账号尚未开通

`asc ads auth doctor` 检查确认目前没有存任何 Apple Ads 凭证。这是一套**独立于 App Store Connect API 的账号体系**，需要你本人操作：

1. 用你的 Apple ID（需要是 App Store Connect 团队里有权限的账号）登录 [searchads.apple.com](https://searchads.apple.com)，开通 Apple Search Ads 账号（Basic 或 Advanced 版本——中国区投放、按关键词精细定向，需要选 **Advanced**，Basic 版不支持自定义关键词只支持自动定向）。
2. 在 Search Ads 后台「设置 → API」里生成一个 API Key：会拿到 `client-id`、`team-id`、`key-id` 和一份私钥文件（`.pem`）。
3. 把私钥文件路径和另外三个 ID 给我（**不要把私钥内容直接贴在聊天里**，给文件路径即可），我用下面命令帮你存进 keychain：
   ```
   asc ads auth login --name "ChanSearchAds" --client-id "<CLIENT_ID>" --team-id "<TEAM_ID>" --key-id "<KEY_ID>" --private-key <私钥文件路径> --ad-account "<AD_ACCOUNT_ID>"
   ```

拿到凭证配置好之后，我可以直接：
- 建一个中国区（storefront `CN`）的 Search Results campaign，目标 App 是「DeepAlpha 缠论」。
- 关键词定向复用已经验证过排名效果的 ASO 关键词串（见 `project-aso-chan-keywords` 记忆）：`分型,笔,线段,中枢,背驰,买卖点,MACD,美股,港股,A股,图表,行情图表,技术分析,缠中说禅,周线,日线`，外加竞品/泛词做 Discovery 定向补充长尾流量。
- 创意用现有 App Store 截图（无需额外制作素材，Search Ads 的创意集直接复用产品页素材）。
- 设置每日预算和每次下载出价上限（CPT/CPA）。

### B3. 待你确认的两件事

- **Advanced 账号是否已经具备中国区投放资质**：Apple Search Ads Advanced 目前支持的国家/地区列表里是否包含中国大陆，需要在开户时确认（如果 Search Ads 尚未开放中国大陆投放，这条轨道要改回"大陆先做 ASO+自然量，不投付费广告"）。
- **中国区 App Store 账号是否需要额外的税务/银行信息**：中国区收付款主体和美区/港区不同，开通投放前 Search Ads 账号可能要求补充中国区的账单信息。

---

## 上线后怎么看效果、何时加预算

- **Google Ads 轨道**：前 1-2 周只看安装量、CPI 是否在可接受范围，不要过早看订阅转化——SKAdNetwork postback 有 24-144 小时延迟。两周后去「SKAdNetwork 转化」报告，对照三档转化值（1=注册 2=用过分析 3=订阅）判断用户质量。
- **Apple Search Ads 轨道**：Apple 自己的归因是实时的（不像 SKAdNetwork 有延迟），可以更快看到"点击→下载→注册"的转化率，重点看哪些关键词的下载成本低、转化率高，及时砍掉表现差的关键词。
- 两条轨道分开记账、分开评估，不要合并算整体 ROI——中国区和美港区的订阅定价、用户付费意愿本身就不是一回事。

## 待办 / 阻塞

- [ ] 下次发版把 SKAdNetwork 改动带上线（Google Ads 轨道依赖它）
- [ ] 开通 Google Ads 账号，确认是否需要金融服务认证（轨道 A）
- [ ] 开通 Apple Search Ads Advanced 账号，确认中国区投放资质和账单信息（轨道 B）
- [ ] 生成 Apple Ads API Key，给我凭证后由我执行 `asc ads auth login` 和后续 campaign 搭建
- [ ] 从现有 `marketing/chan/runs/` 里选 2-3 条视频供 Google Ads 轨道使用
- [ ] 美国 Campaign 的简体中文文案定稿；是否要追加英文素材待第一轮数据出来后再定
