# 缠论每日运营执行手册

## 调度入口

只保留 `app`（缠论 APP 每日创意闭环运营），每日北京时间 09:00，工作目录固定为 `/Users/zhangfang/deepalpha-club-ai`。项目 `.codex/config.toml` 明确使用内置 `openai` 服务。不要恢复使用 `codexcnorg` 的旧失败任务；它们保存了已经移除的服务名称。模型与工具续接使用桌面应用随附版本实测。

## 前置配置

- 本机需保持可运行状态，具备 Xcode、iOS 模拟器、ffmpeg、uv 和已授权的 Buffer 连接。
- 中文旁白从项目 `.env` 或环境变量读取 MiniMax 配置，使用 `Chinese` 与中文音色；不传历史失败的 `emotion=fluent` 参数。
- 无签名 Debug 模拟器不能假定 Keychain 可用。自动登录读取仓库外 `~/.config/deepalpha/marketing.env` 的 `CHAN_DEMO_ACCOUNT`、`CHAN_DEMO_PASSWORD`，通过子进程环境注入，不放命令行、不写仓库。文件权限必须为 0600。
- 运营桥接仅编译到模拟器 Debug 包；登录、分析、额度检查沿用真实 App。没有绕过鉴权或订阅限制。
- 若模拟器未启动，读取 `xcrun simctl list devices available` 后启动已有的 iPhone 模拟器并等候启动就绪；不要删除或重置设备数据。
- 首次运行或 Swift 代码改变后，构建并安装 `ios/DeepAlphaChan.xcodeproj` 的 `DeepAlphaChan` Debug 模拟器包。运营固定使用专用设备 `DeepAlpha-Marketing-iPhone-17-Pro`（UDID `95F37B4C-7BEF-4690-ACAA-9018B3C246B0`）；可用 `CHAN_SIMULATOR_UDID` 显式覆盖。生产脚本会启动并等待该设备，不再使用含糊的 `booted` 目标，避免误录其他模拟器。
- Debug 模拟器不申请 APNs 通知权限。录屏前必须保存 `preflight.png` 并检查中心区域亮度；检测到系统弹窗或亮色遮挡立即停止，禁止先录后侥幸发布。
- 成片固定为 720×1280。背景可以铺满，但所有标题、价格、图表、图例及字幕必须落在平台安全区 `x=36–600, y=96–1020`；右侧至少预留 120 像素给点赞/评论/转发，底部至少预留 260 像素给账号、标题与平台说明。逐帧视觉审核必须明确检查这两处，不得只检查画面是否存在。

## 顺序执行

