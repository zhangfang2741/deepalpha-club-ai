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
4. 形成热门标的候选池后逐个调用缠论分析，检查分型、笔、线段、中枢、背驰和买卖点；无清晰可讲结构的标的直接淘汰。
5. 对剩余标的按市场热度、结构清晰度、信号新鲜度、教学价值和画面可读性评分，选择主推标的与概念；不得因热门而硬用无信号标的。
6. 生成自动播放脚本，明确输入代码、点击分析、图层切换、缩放和停留时间；旁白分段必须与脚本步骤一一对应。
7. 根据脚本生成 MiniMax 中文旁白，执行模拟器录屏并按同一时间轴混音，校验音画同步后再上传和发布。
8. 后续每日任务复盘 24/72 小时表现，每周调整标的选择、教学主题和开头变量。无法执行的环节要说明实际阻塞，不虚报完成。

### 标的决策规则

- 市场热度只是候选池入口，不是最终选题理由。
- 必须有至少一个清晰、可在 App 中演示的结构信号；最新没有信号的代码不制作教学视频。
- 如果热门标的都没有清晰结构，改用常青概念或最近的历史案例，并明确说明原因。

### 自动播放脚本与发布闸门

- 脚本总时长控制在 20–45 秒，开头 0–3 秒必须已经显示真实 App 和主推代码；每一步固定记录 `step_id`、`time_sec`、`app_action`、`on_screen_text`、`narration_text`、`expected_visual`。
- `app_action` 必须能落到模拟器操作：启动/登录、输入代码、点击分析、显示或隐藏分型/笔/线段/中枢/背驰/买卖点、缩放或滚动、停留；旁白按同一 `step_id` 对齐，只解释当前屏幕，不做事后预测。
- 生产必须使用真实模拟器录屏和服务端 MiniMax 中文旁白。单张截图平移、无图层变化或无法对应脚本步骤的素材不得进入发布阶段。
- 发布前必须同时通过四项检查：每一步画面变化与口播对应、视频为 H.264/AAC 且响度正常、媒体 URL 可匿名 `HEAD/GET`、Buffer 频道身份与幂等标识已核实。任一失败则记录阻塞并停止发布。

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

## 运行记录（2026-09-07 北京时间）

- 每日任务在发布前置核验阶段正常结束：按北京日期（账号时区 Asia/Singapore, UTC+8）核查，两个频道当日均已有 sent 帖子，命中防重复闸门，未生产也未发布新内容。未更新任何 latest-* 指针。
- 上一次运行遗留阻塞已解除：TikTok postId 6a9d985b5c2ba4d154180dba 已由 sending 变为 sent（2026-09-06T16:46:32Z），公开链接 https://tiktok.com/@littlemonkey437/video/7682464195287272724 。run 2026-09-06-claude-demo 的 publish.md 中"TikTok 未确认"的结论已过时。
- 日期口径教训：上一次运行在 UTC 16:42–16:46 提交，实际已跨入北京 2026-09-07，却被记为 date_beijing 2026-09-06。今后构造幂等标识和查重必须用 UTC+8 换算后的日期，避免跨零点误判。
- 档期占用提示：占住 2026-09-07 的两条帖子是带「【演示/测试，稍后删除】」前缀的全流程测试内容，已真实公开发布。若要在当日发布正式内容，需先删除这两条帖（及 TikTok 草稿 6a9d97d96acbdfc9eda3d6dc）再手动重跑任务。
- 权限现状：本次会话初始 connectedFolders 为空，三个文件夹（仓库、~/.config/deepalpha、Desktop）与 computer-use（Simulator full / Xcode click）均为本次运行主动申请后获批。~/.config/deepalpha/marketing.env 存在且权限为 0600。
- 2026-09-07 正式发布完成：用户确认平台侧已删除占位测试内容并授权后重跑，三阶段全部走通。NVDA 五图层教学，成片 39.20 秒 720×1280 H.264/AAC，sha256 91fa13eb…9869。TikTok postId 6a9da23d9730c9bde54a5ff1（sent，https://tiktok.com/@littlemonkey437/video/7682474924597873941），YouTube postId 6a9da2536acbdfc9eda4d24f（sent，Short，Education，public，https://www.youtube.com/watch?v=Ul7AOK553Ko）。两条均 schedulingType=automatic + shareNow，均标记 AI 生成。
- 工程经验（本次新增）：① device_bash 每次调用是独立 bwrap 沙箱且 --die-with-parent，后台 nohup 进程无法跨调用存活，长任务（ffmpeg 约 2 分 40 秒）必须同步执行并显式设置 timeout_ms。② ffmpeg crop 的 w/h 只在初始化时求值，不支持随 t 变化，连续推近必须用 zoompan。③ zoompan 用 z='1+k*on/N' 线性表达式，不要用 min(zoom+step, cap)，后者会在中途封顶变成静止画面。④ MiniMax 中文约 0.27 秒/字，四段合计控制在约 130 字以内才能落进 20–45 秒。⑤ device_bash 运行在 Linux VM 中，没有 xcrun/simctl，模拟器只能通过 computer-use 操作 macOS 侧；app_click 对 Save Screen 按钮无效，用 app_key combo=cmd+s 成功。
- 2026-09-07 第二次定时触发（北京 08:06）在发布前置核验阶段正常防重复退出：两个频道当日均已有 sent 的正式内容（TikTok 6a9da23d…01:28、YouTube 6a9da253…01:26），未生产、未发布、未更新任何 latest-* 指针。全量查询 draft/scheduled/sending/error/needs_approval 仅返回一条 TikTok 测试草稿 6a9d97d96acbdfc9eda3d6dc，无 sending/error 需要消歧。回执见 runs/2026-09-07/run-summary-0806.md。
- 指标口径教训（本次新增）：Buffer 返回的 0 值不等于真实零表现。若某帖 metricsUpdatedAt 等于甚至早于 sentAt（如 09-06 白天那 6 条），说明平台从未采集过该帖指标，必须记为「缺失/未采集」。同期聚合接口在 09-01~09-07 只计入 2 条帖（实际 sent 10 条），进一步说明采集覆盖率不足，聚合值不能当作整体表现。
- 数据缺口未变：YouTube 官方 Analytics、TikTok 官方数据与下载/注册/付费归因仍未接通，公开互动数据不代替转化归因。
