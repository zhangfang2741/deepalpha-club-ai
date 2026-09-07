# 缠论每日运营执行手册

## 调度入口

只保留 `app`（缠论 APP 每日运营全流程），每日北京时间 09:00，工作目录固定为 `/Users/zhangfang/deepalpha-club-ai`。项目 `.codex/config.toml` 明确使用内置 `openai` 服务。不要恢复使用 `codexcnorg` 的旧失败任务；它们保存了已经移除的服务名称。模型与工具续接使用桌面应用随附版本实测。

## 前置配置

- 本机需保持可运行状态，具备 Xcode、iOS 模拟器、ffmpeg、uv 和已授权的 Buffer 连接。
- 中文旁白从项目 `.env` 或环境变量读取 MiniMax 配置，使用 `Chinese` 与中文音色；不传历史失败的 `emotion=fluent` 参数。
- 无签名 Debug 模拟器不能假定 Keychain 可用。自动登录读取仓库外 `~/.config/deepalpha/marketing.env` 的 `CHAN_DEMO_ACCOUNT`、`CHAN_DEMO_PASSWORD`，通过子进程环境注入，不放命令行、不写仓库。文件权限必须为 0600。
- 运营桥接仅编译到模拟器 Debug 包；登录、分析、额度检查沿用真实 App。没有绕过鉴权或订阅限制。
- 若模拟器未启动，读取 `xcrun simctl list devices available` 后启动已有的 iPhone 模拟器并等候启动就绪；不要删除或重置设备数据。
- 首次运行或 Swift 代码改变后，构建并安装 `ios/DeepAlphaChan.xcodeproj` 的 `DeepAlphaChan` Debug 模拟器包。当前验证设备为 iPhone 17 Pro；应使用实际设备 ID，不盲目创建新设备。

## 顺序执行

1. 先用 Buffer 连接器读取 `My organization` 下的频道身份、当天帖子和未确定的提交。两平台当日已成功则正常运营结束；测试模式可以生产新素材但只创建草稿，不重复公开发布。复盘应先于“当天已发布”的退出判断，24/72 小时未到期就不编造数据。
2. 核验市场信息与候选来源。生产工具的候选参数只是调用方提供的顺序，不自动代表“热门”或市场评分。常青教程明确说明是历史结构教学，不能把测试候选筛选说成热点研究。
3. 执行 `uv run python scripts/chan_marketing.py produce --run-id 日期-唯一标识 --symbols NVDA AAPL TSLA`。功能测试加 `--test`。工具逐个请求真实分析、筛选已确认分型和笔，生成 4 段中文旁白与对应图层脚本，等待页面就绪，开始真实录屏，按音频长度对齐动作，编码并提取每步画面。没有合格结构或任何失败则停止。
4. 读取该运行的 `selection.json`、`script.json`、`events.json`、`production.json`，查看每个 `frame-*.jpg` 并核验声音内容、音量和时间对应。不得仅凭文件存在就通过。完成核验后写 `review.json`，包含成片 `sha256`、`visual: passed`、`audio: passed` 和实际核验依据。这里的核验由执行任务的助手完成，不要求用户每天确认。
5. 执行 `uv run python scripts/chan_marketing.py upload --run-id 同一标识`。它会检查审核哈希，调用真实 `/api/v1/media/upload`，匿名 HEAD 与 GET，比较下载内容哈希；失败时禁止 Buffer 提交。上传结果保存在 `upload.json`。此处不会自动重试上传，避免不明确响应造成重复对象。
6. 通过 Buffer 再次核实频道：TikTok `littlemonkey437`、YouTube `DeepAlpha`。每个平台提交前写入 `submit-频道.json`：日期、内容哈希、主题、频道 ID、`status: submitting`；获取响应后立即保存 postId 和真实状态。若中断在 submitting，先查询 Buffer，不再次盲目创建。
7. 测试模式使用 `saveToDraft: true`，确认草稿视频和频道绑定正确即可验证提交，不把草稿写成公开发布成功。日常发布按授权执行，YouTube 必须提供标题与分类，两个平台标记合成配音。平台返回 sending 时保留待核验状态；只有 sent 和公开链接才写成功。
8. 写入本次 `publish.json/md`，更新 `latest-selection.json/md`、`latest-production.md`、`latest-publish.md`。只更新对应成功阶段的指针，全部记录必须使用相同 run_id。测试产物标记 test，不覆盖日常发布事实。

## 故障恢复

- `failure.json` 指明失败阶段；未完成阶段不得放行。旧失败日志保留用于审计。
- `production.json` 已存在时工具拒绝覆盖，先检查并继续 review/upload；确需重新生产时使用新运行标识。
- `runs/.production.lock` 对生产及上传加进程锁，防止两次运行同时操作模拟器。
- 字幕或旁白与画面不符时调整脚本重新生产；不能使用截图平移或旧 MP4 冒充本次录屏。
- 已发布渠道不重复提交，单渠道失败只补缺失渠道。历史回执与当天测试分开保留。

## 测试

`uv run pytest tests/test_chan_marketing.py -q` 验证失败闸门；`uv run pyright scripts/chan_marketing.py` 检查生产脚本。完整记录以运行目录为准，成功的旧帖子不能代替本次生产测试证据。
