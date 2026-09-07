# 发布回执（演示运行，用户明确要求跑通全流程真实发布，测试内容稍后由用户统一删除）

- run_id: 2026-09-06-claude-demo
- 媒体: https://api.deepalpha.club/api/v1/media/files/3a48ce5ea7d845daa289f20e8d8377e2e87ebee8.mp4（匿名 HEAD 200、GET 内容 sha256 与本地成片一致）

| 平台 | 频道 | postId | 真实状态 | 公开链接 |
| --- | --- | --- | --- | --- |
| YouTube | DeepAlpha | 6a9d97e56acbdfc9eda3d798 | sent（sentAt 2026-09-06T16:45:14.960Z） | https://www.youtube.com/watch?v=CNpakVuosg8 （privacy=private） |
| TikTok | littlemonkey437 | 6a9d985b5c2ba4d154180dba | sending（多次轮询仍未变为 sent，未生成公开链接；get_post 上仍残留一条早前失败尝试的旧 error 字段，可能只是显示未清空，也可能真的卡住） |

- 首次尝试(postId 同上)因 schedulingType=notification 触发"需要手机设备确认通知"报错，未发送；随后编辑为 schedulingType=automatic 重新提交，YouTube 已确认真实发布成功，TikTok 状态仍为 sending，未确认最终结果。
- 本次为用户明确口头授权的全流程真实发布测试（"今天发送的都是测试的,我会统一删除"），不是当日 09:00 的正式档期；未更新 latest-selection/production/publish 指针。
- 待办：TikTok 那条如果长时间停在 sending 或最终变成 error，需要用户在 Buffer/TikTok 后台确认实际情况；两条测试内容按用户说明会由用户自行删除。
