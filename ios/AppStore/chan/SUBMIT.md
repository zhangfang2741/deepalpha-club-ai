# 缠论 App 上架操作清单

**先读这页。** 代码侧我已全部处理完并验证过；下面是只能由你操作的部分，
按顺序做，每步都有验收标准。

预计耗时：首次约 1.5–2 小时（大头在 ASC 表单填写与内购配置）。

---

## 🔴 当前状态：被拒（2026-08-31）— 只需改元数据，5 分钟

Apple 拒因：卖自动续订订阅，但商品页描述里没有使用条款（EULA）链接。
**不涉及代码，不用重新 Archive、不用重传构建版本。**

按顺序做这三步：

1. **ASC → 你的 App → 1.0 版本页 → 「描述」**，把 `store-listing.md`
   第三节（中文）和第四节（英文）的描述**整段重新粘贴一遍**——已在末尾
   加了 EULA + 隐私政策链接和完整的自动续订披露。
   **中英两个语言版本都要改**，只改一个会被再拒一次。

2. **确认许可协议用的是 Apple 标准 EULA**：ASC →「App 信息」→ 拉到
   「许可协议」（License Agreement），保持 **Apple 标准 EULA**（默认值，
   不要上传自定义协议）。我们描述里给的就是这份标准协议的官方链接。

3. **回复审核 + 重新提交**：在 App Review 消息里回复
   `review-notes.md` 末尾「EULA 被拒的回复话术」那段英文，然后点
   「提交以供审核」。

**验收**：商品页预览的描述末尾能看到这两行——

```
使用条款（EULA）：https://www.apple.com/legal/internet-services/itunes/dev/stdeula/
隐私政策：https://deepalpha.club/privacy
```

> 元数据被拒（Metadata Rejected）状态下重新提交，通常几小时内复审完毕，
> 比首审快很多。

下面是首次提交时的完整清单，已完成的部分保留供复查。

---

## 我已经做完的（不用再管）

| 项目 | 状态 |
|------|------|
| 隐私清单 `PrivacyInfo.xcprivacy` | 已创建并验证进归档包 |
| 后端地址改为 `api.deepalpha.club` | 已改（原来是 Railway 临时域名，会变） |
| ATS 明文例外 | 已移除，全站强制 HTTPS |
| StoreKit 测试配置混入发布包 | 已排除 |
| VoiceOver 标签 | 已补 4 处纯图标按钮 |
| 免登录浏览教程入口 | 已加（降低 5.1.1 拒因） |
| 动态字体 | 结论区已支持缩放 |
| 付费墙宣传已删除的 GAP 功能 | **已修**，改为「美股/A股/港股」 |
| 设备族改为仅 iPhone | 已改，因此不需要 iPad 截图 |
| 6.9 英寸截图 ×6（真实数据） | 改版后已全部重截；**上传带标题版** `screenshots-6.9-captioned/` |
| 审核演示账号 | 已在生产创建并验证 |
| Archive 归档 | 已验证 `ARCHIVE SUCCEEDED`（形态分析改版后重验过） |
| 四处免责声明 | 登录页 / 结果页 / 买卖点列表 / 教程末尾，均常驻可见（风险提示折叠卡不算这一项） |
| 上架文案（中英） | 见 `store-listing.md` |
| 审核备注（中英） | 见 `review-notes.md` |
| ASC 表单逐项答案 | 见 `asc-form-answers.md` |

---

## 第 0 步：截图 ✅ 已完成

「形态分析」改版后已用 iPhone 17 Pro Max 模拟器（1320×2868，6.9 英寸标准尺寸）
全部重截，真实数据、状态栏统一为 9:41 / 满电 / 满信号。

**上传 `screenshots-6.9-captioned/` 里的 6 张**（带标题版），不是 `screenshots-6.9/`
里的原图。前者是后者加了标题文案后的成品，顺序见 `store-listing.md` 第七节。

重跑截图的工具链（都在本目录）：

```bash
# 1. 起模拟器、锁状态栏、装 App
xcrun simctl boot "iPhone 17 Pro Max"
xcrun simctl status_bar "iPhone 17 Pro Max" override \
  --time "09:41" --batteryState charged --batteryLevel 100 --cellularBars 4 --wifiBars 3

# 2. 按归一化坐标点击 / 输入（Simulator 不吃 AppleScript 合成点击，故走 Quartz）
uv run --with pyobjc-framework-Quartz --no-project python ios/AppStore/chan/simtap.py tap 0.5 0.33
uv run --with pyobjc-framework-Quartz --no-project python ios/AppStore/chan/simtap.py type 0700

# 3. 截图存到 screenshots-6.9/，再加标题
xcrun simctl io "iPhone 17 Pro Max" screenshot ios/AppStore/chan/screenshots-6.9/01_analysis_us.png
uv run --with pillow --no-project python ios/AppStore/chan/make_captioned.py
```

⚠️ 截 `05_query` 要在**没有分析历史**时截：空状态只在无历史时显示
AAPL/NVDA/TSLA 起步示例，跑过分析后会变成「最近分析过」。先
`xcrun simctl uninstall "iPhone 17 Pro Max" club.deepalpha.chan` 再装。

