# 缠论 1.2 发布执行记录

执行日期：2026 年 10 月 7 日；恢复记录：2026 年 10 月 8 日。当前尚未提交审核；审核通过后采用手动发布。

## 已完成

- 发布代码已经合入主干，最终构建来自 `be1d0eaf`，包含措辞、登录失效处理和本次新截图。
- 已核对 Railway 成功部署记录，发布功能已上线；隐私政策显示 2026 年 10 月 7 日，包含手机号和自选列表。
- 审核账号登录成功；美股、A 股、港股市场概览、三市场财报入口及美股示例雷达共七个接口均返回 HTTP 200，财报业务状态为 `ok`，雷达为 `ready`。
- 最新主干的 Release 归档和签名导出成功：`club.deepalpha.chan`、版本 `1.2`、构建 `3`、仅 iPhone。
- 独立发布目录的运行方案已关闭 StoreKit 测试配置，最终包不含 `.storekit` 文件，隐私清单包含全部六类数据。
- 安装包已上传，Apple 处理状态为 `VALID`，已绑定至 1.2 版本。构建 ID：`866963b9-df5b-4a39-8b52-373c2caef306`。
- 1.2 简体中文描述和更新说明已替换；保留原关键词与副标题。
- 描述中的“不打分、不排名”改为准确说明基本面评分和分位，避免与实际截图不符。
- App 审核备注与订阅审核备注均已替换；审核登录信息仍为必填。
- App 1.2 发布方式已设置为 `MANUAL`。
- 按用户指定的 `ios/AppStore/chan/screenshots-6.9-captioned/` 上传最新九张原图至“App 预览和截屏”。其他 iPhone 尺寸使用 Apple 自动缩放，移除旧 6.5 英寸独立截图覆盖。未修改“标题和搜索结果”素材。
- 现有商品 `club.deepalpha.chan.pro.monthly` 已创建新的待审元数据版本，中英文名称和权益描述已更新；未创建 premium 商品。
- 现有 133 个销售地区的常规价格已设置为 2026-10-08 生效，中国大陆为 ¥128/月，其他地区采用 Apple 等值价格。请求均启用保留现有用户价格；回读已确认中国旧价格记录为 preserved。

- 全部旧免费试用优惠已删除；133 个销售地区的新首月优惠已创建并回读：中国 ¥58、按期付费、一个月一期，2026-10-08 生效。

## 仍需完成

- [x] App 隐私标签已补充“其他用户内容”和“客户支持”，用途为 App 功能、关联身份、不用于追踪，并已发布；2026-10-08 回读 `published=true`，目标差异为空。
- [x] 已用用户提供的新版付费墙替换订阅审核截图；线上截图 ID `7d2e5ef0-fcde-4a38-95c9-eebd185017d5`，尺寸 1320×2868，状态 `COMPLETE`。截图显示首月 ¥58、之后 ¥128/月、无免费试用、恢复购买、条款和隐私链接。
- [x] TestFlight 真机验证：用户确认新客购买、恢复购买、老订阅者权益、转屏回归及清单中其余操作验证通过。
- [x] App 1.2 与本次订阅元数据版本已加入审核提交并提交成功；学习页版本也已加入。三市场页因 ASC 在 `items-add` 返回资源不存在而暂未加入，页面草稿仍保留。

## 当前阻塞

Apple 网页登录已完成，隐私申报和订阅审核截图均已发布。审核提交已完成，当前等待 Apple 审核；三市场自定义产品页仍为独立草稿。

## 恢复步骤

1. 等待 Apple 审核结果，保持 App 发布方式为 `MANUAL`。
2. 审核通过后手动发布 App 1.2。
3. 处理三市场自定义产品页的独立审核提交；当前版本 ID 为 `e5f680b9-0853-4835-9234-afbbe258d60f`，ASC `items-add` 暂报资源不存在。

## 2026-10-08 回读