1. 先用 Buffer 连接器读取 `My organization` 下的频道身份、当天帖子和未确定的提交。两平台当日已成功则正常运营结束；测试模式可以生产新素材但只创建草稿，不重复公开发布。复盘应先于“当天已发布”的退出判断，24/72 小时未到期就不编造数据。
2. 识别最新版 APP，而不只确认二进制能够启动。读取 `ios/AppStore/chan/RELEASE-*-STATUS.md`、当前版本与构建号、最近涉及 `ios/DeepAlphaChan` 的提交和实际界面，建立最新版能力清单。能力清单至少核对实际存在的三市场覆盖、市场雷达、买卖点严格/中等/宽松口径、基本面评分与分位、财报入口与 AI 总结、学习页和自选；只记录当前源码或已发布版本真实具备的能力，不得臆造。
3. 读取最近 14 天的 `daily/`、`runs/*/creative-brief.json`、发布文案与表现数据，建立题材去重表。连续 7 天不得重复相同的“标的 + 开头钩子 + 教学结构 + 画面路径”；连续两天不得使用相同标的作为主角，除非出现有权威来源支持的重大市场事件。若现有生产能力只能生成重复模板，必须停止发布并记录所缺能力，不得用旧模板兜底。
4. 每天先完成四层研究再选题：市场层比较美股、A 股、港股或当天有可靠数据的市场；行业层用真实行业雷达比较行业强弱、结构状态或信号分布；个股层从所选行业的真实个股雷达或名单筛选标的；基本面层核实综合评分或等级、同行业或样本分位、关键维度以及最新财报或公司事实。最终形成“市场 → 行业 → 个股 → 基本面 → 缠论结构”的筛选链。市场事实至少使用一个交易所、上市公司公告、SEC 文件或其他一手来源，并记录 URL、事件时间、数据日期和最近交易日。任一层缺少可靠数据时必须换市场、行业或标的；缺失指标明确写缺失，禁止推断或填零。常青教程仍须展示完整四层 APP 路径，不得把测试候选筛选说成热点研究。
5. 每次生产前写入 `creative-brief.json`，至少包含：`market_event`、`primary_source`、`symbol`、`chan_structure`、`format`、`hook_0_3s`、`app_actions`、`deepalpha_app_store_prompt`、`difference_from_last_14d`、`app_version`、`app_build`、`latest_app_capabilities`、`version_evidence`、`market_radar_snapshot`、`industry_radar_snapshot`、`stock_radar_snapshot`、`fundamental_snapshot`、`selection_funnel`、`selected_latest_capabilities`。四个 snapshot 分别记录真实界面证据、数据日期、核心事实和缺失项；`selection_funnel` 解释每一层如何筛到下一层。只选择一项新版功能、只做三市场切换或只重复分型、笔、线段均不算结合最新版 APP。
6. 视频开头 0–3 秒必须给出与当天选题直接相关的问题、反差或可核验事实，并展示真实 App 或真实市场画面；5 秒内进入市场或行业雷达。20–45 秒内必须讲清一个结论，并真实完成至少五步有意义操作：市场雷达或市场/指数切换、进入行业雷达或行业面板、进入个股雷达/名单并选中个股、打开基本面评分与分位或财报、进入个股缠论结构。旁白和字幕必须分别点明市场、行业、个股、基本面与结构的关键事实。结尾 3–5 秒使用自然转化引导：画面与口播统一写“App Store 搜索 DeepAlpha 缠论”；YouTube 文案保留 App Store 直链。不得承诺收益、夸大信号或伪造实时性。
7. 使用本项目已验证生产流程执行当天 `creative-brief.json` 对应的真实 App 操作。若 `scripts/chan_marketing.py` 尚不支持 brief 所需的标的、图层顺序、停留、缩放、滚动或 DeepAlpha 缠论下载引导，可先做最小安全扩展并跑测试；禁止退回硬编码的固定四段模板。没有合格结构或发生失败时，按下方“当日目标闭环”回到对应上游节点继续，不把单次尝试失败当作整日任务结束。
8. 读取该运行的 `creative-brief.json`、`selection.json`、`script.json`、`events.json`、`production.json`，查看每个 `frame-*.jpg` 并核验声音内容、音量、时间对应、钩子兑现和“DeepAlpha 缠论”完整品牌名及下载引导。确认关键信息没有进入右侧 120 像素及底部 260 像素的平台覆盖区。不得仅凭文件存在就通过。完成核验后写 `review.json`，包含成片 `sha256`、`visual: passed`、`audio: passed`、`platform_safe_zone: passed`、`creative_brief_match: passed` 和实际核验依据；`creative_brief_match` 必须列出版本号、四层 snapshot、五步真实操作及各自关键帧/时间码，并证明旁白与画面事实一致。缺少任一层、任一步或证据即判失败。
9. 执行 `uv run python scripts/chan_marketing.py upload --run-id 同一标识`。它会检查审核哈希，调用真实 `/api/v1/media/upload`，匿名 HEAD 与 GET，比较下载内容哈希；失败时禁止 Buffer 提交。上传结果保存在 `upload.json`。此处不会自动重试上传，避免不明确响应造成重复对象。
10. 通过 Buffer 再次核实频道：TikTok `littlemonkey437`、YouTube `DeepAlpha`。每个平台提交前写入 `submit-频道.json`：日期、内容哈希、主题、频道 ID、`status: submitting`；获取响应后立即保存 postId 和真实状态。若中断在 submitting，先查询 Buffer，不再次盲目创建。
11. 测试模式使用 `saveToDraft: true`，确认草稿视频和频道绑定正确即可验证提交，不把草稿写成公开发布成功。日常发布按授权执行，YouTube 必须提供标题与分类，两个平台标记合成配音。平台返回 sending 时保留待核验状态；只有 sent 和公开链接才写成功。
12. 写入本次 `publish.json/md`，更新 `latest-selection.json/md`、`latest-production.md`、`latest-publish.md`。只更新对应成功阶段的指针，全部记录必须使用相同 run_id。测试产物标记 test，不覆盖日常发布事实。

