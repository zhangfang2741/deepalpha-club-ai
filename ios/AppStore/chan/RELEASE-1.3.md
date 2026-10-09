# 缠论 App 1.3 发版操作清单（2026-10-09）

线上：**1.2.1 (4)**，`READY_FOR_DISTRIBUTION`（版本 ID `082c5fe5-9e2b-4d78-95f4-47a7ceeeccff`）。本次提交：**1.3 (5)**。
App ID：`6806500280`，Bundle ID：`club.deepalpha.chan`，Release 签名团队 `L565U2X5NL`（自动签名）。

按顺序执行，每一步都有**验收标准**；验收不过就停下，把输出记到文末「执行记录」，不要跳步。
标了 **【人工】** 的步骤要在真机或网页上操作，执行者做不了就留给人，其余步骤都能在命令行完成。
`asc` 命令的参数以 `asc <命令> --help` 为准；下面的写法已在 2026-10-09 对照过当前 CLI。

---

## 本版内容（1.2.1 构建之后的 iOS 改动，均已在 master）

| 变化 | 位置 / 说明 |
|------|------|
| 图表指标栏：均线 / EMA（12, 26）/ BOLL（20, 2） | 图表下方一行，点一下开 / 关，**默认全部关**；右边的按钮打开参数设置小面板（每条线可勾选、−/+ 调周期） |
| 指标数值 | 图表左上角，每个指标一行，点一下折叠成只剩指标名 |
| 全屏按钮 | 从左上角移到右上角 |
| 30 分钟周期（**会员功能**，示例股除外） | 分析页条件里多一个「30 分钟」；与「次级别确认」同一权益 |
| 搜索按名称联想 | 分析页搜索框输入名称出联想浮层，A 股 / 港股可输中文名 |
| 买卖点口径移到「我的」一级页 | 原来在「我的 → 偏好设置」里；偏好设置只剩「显示专业数值」 |
| 去掉「我的」页的「重看新手导览」 | 学习页、首次进雷达仍能看到导览 |
| 雷达示例日也能打开基本面名单 | 免费用户选中示例日时，画布左下角显示「名单」，名单里的买卖点只按示例日那天判断 |
| 修复：雷达行业横条偶发一直「数据准备中」 | 示例日必现，现在正常显示行业并可筛选 |
| 修复：手指放在 K 线 / MACD 上无法上下滚动页面 | iOS 18 起出现 |
| 修复：在图表上往右拖会退回上一页 | iOS 26「内容区右滑返回」抢手势 |
| 修复：MACD 副图越往右越和 K 线错位 | 按合并 K 线的最后一根对齐 |

后端相关接口（EMA / BOLL 参数、搜索联想）已随 master 部署到线上，App 不依赖未上线的后端。
营销自动化代码（`App/MarketingAutomation.swift`、`MarketingStep.swift`）包在 `#if DEBUG && targetEnvironment(simulator)` 里，不会进正式包。

---

## 一、发版前必须先改的内容：新手入门里的「我的」页截图

新手入门第一篇（`guide-app-tour`）配图 `guide-tab-profile` 还是旧界面：图上有「重看新手导览」、没有「买卖点口径」一行。不改的话，用户看到的介绍和实际界面对不上。

文件（中英各一张，900 px 宽，JPG）：
- `ios/DeepAlphaChan/Resources/Assets.xcassets/Guide/guide-tab-profile.imageset/guide-tab-profile.jpg`（中文界面）
- `ios/DeepAlphaChan/Resources/Assets.xcassets/Guide/guide-tab-profile-en.imageset/guide-tab-profile-en.jpg`（英文界面）

做法（用模拟器，登录凭证在 `~/.config/deepalpha/marketing.env` 的 `CHAN_DEMO_ACCOUNT` / `CHAN_DEMO_PASSWORD`，只通过环境变量传给 App，不要打印）：

