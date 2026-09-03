# 审核备注（App Review Information → Notes）

把下面「可直接粘贴的备注正文」里的**英文版**填进 ASC 的备注框
（字段上限 4000 字符，中英都贴会超）。

备注框的位置：**版本页（如「1.1 准备提交」）拉到最底部的「App 审核信息」区块**。
左侧菜单里的「App 审核」是提交记录与 Apple 的消息往来，没有输入框，别找错。

---

## 演示账号（Sign-in required 处填写）

| 字段        | 值                          |
| --------- | -------------------------- |
| User Name | `appreview@deepalpha.club` |
| Password  | `AppReview2026`            |

已在生产环境创建并验证：可正常登录，美股 / A 股 / 港股三个市场均能返回真实
分析结果。**该账号仅供审核使用，上架后可随时删除。**

> 登录方式选「邮箱」页签，输入上面的邮箱与密码即可。
> 也可以不登录，点登录页的「先看看缠论入门」直接浏览全部教程内容。

---

## 可直接粘贴的备注正文

> ⚠️ **ASC「备注」字段上限 4000 字符**，中英两版合计 4508 字，一起贴会被
> 拒填（2026-09-03 踩过）。**只贴下面的英文版**（3302 字）——审核员统一看
> 英文，中文版重复一遍不会提高通过率，只会挤爆字数。中文版留档备查。
>
> 演示账号在「App 审核信息」里有独立的用户名/密码输入框，备注正文里那份
> 是给审核员对照用的，删掉也不影响。

### 英文版 —— 贴这段（3302 字符）

```
1. DEMO ACCOUNT
Email: appreview@deepalpha.club
Password: AppReview2026
Please switch to the "Email" tab on the sign-in screen.

2. QUICK WALKTHROUGH
- After signing in, the Analysis tab is pre-filled with AAPL. Tap "Analyse".
  You may also pick a market and enter 600519 (China A-share) or 0700 (HK).
- The result screen draws fractals, strokes, segments, pivots and buy/sell
  points on the chart, with a MACD subchart below. Tap the icon at the top
  right for fullscreen.
- The "Analysis" and "Signals" tabs below describe the detected structure.
- The Learn tab contains nine lessons, each with a diagram. Terms in the chart
  legend and on signal labels are tappable and open the matching lesson.
- Content is also viewable WITHOUT an account: tap "Browse the Chan primer"
  on the sign-in screen.

3. NATURE OF CONTENT (IMPORTANT)
This app is a candlestick technical-analysis tool and educational material on
Chan theory. It is not an investment advisory service. It does not recommend
securities, issue trade instructions, or promise returns.
Labels such as "Buy 1 / Buy 2 / Buy 3" are the standard terminology of Chan
theory for structural positions (first/second/third-class buy point). They name
a detected chart structure; they are not recommendations to trade.
The "Analysis" tab reports a technical read such as "firm / soft / balanced".
This is an objective description of structure that has already formed, derived
by weighting the last stroke, segment direction, position relative to the latest
pivot, divergence and volume; every contributing factor is listed so the reader
can check it. It describes the present state, makes no forecast, and contains no
action verbs.
A disclaimer is shown on the sign-in screen, on the analysis result screen, in
the signal list, and at the end of every lesson.

4. SUBSCRIPTION
Free users may analyse 3 distinct tickers per day. DeepAlpha Pro removes the
limit. The paywall includes the auto-renewal disclosure, links to Terms of Use
and Privacy Policy, and a Restore Purchases button.

5. ACCOUNT DELETION
"Profile" tab → "Delete Account", with a confirmation step. This permanently
deletes the account and associated data.

6. DATA SOURCES
Market data comes from public third-party market-data APIs. The app collects no
location, contacts or health data, does not read the photo library, and uses no
advertising tracking. Photo-library access is write-only and is used solely to
save an image the user explicitly generated — see section 7.

7. NEW IN THIS VERSION (1.1)
- Share analysis image: the share button at the top right of the result screen
  exports the whole analysis page as one tall image (with branding and a
  download QR code). Taking a screenshot inside the app opens the same share
  preview.
- Photo library permission (new in this version): "Save to Photos" in the
  preview requests write-only access (PHAccessLevel.addOnly). The app never
  reads, browses or uploads anything from the user's photo library, and the
  permission is never requested unless the user taps Save to Photos.
  Steps to reproduce: analyse any ticker -> share icon at top right ->
  Save to Photos.
- The MACD subchart now supports the same pan and pinch-to-zoom gestures as the
  main chart.
- Phone-number sign-up and sign-in (mainland China, +86).
```

