# 缠论 App 1.2.1 发版操作清单（2026-10-08）

线上：**1.2 (3)**，`READY_FOR_DISTRIBUTION`，分阶段发布中。本次提交：**1.2.1 (4)**。
按顺序做，每一步都写了**验收标准**。上一版的完整清单见 `RELEASE-1.2.md`；这版改动很小，元数据大部分沿用。

---

## 本版内容

1.2 构建（`be1d0eaf`）之后，iOS 只有一处改动（`8e31dec1`，已合入 master）：

| 变化 | 位置 |
|------|------|
| 新增「兑换优惠码」 | 「我的 → 订阅」列表；付费墙底部小字一行（恢复购买 · **兑换优惠码** · 服务条款 · 隐私政策） |

点击后调起苹果**系统**的优惠码兑换面板（StoreKit `offerCodeRedemption`）。码在 App Store Connect 里生成（见第四节）。
兑换成功就是会员商品 `club.deepalpha.chan.pro.monthly` 的正常订阅权益，门禁逻辑不变。
**不自建兑换码**：审核指南 3.1.1 不允许 App 用自己的码解锁功能。

> 不升级也能先用：Apple 的优惠码不依赖 App 内入口。用户可以打开兑换链接
> `https://apps.apple.com/redeem?ctx=offercodes&id=6806500280&code=优惠码`，
> 也可以在 App Store →右上角头像→「兑换充值卡或代码」里输入。1.2.1 只是把入口放进 App 里，用户更容易找到。

---

## 一、版本号与打包

1. 在 master 上递增版本号（`ios/DeepAlphaChan.xcodeproj/project.pbxproj`，Debug / Release 两处都改）：
   `MARKETING_VERSION = 1.2.1`，`CURRENT_PROJECT_VERSION = 4`。提交：`chore(ios/chan): 版本号 1.2.1 (4)`。
2. Xcode → scheme DeepAlphaChan → Edit Scheme → Run → Options → **StoreKit Configuration 设为 None**
   （否则包里会带本地测试配置，线上读不到真实商品）。
3. Any iOS Device → Product → Archive → Distribute App → App Store Connect → Upload。
4. 归档完成后把 scheme 的 StoreKit Configuration 改回来，别把这个改动提交上去。

**验收**：5–15 分钟后执行 `asc status --app 6806500280`，`builds.latest` 显示 `1.2.1 / 4 / VALID`。

---

## 二、在 ASC 新建 1.2.1 版本

ASC → App → 左侧「iOS App」旁的 **＋** → 版本号填 `1.2.1`。

| 字段 | 填什么 |
|------|--------|
| 截图 / 描述 / 关键词 / 副标题 | **不用动**，自动沿用 1.2 |
| 此版本新增内容（中文） | `新增「兑换优惠码」：在「我的 → 订阅」或订阅页底部输入 App Store 优惠码，即可兑换会员。` |
| 此版本新增内容（英文） | `New: Redeem offer codes. Enter an App Store offer code in Profile → Subscription or at the bottom of the subscription screen to unlock membership.` |
| 构建版本 | 选 **1.2.1 (4)** |
| 出口合规 | 不加密（`ITSAppUsesNonExemptEncryption=false`，一般不会再问） |
| 登录信息 | 沿用：`appreview@deepalpha.club` / `AppReview2026` |
| 发布方式 | **手动发布**（和 1.2 一致；想过审即上线就选「自动发布」） |

**App 隐私、年龄分级**：不用改（没有新增收集的数据，兑换由系统完成）。

---

## 三、审核备注

沿用 1.2 那段（`RELEASE-1.2.md` 第四节），**在第 2 条「WHAT'S NEW」开头加一行**：

```
- NEW IN 1.2.1: "Redeem offer code" in Profile -> Subscription and at the bottom of the paywall. It opens Apple's system offer-code redemption sheet (StoreKit); codes are App Store subscription offer codes created in App Store Connect for club.deepalpha.chan.pro.monthly. No custom code or unlock mechanism is used.
```