```bash
SIM=<一台已启动的 iPhone 模拟器 UDID>   # xcrun simctl list devices booted
cd ios
xcodebuild -project DeepAlphaChan.xcodeproj -scheme DeepAlphaChan -destination "id=$SIM" -derivedDataPath /tmp/dd-chan -quiet build
xcrun simctl install $SIM /tmp/dd-chan/Build/Products/Debug-iphonesimulator/DeepAlphaChan.app
set -a; source ~/.config/deepalpha/marketing.env; set +a
xcrun simctl terminate $SIM club.deepalpha.chan 2>/dev/null
SIMCTL_CHILD_deepalphaDemoAccount="$CHAN_DEMO_ACCOUNT" SIMCTL_CHILD_deepalphaDemoPassword="$CHAN_DEMO_PASSWORD" \
  xcrun simctl launch $SIM club.deepalpha.chan -deepalphaDemo     # 英文图另加启动参数 -app_language_preference en；中文可加 -app_language_preference zh-Hans
# 点底部「我的」Tab（可用 /usr/local/bin/axe tap），截图：
xcrun simctl io $SIM screenshot /tmp/profile.png
```

把截图裁成与旧图相同的范围：从「语言」那一行到「账号与安全」那一行（含中间新增的「买卖点口径」和它下面的说明小字），左右贴着卡片边缘，然后缩放到宽 900 px、存成 JPG（质量约 85）：
`sips -c <高> <宽> --cropOffset <上> <左> /tmp/profile.png --out /tmp/crop.png && sips --resampleWidth 900 -s format jpeg -s formatOptions 85 /tmp/crop.png --out <目标文件>`（宽高按实际像素算）。

**验收**：打开两张新图确认：没有「重看新手导览」；「语言」下面是「买卖点口径 · 中等」一行；英文图全是英文。
提交：`fix(ios/chan): 新手入门「我的」页配图换成新界面`。

> 可选：`guide-tab-analysis` 配图拍的是旧图表（下面没有指标栏）。不影响理解，这版可以不换。

---

## 二、版本号、检查、打包上传

1. 工作区干净、在最新 master：`git status --short` 无输出，`git pull --ff-only`。
2. 改版本号（Debug / Release 两处都要改）：
   ```bash
   sed -i '' 's/MARKETING_VERSION = 1.2.1;/MARKETING_VERSION = 1.3;/; s/CURRENT_PROJECT_VERSION = 4;/CURRENT_PROJECT_VERSION = 5;/' ios/DeepAlphaChan.xcodeproj/project.pbxproj
   grep -n 'MARKETING_VERSION\|CURRENT_PROJECT_VERSION' ios/DeepAlphaChan.xcodeproj/project.pbxproj
   ```
   **验收**：DeepAlphaChan 目标的两处都是 `1.3` / `5`（文件里其它目标的版本号不要动）。提交：`chore(ios/chan): 版本号 1.3 (5)`，推到 master。
3. 发版前检查：
   ```bash
   uv run pytest tests/ios_content -q        # 学习内容 / 词典引用守护
   cd ios && xcodebuild -project DeepAlphaChan.xcodeproj -scheme DeepAlphaChan -destination 'generic/platform=iOS Simulator' -quiet build
   ```
   **验收**：测试全过；编译无 error。
4. 归档、导出 IPA（Release 配置；scheme 里的 StoreKit 测试配置只挂在 Run 上，archive 不受影响，**不需要**改 scheme）：
   ```bash
   cd ios
   asc xcode archive --project DeepAlphaChan.xcodeproj --scheme DeepAlphaChan --configuration Release \
     --archive-path ../.asc/artifacts/DeepAlphaChan-1.3-5.xcarchive --clean --overwrite \
     --xcodebuild-flag=-allowProvisioningUpdates
   asc xcode export --archive-path ../.asc/artifacts/DeepAlphaChan-1.3-5.xcarchive \
     --ipa-path ../.asc/artifacts/DeepAlphaChan-1.3-5.ipa --method app-store-connect --signing-style automatic \
     --team-id L565U2X5NL --overwrite --xcodebuild-flag=-allowProvisioningUpdates
   asc ipa-info --path ../.asc/artifacts/DeepAlphaChan-1.3-5.ipa   # 核对版本 1.3、构建号 5、Bundle ID
   ```
   如果签名失败（本机钥匙串没有分发证书 / Xcode 没登录账号）：**【人工】**用 Xcode → Product → Archive → Distribute App → App Store Connect → Upload，然后直接跳到第 6 步。
