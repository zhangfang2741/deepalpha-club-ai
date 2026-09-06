# DeepAlpha 缠论运营记录

## 目标与授权

- 用户已明确授权：自主操作浏览器，接入其用于推广 APP 的小红书、TikTok、YouTube 账号；每天复盘数据、核验热点、制作并发布日常 APP 推广与学习内容。常规发布不需要每天重复确认。
- 发布前需从后台核实账号身份，身份不明确时询问用户，不能任意使用已登录的个人账号。
- 尚未授权任何付费投放或购买服务。扫码、手机验证等需要用户实际参与的步骤应在页面准备好后交接。
- 目标关注有效下载、注册、试用和付费，公开互动数据不能代替转化归因。

## 接入状态（2026-09-06）

- 小红书：尚未登录验证。Chrome 可列出标签页、创建空白页，但导航创作者后台反复超时；内置浏览器同样超时。尚未读到后台数据或发出任何内容。
- TikTok、YouTube：尚未验证账号与发布能力。官方接口限制已在当前对话核查，不能仅凭用户授权就宣称接口接通。
- 每日运营任务：已创建，上午 9 点；账号接入成功前仍须如实标记冷启动数据缺失。

## 执行流程

1. 核实运营账号并记录公开主页或账号标识，不保存密码、验证码或 Cookie 到仓库。
2. 读取可用的近 14 天数据，保存采集时间、统计口径、来源与缺失项。
3. 按同平台、同形式、相同发布后窗口比较表现，选择一个主推主题和一个实验变量。
4. 根据产品实际功能制作内容，校对文字、素材、日期、行动引导与落地链接。
5. 在已核实的运营账号发布，记录平台返回的作品链接和状态；遇到不确定结果先检查作品列表，避免重复提交。
6. 后续每日任务复盘 24/72 小时表现，每周调整内容组合。无法执行的环节要说明实际阻塞，不虚报完成。

## 冷启动首条候选

## 接入路线更新（2026-09-06）

- 用户已同意优先采用 Buffer 发布、YouTube 官方 Analytics API 深度复盘，再接 TikTok。
- Buffer 官方登录入口已在本任务内置浏览器打开并跳转至 auth.buffer.com；尚未登录、授权或核实频道。
- Buffer 支持 OAuth 连接 MCP；设置入口为头像 → Apps & Integrations → Integrations。具体连接参数以登录后的官方页面为准。
- 浏览器页面读取仍存在超时；本机 codex 命令行执行帮助命令异常退出，尚未添加 MCP 配置。
- 下一步：用户完成 Buffer 首次登录，检查是否已有 YouTube 频道连接；完成频道授权后验证频道列表与草稿创建。Google Analytics 授权另行接入，不把 Buffer 的实验性指标当作完整后台数据。
- 进展：用户已完成 Buffer 登录，浏览器标签显示 Home。使用桌面应用内置命令行成功添加全局 `buffer` MCP（https://mcp.buffer.com/mcp），OAuth 已启动并等待用户确认。尚未验证 OAuth 完成、工具可用或频道连接。旧的 /usr/local/bin/codex 异常，桌面应用内置版本可用。
- 最新验证：OAuth 命令已正常结束，返回 Successfully logged in，Buffer 授权成功。当前对话工具列表尚无 Buffer 工具，查询该 MCP 服务返回 unknown MCP server；需重新加载客户端连接后验证。无需重复 OAuth。尚未读取频道列表、创建草稿或发布内容。接下来读取 Buffer 已连接频道，优先接通 YouTube Shorts；若无频道则引导完成频道授权。
- 重新加载后验证成功：Buffer MCP 工具可用，get_account 和 list_channels 均成功返回。唯一工作区 My organization，organizationId 为 6a9cdfc735acc2085b560c49，时区 Asia/Singapore（UTC+8）；频道列表为空。当前真正阻塞为尚未在 Buffer 绑定 YouTube/TikTok。浏览器读取仍超时，MCP 数据读取正常。尚未创建频道发布草稿或公开作品。
- 最新进展（2026-09-06 11:55 UTC+8）：用户完成绑定后已验证两个频道正常、未锁定、队列未暂停，默认非提醒发布。YouTube DeepAlpha：channelId `6a9ce2eacd8b9c702c1543bf`，主页 https://www.youtube.com/channel/UC3T7V4k5jdOJJTzoa06iU6w 。TikTok littlemonkey437：channelId `6a9ce3f9cd8b9c702c154602`，主页 https://tiktok.com/@littlemonkey437 。以上为用户本次主动绑定的运营账号，常规推广发布已获授权。
- Buffer 帖子列表读到一条 2026-09-03 的 TikTok 历史内容，postId `6a9ce3fada9395a1c2a962fc`，文案「做了一个缠论自动画线和基础学习的App」。指标更新时间 2026-09-06T03:54:34.679Z：80 播放、3 赞、0 评论、0 分享、平均观看 1.73 秒，平台返回互动率 3.75%。只有一条样本，不作因果推断。未读到 YouTube 历史帖子不等于频道从未发布。
- 下一步先制作真实 APP 演示短视频，测试前 3 秒直接展示图层变化；素材与成片校验后发布。Buffer 创建内容需要可访问的媒体 URL；尚未配置素材托管。YouTube 官方 Analytics 和下载/注册归因尚未接通，Buffer 缺失指标不填零。
- 首条成片已完成，最终采用分型学习教学方案，详见 daily/2026-09-06.md。文件 assets/2026-09-06/chan-intro-20260906.mp4；18.88 秒，720×1280。待素材站公开访问后通过 Buffer 发到两个已绑定频道，使用合成内容标记并注明真实截图演示。
- 素材站独立目录 /Users/zhangfang/chan-media-site；project_id appgprj_6a9ce5790a908191a68213f76fce32aa；version_id appgprj_6a9ce5790a908191a68213f76fce32aa~appgver_fdd3b3e5d1a88191b3006db7b205522d；私有部署 appgdep_6a9ce6b05dfc8191a4ce51fd23abb82b。只含宣传视频与下载页面，不含运营数据或凭证。公开访问尚待确认，切勿将私有链接直接用于 Buffer。
- 私有部署已于 2026-09-06 12:08（UTC+8）成功，实际地址 https://deepalpha-chan-media.zfleo.chatgpt.site 。不要使用创建时的 expected_url。已向用户发出公开素材页的确认，尚未收到答复；收到同意后更新 Sites 访问并按技能发布已保存版本，验证匿名 MP4 请求返回 video/mp4 后再调用 Buffer，避免重复创建。

- 主题：第一次打开缠论图，先别把所有图层都打开。
- 形式：真实 APP 录屏或截图，逐步展示原始 K 线与结构图层开关。
- 重点：帮助新用户理解界面与学习入口，避免把结构标签讲成确定的交易预测。
- 待完成：核实当前上线界面、制作视觉素材、确认运营账号后发布。