### 中文版 —— 留档备查，不要贴

```
一、演示账号
邮箱：appreview@deepalpha.club
密码：AppReview2026
登录时请切换到「邮箱」页签。

二、如何快速体验核心功能
1. 登录后进入「分析」页，股票代码默认为 AAPL，直接点「分析」；
   也可选择市场后输入 A 股代码 600519 或港股代码 0700。
2. 分析完成后进入结果页：图表上会标出分型、笔、线段、中枢与买卖点，
   下方是 MACD 副图。点右上角图标可全屏查看。
3. 下方「形态分析」与「买卖点」两栏是结构识别结果的文字说明。
4. 「学习」页有 9 篇缠论入门词条，每篇配示意图。图例中的术语
   （笔 / 线段 / 中枢 / 顶分型 / 底分型）和买卖点标签均可点击，
   会弹出对应词条。
5. 无需登录也可查看教程：登录页点「先看看缠论入门」。

三、关于内容性质（重要）
本 App 是 K 线技术分析工具与缠论学习材料，不是投资顾问服务，
不提供个股推荐、买卖指令或收益承诺。
图表上标注的「一买 / 二买 / 三买」等是缠论理论中对走势结构位置的
固定命名（第一类买点 / 第二类买点 / 第三类买点），是结构识别结果的
标签，不是操作建议。
「形态分析」栏给出的「技术面偏强 / 偏弱 / 多空僵持」是对已发生结构的
客观描述，由末笔方向、线段方向、中枢位置、背驰、量价等因子加权得出，
每一项依据都逐条列出供核对；它描述现状，不预测涨跌，也不含操作动词。
免责声明在登录页、分析结果页、买卖点列表和每篇教程末尾均有展示。

四、订阅说明
免费用户每日可分析 3 支不同标的。DeepAlpha Pro 解除次数限制。
付费墙内已包含自动续订说明、服务条款与隐私政策链接、恢复购买按钮。

五、账号删除
「我的」页底部有「删除账号」入口，二次确认后永久删除账号及关联数据。

六、数据来源
行情数据来自公开的第三方行情接口。App 不采集位置、通讯录或健康数据，
不读取相册，不使用广告追踪。相册权限仅用于把用户主动生成的分析图
写入相册（add-only），详见第七节。

七、本版新增（1.1）
1. 分享分析图：结果页右上角的分享按钮会把整页分析导出为一张长图
   （含品牌与下载二维码）；在 App 内截屏也会自动弹出同一个分享预览。
2. 相册权限（本版新增）：预览页的「保存到相册」会申请相册写入权限
   （PHAccessLevel.addOnly，只写不读）。App 不读取、不浏览、不上传
   用户相册中的任何内容；不点「保存到相册」就完全不会触发该权限。
   复现路径：分析任意标的 → 结果页右上角分享按钮 → 保存到相册。
3. MACD 副图现在与主图一样支持左右平移与双指缩放。
4. 新增手机号注册与登录（中国大陆 +86）。
```

---

## 如果被拒，最可能的三个理由与应对

**1. Guideline 3.1.1 / 5.2.5 — 被当成投资顾问或荐股**

这是金融类 App 最常见的拒因。应对：强调上面备注第三条——「一买/二买/三买」
是缠论理论的固定术语（对应 first/second/third-class buy point），命名的是
走势结构位置，不是操作指令；App 内四处都有免责声明。
必要时可截图说明免责声明的展示位置。

**2. Guideline 2.1 — 审核员登录不进去**

先自行验证账号仍可用（见下方命令），再回复。也可提示审核员用
「先看看缠论入门」免登录浏览。

```bash
curl -s -X POST https://api.deepalpha.club/api/v1/auth/login/account \
  -H 'Content-Type: application/json' \
  -d '{"account":"appreview@deepalpha.club","password":"AppReview2026"}'
```

**3. Guideline 3.1.2 — 订阅信息展示不全 ← 2026-08-31 实际被拒于此**