5. 上传：
   ```bash
   asc builds upload --app 6806500280 --ipa ../.asc/artifacts/DeepAlphaChan-1.3-5.ipa --wait
   ```
6. **验收**：`asc status --app 6806500280` 的 `builds.latest` 为 `1.3 / 5 / VALID`。记下 `builds.latest.id`（下面叫 `BUILD_ID`）。
   `.asc/` 是构建产物，不要提交（必要时加进 `.gitignore`）。

---

## 三、在 ASC 建 1.3 版本并填写

1. 建版本（沿用 1.2.1 的描述、关键词、截图等元数据）：
   ```bash
   asc versions create --app 6806500280 --version 1.3 --platform IOS --copy-metadata-from 1.2.1
   asc versions list --app 6806500280 --platform IOS     # 记下 1.3 的版本 ID（下面叫 VERSION_ID）
   ```
2. 关联构建：`asc versions attach-build --version-id VERSION_ID --build-id BUILD_ID`
3. 发布方式选手动：`asc versions update --version-id VERSION_ID --release-type MANUAL`
4. 「此版本新增内容」（两个语言都要填；当前版本配置了 `zh-Hans` 和 `en-US`）：
   ```bash
   asc localizations update --version VERSION_ID --locale zh-Hans --whats-new "$(cat <<'EOF'
   • 图表新增指标栏：均线、EMA、布林带（BOLL）点一下即可开关，周期可调；左上角显示指标数值，可折叠
   • 新增 30 分钟周期（会员）
   • 搜索支持按名称联想，A 股、港股可直接输入中文名
   • 雷达示例日也能查看基本面名单
   • 买卖点口径移到「我的」页，切换更方便
   • 修复：手指放在图表上无法上下滚动页面、在图表上横向拖动会退回上一页、MACD 与 K 线错位、行业横条偶尔一直显示「数据准备中」
   EOF
   )"
   asc localizations update --version VERSION_ID --locale en-US --whats-new "$(cat <<'EOF'
   • New indicator bar under the chart: tap to show MA, EMA or Bollinger Bands (BOLL), with adjustable periods; values appear at the top left and can be collapsed
   • New 30-minute timeframe (membership)
   • Search now suggests matches by company name, including Chinese names for A-shares and Hong Kong stocks
   • The fundamentals list is now available on the radar's sample day
   • Signal rules moved to the Profile page for quicker switching
   • Fixes: page could not scroll when your finger started on the chart; dragging the chart sideways could go back to the previous screen; MACD drifting out of line with candles; the industry strip sometimes stuck on "Preparing data"
   EOF
   )"
   ```
   **验收**：`asc localizations list --version VERSION_ID --output table` 两行的 Whats New 都是新文案。
5. 描述、关键词、副标题、截图：**不用动**（自动沿用）。截图里的界面没有因本版改错，换不换都能过审。
6. App 隐私、年龄分级、出口合规：**不用改**（没有新增收集的数据；搜索联想只把输入的代码 / 名称发给我们自己的服务器查行情，与原有查询同类）。
7. 登录信息沿用：`appreview@deepalpha.club` / `AppReview2026`。

---

## 四、审核备注（整段替换）

在 1.2 那份的基础上改了三处：第 2 条换成 1.3 的新内容；口径设置的路径改为 Profile -> Signal rules；第 6 条写明 30 分钟周期是会员功能、示例日可看名单。

```bash
asc review details-for-version --version-id VERSION_ID     # 取 DETAIL_ID；没有就用 details-create 建（联系人沿用 1.2.1）
asc review details-update --id DETAIL_ID --notes "$(cat ios/AppStore/chan/review-notes-1.3.txt)"
```

先把下面这段原样存为 `ios/AppStore/chan/review-notes-1.3.txt`（约 3830 字符，上限 4000），再执行上面的命令：