- `asc validate --deep`：阻塞项 `0`；隐私发布、协议和地域可用性均通过。
- App 1.2：`PREPARE_FOR_SUBMISSION`，构建 `866963b9-df5b-4a39-8b52-373c2caef306` 为 `VALID`，审核详情已配置。
- 两个自定义产品页面版本仍为 `PREPARE_FOR_SUBMISSION`：学习页 `499206e9-737c-4048-b38f-4489aec7720c`，三市场页 `e5f680b9-085e-4835-9234-afbbe258d60f`。
- 非阻塞提示：订阅没有促销图片；医疗器械声明为非必需的 `PENDING_COLLECTION`，不影响当前提交准备。
- 订阅审核图检查：旧截图已删除并替换为用户提供的新版付费墙；原始 PNG 及无 alpha 的 JPEG 副本保存在 `ios/build/release-1.2-20261007/订阅审核/`。新图交付状态为 `COMPLETE`。
- TestFlight 真机验证：用户确认通过。
- 审核提交：ID `50b1782c-47a4-4635-abaf-97344a69c4da`，状态 `WAITING_FOR_REVIEW`，包含 App 1.2、订阅版本 `66b949a6-652f-49c8-bdff-a0e377530596`、学习页版本 `499206e9-737c-4048-b38f-4489aec7720c`。

## 资源标识

- App：`6806500280`
- App 1.2：`328ccfe0-14c6-48a9-966a-512660cac437`
- 中文本地化：`949c6899-9442-4137-a186-41f618cdebca`
- 订阅商品：`6806560223`
- 本次订阅元数据版本：`66b949a6-652f-49c8-bdff-a0e377530596`
- [App Store Connect](https://appstoreconnect.apple.com/apps/6806500280)
- [隐私申报](https://appstoreconnect.apple.com/apps/6806500280/appPrivacy)

## 本机交付物

归档、安装包及执行证据位于 `ios/build/release-1.2-20261007/`，此目录已被 Git 忽略。
独立发布目录为 `/Users/zhangfang/.codex/worktrees/chan-release-1-2/deepalpha-club-ai`，没有修改原工作区的应用代码。

## 新营销功能评估

用户明确：指定文件夹用于“App 预览和截屏”，新功能由代理决定。本次已创建两个自定义产品页面草稿，均使用指定文件夹原图，只调整截图顺序；未启动页面实验或设置标题素材。两个页面均为 `PREPARE_FOR_SUBMISSION`，尚未提交审核或上线。

| 页面 | 截图数与重点 | 已配置搜索词 |
| --- | --- | --- |
| 缠论入门与结构讲解 | 5 张，课程、结构释义优先 | 分型、笔、线段、中枢 |
| 美股 A股 港股结构分析 | 6 张，三市场、雷达、基本面与财报优先 | 美股、港股、A股 |

推广文案已保存。回读确认两页截图顺序、文件校验和及全部上传完成状态；文案与搜索词均核对通过。素材涉及 1.2 功能，安排与 1.2 同批送审。执行证据位于 `ios/build/release-1.2-20261007/custom-pages/`。

- 学习页 ID：`019290bf-6cdb-4400-a46c-6a35f7279e42`；待审版本：`499206e9-737c-4048-b38f-4489aec7720c`。
- 三市场页 ID：`a5620ab9-b25b-417a-9ae8-ce5e3f7ce7f1`；待审版本：`e5f680b9-085e-4835-9234-afbbe258d60f`。

- 标题和搜索结果：可以增加独立横版创意图，现有竖版截图不能直接使用；标题图支持 3840×1646 或通用图 5244×2950，创意展示适用于 iOS 27 / iPadOS 27 及以上。
- 素材库：集中复用截图、预览和独立创意素材，不是另一个投放渠道。
- 自定义产品页面：已配置上述两个草稿，用独立链接承接学习和市场研究两类需求；基本面与财报纳入三市场页。
- 产品页面优化：建议 1.2 上架后测试“缠论结构”与“三市场覆盖”谁作为第一张更有效。发布新版可能影响正在运行的实验，暂不启动。

参考：[素材管理](https://developer.apple.com/help/app-store-connect/manage-app-information/manage-your-app-store-assets)、[创意规格](https://developer.apple.com/help/app-store-connect/reference/app-information/creative-assets-specifications)、[自定义产品页面](https://developer.apple.com/app-store/custom-product-pages/)、[产品页面优化](https://developer.apple.com/help/app-store-connect/create-product-page-optimization-tests/overview-of-product-page-optimization/)。
