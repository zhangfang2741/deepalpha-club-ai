# 发布回执 · run 2026-09-07

- 日期：2026-09-07（北京时间），正式运营档期
- 成片：`teaching.mp4`，720×1280，H.264/AAC，39.20 秒，6,134,491 字节
- sha256：`91fa13ebddf1cc2674bb1ffe877710a1a74c4ffe7780409df6fa148683969869`
- 媒体 URL：https://api.deepalpha.club/api/v1/media/files/539b8c3a9c5141818aeeb8ba580f5870061a6c20.mp4
  - 匿名 HEAD 200，`content-type: video/mp4`
  - 匿名 GET 下载内容 sha256 与本地成片**完全一致**

## 两个频道均已确认发布成功

| 平台 | 频道 | postId | 真实状态 | 发布时间（北京） | 公开链接 |
| --- | --- | --- | --- | --- | --- |
| TikTok | littlemonkey437 | 6a9da23d9730c9bde54a5ff1 | **sent** | 2026-09-07 01:28:06 | https://tiktok.com/@littlemonkey437/video/7682474924597873941 |
| YouTube | DeepAlpha | 6a9da2536acbdfc9eda4d24f | **sent** | 2026-09-07 01:26:47 | https://www.youtube.com/watch?v=Ul7AOK553Ko |

两条均为 `schedulingType: automatic` + `mode: shareNow`，未触发 2026-09-06 遇到的 notification 报错。

- TikTok：提交后返回 sending，轮询约 105 秒后变为 sent 并返回公开链接，全程 `error: null`。已标记 `isAiGenerated: true`。
- YouTube：提交即返回 sent，发布为 **Short**，分类 Education（27），`privacy: public`，已标记 `isAiGenerated: true`、`madeForKids: false`。

### 关于 YouTube privacy

本次设为 **public**。理由：这是北京 2026-09-07 的正式运营档期，与当日其他正式帖一致；2026-09-06 那次用 private 是因为它是明确标注的测试运行。OPERATIONS.md 未写明必须 private，规范原文为"可设 private 降低早期风险"。如需改回 private 或 unlisted，告知即可调整。

## 复盘计划

| 窗口 | TikTok | YouTube |
| --- | --- | --- |
| 24 小时 | 2026-09-07T17:28:06Z（北京 09-08 01:28） | 2026-09-07T17:26:47Z（北京 09-08 01:27） |
| 72 小时 | 2026-09-09T17:28:06Z（北京 09-10 01:28） | 2026-09-09T17:26:47Z（北京 09-10 01:27） |

缺失指标（完播率、留存曲线、下载/注册归因）不填零，如实标注缺失。Buffer 指标按日刷新，可能滞后约 24 小时，采样时记录实际 `metricsUpdatedAt`。