```
1. DEMO ACCOUNT
Email: appreview@deepalpha.club / Password: AppReview2026
Use the "Email" tab. Lessons are also viewable without an account ("Browse the Chan primer").

2. WHAT'S NEW IN 1.3 AND WHERE TO FIND IT
- Analysis tab (opens by default): AAPL is pre-filled; tap Analyze. Below the chart is a new indicator bar: tap MA, EMA or BOLL to show or hide them (all off by default); the slider button adjusts periods. Values appear at the top left and can be collapsed.
- Search box: typing a company name shows matching tickers (Chinese names work for A-shares and Hong Kong stocks).
- 30-minute timeframe in the analysis conditions: membership feature (sample stocks NVDA / 600519 / 0700 are free).
- Profile -> Signal rules (moved from Profile -> Preferences): strict / medium / loose.
- Radar tab: on the sample day (marked "Sample"), non-subscribers can now open the fundamentals list (the "List" button at the bottom left of the radar).
- Fixes: page scrolling over the chart, accidental "back" when dragging the chart, MACD alignment.

3. NATURE OF CONTENT
This is a technical-analysis and education app about Chan theory. It is not an investment advisory service and does not recommend securities, issue trade instructions or promise returns. "Buy 1/2/3" and "Sell 1/2/3" are Chan theory's standard names for chart-structure positions, not trade recommendations. MA, EMA and Bollinger Bands are standard chart indicators shown for reference only. The radar does not score or rank stocks; the fundamentals threshold only narrows which stocks are shown. Letter grades describe reported financial data relative to industry peers and make no forecast. Disclaimers are shown on the sign-in screen, the Radar screen, the analysis result screen, the Fundamentals section and in Profile -> About.

4. AI-GENERATED CONTENT
The report summary is generated by a large language model only from the text of the public report. It is labeled "AI summary", states that it may contain errors and that the original report prevails, and is filtered to exclude buy/sell wording. Only public report text is sent to the model; no personal data.

5. THIRD-PARTY DOCUMENTS
Company reports are public regulatory filings (SEC EDGAR for US; exchange announcements for China A-share and Hong Kong). A-share analyst rating rows can open the publicly posted research report for reading; these broker reports can be read in the app but cannot be saved or shared from it. US/HK rating rows link to the related public news article, opened in an in-app viewer restricted to that website (other links open in Safari).

6. SUBSCRIPTION
One auto-renewing monthly subscription, club.deepalpha.chan.pro.monthly ("DeepAlpha Membership", 128 CNY/month in China). Eligible first-time subscribers get an introductory price of 58 CNY for the first month; there is no free trial. It includes unlimited analysis (free: 3 distinct tickers per day), the sub-level view and the 30-minute timeframe, the daily radar with 30 trading days of history, the fundamentals list (free users: sample day only), and an unlimited watchlist. Paywall: "Subscribe" in the quota bar on the Analysis tab, or Profile -> Subscription -> View Plans. It shows the price, the intro offer with the renewal price, the auto-renewal disclosure, Terms and Privacy links, Restore Purchases and Redeem offer code. A sandbox account can purchase and restore.

7. PERMISSIONS AND DATA
- Photos: add-only, requested only when the user taps "Save to Photos" in the share preview.
- No notification permission. No location, contacts, camera, microphone or ad tracking (SKAdNetwork only, no IDFA).

8. ACCOUNT DELETION
Profile -> Account & Security -> Delete account (with confirmation); permanently deletes the account and its data.

Network access is required; market data comes from public market-data APIs.
```

**验收**：`wc -m ios/AppStore/chan/review-notes-1.3.txt` 小于 4000；`asc review details-get --id DETAIL_ID` 的 notes 是新文本。
订阅商品这版**不用改**，不要把订阅项加进审核提交。

---

## 五、提交前自查

命令行能做的：
```bash
asc validate --app 6806500280 --version 1.3      # 不能有 blocker
```