---

## 第 1 步：配置内购订阅（如果还没配）

ASC → 你的 App → 「App 内购买项目」→ 创建自动续订订阅。

**产品 ID 必须与代码完全一致**（已从代码中查出）：

```
club.deepalpha.chan.pro.monthly
```

本地 StoreKit 测试配置里的参数，ASC 里按同样口径配：

| 项 | 值 |
|----|-----|
| 产品 ID | `club.deepalpha.chan.pro.monthly` |
| 周期 | 1 个月（P1M） |
| 本地测试价 | ¥9.90（storefront 设为 CHN；ASC 里要挑一个真实存在的价格档位） |
| 免费试用 | 有（付费墙文案写的是「7 天免费试用」，ASC 里要配成 **7 天**，否则文案与实际不符会被拒） |

**各地区货币无需在代码里处理。** 付费墙显示的是 `product.displayPrice`，StoreKit 会按用户
账号所在 storefront 返回本地化的货币符号与格式（美区自动是 `$X.XX` + 英文 `%@/month`）。
ASC 里选定基准价后，Apple 会按它的定价档位表自动生成其余地区价格，可在「所有市场价格」里逐区覆盖。

`Configuration.storekit` 里的 `_storefront` / `displayPrice` **只对 Xcode 本地调试生效**，
真机、TestFlight、线上都不读它。要本地验证某个区的那一屏，临时改这两个字段即可（一次只能模拟一个区）。

- 填写订阅群组、显示名称、描述
- 上传审核截图（用付费墙那一屏，可真机截）
- **状态必须是「准备提交」**

⚠️ **新 App 的首个订阅必须勾选「与新 App 版本一起提交」**，
否则订阅不会进入审核，App 通过了但内购不可用。

**验收**：订阅项状态显示「准备提交」，且在版本页的「App 内购买项目」区块里能看到它。

---

## 第 2 步：真机验证两条我测不了的链路

用 Xcode 连真机跑一遍（scheme 已配好 StoreKit 本地测试）：

1. **订阅购买 + 恢复购买**
   沙盒账号购买 → 确认解除次数限制 → 删除重装 → 点「恢复购买」能恢复
2. **全屏图表方向**
   分析任意标的 → 点全屏 → 转横屏 → 退出 → **确认回到竖屏**，
   且登录页等其它页面转不动

⚠️ 第 2 条如果失败，App 会卡在横屏，只能杀进程——这是必须验的。

---

## 第 3 步：上传构建版本

Xcode → Product → Archive（我已验证过能成功）→ Distribute App →
App Store Connect → Upload。

上传后等 5–15 分钟处理完成，ASC 的「构建版本」里才会出现 1.0 (1)。

**验收**：ASC 版本页能选到构建版本 1.0 (1)。

> 若 Apple 邮件提示缺少 export compliance，按 `asc-form-answers.md`
> 第二节回答（选「豁免」）。

---

## 第 4 步：填写 App 信息与版本信息

按 `store-listing.md` 填名称、副标题、关键词、描述、更新说明、推广文本
（中英两个语言各填一次）。

截图按 `store-listing.md` 第七节的顺序上传 `screenshots-6.9/` 里的 6 张。

**验收**：预览里前两张是分析结果与全屏大图。

---

## 第 5 步：填写隐私与合规问卷

按 `asc-form-answers.md` 逐项填：

- 隐私营养标签：只勾邮箱、电话号码、姓名、用户 ID 四项
- 出口合规：豁免
- 年龄分级：预期 4+
- 内容版权：否

⚠️ 隐私问卷**必须与 `PrivacyInfo.xcprivacy` 一致**，不一致会被打回。

**验收**：提交前在浏览器打开 `https://deepalpha.club/privacy` 确认能访问
（审核员一定会点，404 必被拒）。

---

## 第 6 步：填写审核备注并提交

把 `review-notes.md` 里「可直接粘贴的备注正文」整段贴进
App Review Information → Notes。

演示账号：
```
appreview@deepalpha.club
AppReview2026
```

勾选「登录required」并填入上述账号。

发布方式建议选「**手动发布**」——通过后先自己验一遍再放出。

点「提交以供审核」。

---

## 如果被拒

`review-notes.md` 末尾列了最可能的三个拒因和应对话术。

金融类 App 最常见的是 **3.1.1 / 5.2.5 被当成投资顾问**。核心话术：
「一买/二买/三买」是缠论理论对走势结构位置的固定命名，是结构识别结果的
标签而非操作指令；App 内四处展示免责声明。

---

## 上架之后

1. **删除审核账号**（`appreview@deepalpha.club`）——用 App 内的删除账号
   功能，或直接在数据库删。它是个弱密码账号，留着是风险。
2. 关注 Railway 后端稳定性。App 内置地址是 `api.deepalpha.club`，
   后端挂了 App 就完全不可用。
3. `feat/chan-macd-lesson` 分支已无独有内容，可以删掉。