## 故障恢复

- `failure.json` 指明失败阶段；未完成阶段不得放行。旧失败日志保留用于审计。
- `production.json` 已存在时工具拒绝覆盖，先检查并继续 review/upload；确需重新生产时使用新运行标识。
- `runs/.production.lock` 对生产及上传加进程锁，防止两次运行同时操作模拟器。
- 字幕或旁白与画面不符时调整脚本重新生产；不能使用截图平移或旧 MP4 冒充本次录屏。
- 已发布渠道不重复提交，单渠道失败只补缺失渠道。历史回执与当天测试分开保留。

## 当日目标闭环

- 当日目标定义为：复盘已完成；完整的市场、行业、个股雷达、基本面与缠论结构筛选链已经核实并在真实 APP 中演示；创意 brief 与全部审核闸门通过；TikTok 与 YouTube 均为 `sent` 且有公开链接；“DeepAlpha 缠论”完整品牌名及 App Store 下载引导已在画面、口播和 YouTube 文案中核实。`draft`、`sending`、仅单频道成功、只有本地成片、只重复旧图层模板或只展示单个功能都不算完成。
- 每天先创建 `daily-goal.json`，记录 `date_beijing`、目标、`status: in_progress`、尝试列表和已完成频道。每次失败都追加：`run_id`、失败阶段、根因、保留的有效证据、下一轮要改变的变量和返回节点。
- 市场来源或候选不合格：回到市场研究与候选池，换一手来源、标的或创意角度；不得强行使用无结构标的。
- 旁白时长、脚本或素材能力不足：回到 creative brief 和生产实现，调整文案、步骤或做最小安全扩展，跑测试后使用新 run_id 重产。
- 模拟器、构建、录屏或画面审核失败：先诊断并恢复设备/构建环境，再用新 run_id 重产；不得复用被否决的成片。
- 音频、编码、安全区、钩子、“DeepAlpha 缠论”品牌名或下载引导审核失败：修改具体失败项，重新编码或使用新 run_id 重产，并重新执行完整审核。
- 上传失败：先判断远端是否已经创建对象；响应不明确就查询，只有确认未创建时才能再次上传，禁止盲目制造重复媒体。
- Buffer 返回 `sending`：持续查询原 postId；返回明确 `error` 时修正原因后只补失败频道。任何已 `sent` 的频道都不得重复提交。
- 单次 attempt 的失败闸门只阻止该 attempt 继续向下游，不终止当天任务。执行助手必须携带问题和证据回到对应上游节点，持续循环，不能设置任意的固定尝试次数，也不能因为耗时、困难或首次失败而提前结束。
- 只有出现当前权限内无法解决的外部硬阻塞，例如账号重新授权、验证码/人工验证、凭证缺失或失效、第三方持续服务中断、平台明确拒绝且必须由账号所有者处理，才可将 `daily-goal.json` 标为 `blocked_external`。此时必须保存精确恢复入口和已完成阶段，不得虚报成功；外部条件恢复后从该入口继续，而不是重新提交已成功对象。
- 完成后将 `daily-goal.json` 标为 `achieved`，写入最终成功 run_id、双频道 postId/公开链接和复盘时间；只有这时自动化才可以结束。
- 命名规则：文档、字段、审核回执和最终报告不得再用 `CTA` 代称产品；统一写完整产品名“DeepAlpha 缠论”，需要描述转化动作时写“DeepAlpha 缠论 App Store 下载引导”。

## 测试

`uv run pytest tests/test_chan_marketing.py -q` 验证失败闸门；`uv run pyright scripts/chan_marketing.py` 检查生产脚本。完整记录以运行目录为准，成功的旧帖子不能代替本次生产测试证据。