**【人工】**用 TestFlight 装 1.3 (5)，真机逐项确认（iOS 18 以上的设备，有 iOS 26 的更好）：
- [ ] 分析页：AAPL 分析后图表下方有「均线 / EMA / BOLL」，默认都不亮；点亮后图上出线、左上角出数值；点数值能折叠 / 展开
- [ ] 指标设置面板：矮面板，−/+ 改周期后点「完成」，图上的线跟着变；「恢复默认」有效
- [ ] 手指放在 K 线上、MACD 上分别上下拖，页面能滚动；左右拖平移图表，**不会退回上一页**；双指缩放、点按十字光标正常
- [ ] 全屏按钮在图表右上角，进全屏横屏、退出后回到竖屏
- [ ] 搜索框输入「腾讯」「茅台」「apple」都有联想，点联想项能分析
- [ ] 30 分钟：免费账号对非示例股选 30 分钟弹付费墙；示例股（NVDA / 600519 / 0700）免费可看；会员都能看
- [ ] 「我的」页：语言下面是「买卖点口径」，点进去三选一，返回后右侧名称跟着变；没有「重看新手导览」；「偏好设置」里只剩「显示专业数值」
- [ ] 雷达（免费账号）：示例日左下角有「名单」，点开顶部写「示例日 … · 买卖点按这一天」；行业横条正常显示，点行业后名单只列该行业
- [ ] 学习 → 新手入门第一篇，「我的」页配图是新界面
- [ ] 英文系统走一遍上面几项，界面没有中文夹杂
- [ ] 回归：订阅页价格（首月 ¥58 / 划线 ¥128）、购买、恢复购买、兑换优惠码入口

---

## 六、提交与发布

1. 提交审核：
   ```bash
   asc review submit --app 6806500280 --version 1.3 --build-id BUILD_ID --confirm
   asc status --app 6806500280      # review.state 为 WAITING_FOR_REVIEW
   ```
2. **【人工】**过审后（手动发布）：自己装一遍确认，再 `asc versions release --version-id VERSION_ID --confirm`，或在 ASC 网页点「发布此版本」。
   分阶段发布：功能版本建议开（`asc versions phased-release create --version-id VERSION_ID`，在发布前设置）；想直接全量就不建。
3. 发布后把本文件的「执行记录」补全并提交。

被拒时的话术见 `review-notes.md` 末尾和 `RELEASE.md`「如果被拒」。本版可能多一个问题：技术指标（MA / EMA / BOLL）会不会被当成投资建议——回复要点：标准图表指标，只显示数值、不给任何操作提示，默认关闭，免责声明常驻。

---

## 执行记录

| 日期 | 事项 | 结果 |
|------|------|------|
| 2026-10-09 | 换新手入门「我的」页配图 | 中英 900 px JPG 已目视验收；提交 `08701872` |
| 2026-10-09 | 版本号 1.3 (5) 提交 | Debug / Release 均已更新，提交 `4d5f6601`，已推送 master |
| 2026-10-09 | 发版前检查 | `tests/ios_content`：6 passed；iOS Simulator 编译通过（存在原有未使用变量警告）。额外 `make typecheck`：236 errors / 13 warnings，均在未改动的后端代码，日志 `/tmp/chan-1.3-typecheck.log` |
| 2026-10-09 | 正式归档 / 导出 | Release 归档与导出成功；IPA 核对为 1.3 (5)、club.deepalpha.chan、L565U2X5NL，产物在 `.asc/artifacts/` |
| 2026-10-10 | 上传构建 | 构建 ID：`e8ec5e74-9427-454d-943a-da968c71a3ec`；版本 1.3 (5)，状态 `VALID` |
| 2026-10-10 | 建版本 / 关联构建 / 填文案 / 审核备注 | 版本 ID：`62569786-341f-4840-8eb1-0d293d675e1e`；中英 Whats New 已更新；审核详情 ID：`a8366020-1d94-4cdd-9f5e-d0da11d6dbe5`，备注 3834 字符 |
| 2026-10-10 | 提交审核 | 提交 ID：`04aea3c1-05d4-4a76-81a1-5393abc87bbd`；版本与审核状态均为 `WAITING_FOR_REVIEW` |
| | 过审 / 发布 | |