加完总长度要在 4000 字符以内（1.2 那段约 3800，超了就把第 7 条 PERMISSIONS 缩短）。

订阅商品这版**不用改**，所以不用把订阅项加进审核提交。

---

## 四、生成优惠码（可以和送审并行，1.2 线上就能用）

ASC → App →「订阅」→ 群组「DeepAlpha Pro」→ `Pro Monthly` → **优惠代码（Offer Codes）** → 创建：

| 设置 | 选择 |
|------|------|
| 参考名称 | 自己认得出就行，如「2026-10 内测赠送 1 个月」 |
| 客户资格 | 新订阅者；需要的话也勾「现有 / 过期订阅者」 |
| 优惠类型 | **免费** · 时长 **1 个月** |
| 地区 | 全部（或只中国大陆） |

然后在这个优惠下生成码，两种任选：

| 类型 | 用法 | 适合 |
|------|------|------|
| 一次性代码 | 填数量，生成后下载 CSV，**一个码只能用一次** | 一人发一个（内测用户、合作方） |
| 自定义代码 | 自己起名（如 `CHAN2026`），设兑换次数上限和有效期，多人共用 | 公众号 / 社群公开发 |

规则（Apple 定的，改不了）：
- 同一个 Apple 账户对同一个优惠只能兑换一次。
- 1 个月免费期结束后按正价（¥128/月）**自动续订**，除非用户至少提前 24 小时取消。发码时提醒对方。
- 一次性代码生成后通常要等一会儿（可能几小时）才能用。
- 每个 App 每季度有生成数量上限，以 ASC 页面显示为准。

**验收**：用一个没订阅过的沙盒 / 真实账号打开 `https://apps.apple.com/redeem?ctx=offercodes&id=6806500280&code=你的码`，能兑换，回到 App 后显示「会员」。

---

## 五、提交前真机自查（TestFlight 的 1.2.1 (4)）

- [ ] 「我的 → 订阅」有「兑换优惠码」，点开是系统兑换面板；取消后回到原页面，不崩溃
- [ ] 付费墙底部一行显示「恢复购买 · 兑换优惠码 · 服务条款 · 隐私政策」，小屏机型上不换行错位
- [ ] 用一个优惠码兑换：面板关闭后立刻变成会员，付费墙自动关闭；雷达、次级别、基本面名单解锁
  （TestFlight 不支持兑换真实优惠码；兑换要等上线后用真实账号测，测试时只确认面板能打开）
- [ ] 英文系统下显示 "Redeem offer code"
- [ ] 回归：付费墙价格（首月 ¥58 / 划线 ¥128）、购买、恢复购买仍正常

---

## 六、提交与发布

1. 1.2.1 版本页 → 「添加以供审核」→ 提交。命令行查看状态：`asc status --app 6806500280`（`review.state`）。
2. 过审后（手动发布时）点「发布此版本」。1.2 的分阶段发布会在 1.2.1 上线时自动结束；1.2.1 是否也分阶段发布，在版本页「分阶段发布」里选。
   修复类小版本建议**不分阶段**，直接全量推送。
3. 上线后用真实账号兑换一个码，走一遍完整流程（第四节的验收）。
4. 回到本文件，记录构建 ID、提交 ID、上线日期。

---

## 执行记录

| 日期 | 事项 | 结果 |
|------|------|------|
| 2026-10-08 | 上传构建 1.2.1 (4) | VALID；构建 ID：`5ce57689-1a0c-4ba3-967c-20e164b602b4`；已绑定版本 `082c5fe5-9e2b-4d78-95f4-47a7ceeeccff` |
| 2026-10-08 | 提交审核 | 已提交；提交 ID：`07d0513b-4cf7-4bed-8407-f7f494c789b2`；状态：`WAITING_FOR_REVIEW` |
| | 过审 / 发布 | |
| | 线上兑换实测 | |