付费墙内的自动续订说明、条款/隐私链接、恢复购买一直都有，
但 **App Store 商品页描述**里少了 EULA 链接，被自动检测打回。
修复见 `store-listing.md` 第八节与 `SUBMIT.md` 顶部的红色区块，
回复话术见下。

---

## EULA 被拒的回复话术（2026-08-31，可直接粘贴到 App Review 消息框）

```
Hello,

Thank you for the review.

We have updated the App Description metadata for both localizations
(Simplified Chinese and English) to include a link to the Terms of Use (EULA).
We are using the standard Apple Terms of Use, and the description now ends with:

Terms of Use (EULA):
https://www.apple.com/legal/internet-services/itunes/dev/stdeula/
Privacy Policy: https://deepalpha.club/privacy

The License Agreement in App Store Connect remains the standard Apple EULA.

In the same update we expanded the subscription disclosure in the description
to state the subscription length (1 month), the 7-day free trial, that payment
is charged to the Apple Account at confirmation of purchase, the 24-hour
auto-renewal rule, and how to turn off auto-renew in App Store account settings.

For reference, the in-app paywall already contains the auto-renewal disclosure,
the Terms of Use and Privacy Policy links, and a Restore Purchases button. It
can be reached after signing in with the demo account
(appreview@deepalpha.club / AppReview2026) via the crown icon at the top right
of the Analysis tab, or via Profile -> Upgrade to Pro.

No binary change was required, so the build is unchanged. Please let us know if
anything further is needed.

Best regards,
DeepAlpha
```

---

## 提交前必须自查（我无法代做的部分）

- [ ] 生产后端 `api.deepalpha.club` 正常（App 内置地址就是它）
- [ ] 内购产品在 ASC 里状态为「准备提交」，且已随本版本一起提交
- [ ] 真机沙盒账号完整走一遍：订阅购买 → 恢复购买
- [ ] 真机验证全屏图表转横屏后退出能正常回到竖屏

---

## 附：订阅项的审核备注（ASC → App 内购买项目 → 审核信息）

这段和上面的 App 审核备注是**两个地方**：这里填的是给审核「订阅项」的人看的。
本 App 必须登录才能进主界面，不给账号他连付费墙都打不开，所以演示账号要
在这里再给一遍——订阅项审核未必和 App 审核是同一个人、同一个界面。

可直接粘贴：

```
DeepAlpha Pro 是本 App 唯一的订阅项，按月自动续订，含 7 天免费试用。

【订阅权益】
免费用户每天可分析 3 支不同标的（同一标的当天重复分析不额外计次；
额度用尽后，当天已分析过的标的仍可继续查看）。订阅后解除该次数限制。
订阅不解锁任何额外的功能模块，仅解除次数限制。

【如何找到付费墙】
App 需要先登录。演示账号：
  appreview@deepalpha.club / AppReview2026
登录后两个入口任选其一：
  1) 「分析」标签页右上角的皇冠图标
  2) 「我的」标签页 →「升级 Pro」
付费墙内含：7 天免费试用说明、试用结束后的价格、自动续订披露、
服务条款与隐私政策链接、恢复购买按钮。

【测试提示】
使用沙盒 Apple 账号即可完成购买与「恢复购买」。
本 App 通过后端接口获取行情数据，请确保测试设备可正常联网。

---

DeepAlpha Pro is the only subscription in this app: auto-renewing monthly,
with a 7-day free trial.

WHAT IT UNLOCKS
Free users can analyse 3 distinct tickers per day (re-analysing a ticker
already used that day does not count again; once the quota is used up,
tickers already analysed that day remain viewable). The subscription removes
this limit. It does not unlock any additional feature modules.

HOW TO REACH THE PAYWALL
Sign-in is required. Demo account:
  appreview@deepalpha.club / AppReview2026
After signing in, either entry works:
  1) Crown icon at the top-right of the "Analysis" tab
  2) "Profile" tab -> "Upgrade to Pro"
The paywall shows the 7-day trial, the post-trial price, the auto-renewal
disclosure, Terms/Privacy links and a Restore Purchases button.

TESTING
A sandbox Apple ID is enough to complete purchase and Restore Purchases.
The app fetches market data from our backend, so the test device needs
network access.
```

**「订阅不解锁任何额外功能模块」这句要留着**：付费墙上「优先体验新功能」那条
容易让人以为订阅捆绑了尚未上线的功能，先划清边界省得来回问。
