# czsc 接入 spike 发现记录

日期：2026-09-23

## 环境验证

- `uv add czsc` 是否成功：**成功**，退出码 0。安装 `czsc==1.0.1`，同时拉入 14 个包
  （含 `pyarrow==25.0.1`、`polars==1.44.2`、`scipy==1.18.1`、`statsmodels==0.15.0`、
  `plotly==7.1.0`、`wbt==0.9.1` 等体量较大的依赖）。
- Python 3.13 + 本机环境是否用了预编译 wheel（无需本地 Rust 工具链）：**是**。整个安装
  过程只有 `Downloading` / `Prepared` / `Installed` 三个阶段，没有触发本地编译（无
  `Building` 或 cargo/rustc 相关日志），说明 czsc 为 Python 3.13 提供了预编译 wheel。
  耗时较长（`uv add` 总计约 11 分钟），主要花在 `Prepared 14 packages in 11m 01s` 这一步的
  下载上（pyarrow 35.9MiB、polars-runtime-32 46.1MiB 等大文件），而非编译。
  另外有一条无害警告：`VIRTUAL_ENV=/Users/zhangfang/deepalpha-club-ai/.venv` 与本 worktree
  的 `.venv` 路径不一致，被 uv 忽略（多 worktree 共享同一 shell 环境变量导致，不影响安装结果）。

## 数据类型确认

- `RawBar.dt` / `FX.dt` 实际 Python 类型：**`pandas._libs.tslibs.timestamps.Timestamp`**
  （即 `pd.Timestamp`），不是原生 `datetime.datetime`。构造 `RawBar` 时传入的是
  `datetime.datetime`，但 czsc 内部会转换为 `pd.Timestamp` 存储/暴露。
  - `BI.sdt`/`BI.edt` 本次合成数据未形成任何笔（`bi_list` 为空），未能直接观测其类型，
    但基于 `FX.dt` 的表现，合理推断同样是 `pd.Timestamp`（下一阶段实现前应对真实数据
    再验证一次，不能仅凭本次 spike 假设）。
- `fx.mark` 的实际取值与比较方式：本次样例中 `fx.mark` 打印为**中文字符串 `"顶分型"`**
  （而非设计文档预期的 `Mark.G` 之类枚举成员的 repr）。这意味着如果生产代码要判断
  “这是顶分型还是底分型”，不能想当然地写 `fx.mark == Mark.G`，需要在下一阶段先确认
  `Mark` 枚举与该中文字符串之间的相等关系是否成立（例如 `Mark` 是否是一个其成员的
  `str()`/`__eq__` 结果恰好等于中文名的枚举），本次 spike 未验证，记为**待办/风险点**。

## 结构识别验证（合成数据）

- `CZSC(bars).fx_list/bi_list/zs_list` 数量：`fx_list=1, bi_list=0, zs_list=0`。
  spike 脚本设计的“前 30 根涨、后 30 根跌，每 3 根一次小幅回调制造分型”的合成数据，
  在 czsc 的实际分型/笔判定逻辑下，只识别出 **1 个顶分型**，未形成任何笔或中枢。
  这与设计文档 Step 2 注释里“保证能形成至少几笔和一个中枢”的预期不符，说明
  czsc 对分型 → 笔的确认条件（如笔至少需要独立分型间隔、缠论笔成立的多重约束）
  比本次合成数据构造得更严格，60 根简单往复的合成 K 线不足以触发笔的确认。
  - `FX` 样例：`mark=顶分型`，`dt=2024-02-01 00:00:00`，`high=117.5`，`low=116.8`，
    `fx=117.5`（顶分型的 fx 值取 high）。
- `BI.direction` 取值：**本次无法观测**，因为 `bi_list` 为空（原因见上）。需要在下一阶段
  用真实行情数据（如已有的 FMP 前复权日线）重跑一次，才能拿到真实的 `BI` 样例。

## 信号目录探测

- `czsc._native.signals` 命名空间下有哪些子模块（`dir()` 结果，共 11 项）：
  ```
  ['bar', 'call_signal', 'cvolp', 'cxt', 'get_signal_category', 'get_signal_template',
   'list_signal_names', 'obv', 'pressure', 'tas', 'vol']
  ```
  其中 `bar`/`cvolp`/`cxt`/`obv`/`pressure`/`tas`/`vol` 是信号子模块（按数据来源分类：
  K线/量能价格/缠论结构/OBV/压力位/技术指标/成交量），`call_signal`/`get_signal_category`/
  `get_signal_template`/`list_signal_names` 是配套的工具函数。
- `generate_czsc_signals` 用 README 给出的两个信号名能否跑通：**不能，报错**。
  用字符串列表 `["czsc._native.signals.bar.bar_end_V230331", "czsc._native.signals.cxt.cxt_bi_status_V230101"]`
  调用时报错：
  ```
  [9-ERROR] generate_czsc_signals 调用失败: ValueError: signals_config 中每个元素必须是 dict
  ```
  说明当前安装的 `czsc==1.0.1` 版本中，`generate_czsc_signals` 的 `signals_config` 参数
  期望的是 **dict 列表**（大概率类似 `{"name": "bar_end_V230331", ...其他参数}` 的结构），
  而不是 README 示例里的纯字符串路径列表。README 示例可能对应旧版本 API，或者字符串
  只是信号名简写、还需要额外包装成 dict。这是本次 spike 确认的一个**真实 API 不匹配点**，
  下一阶段对接信号系统前必须先用 `get_signal_template` / 源码/文档确认 dict 的正确 schema，
  不能照抄 README。
- 背驰/买卖点相关信号函数的命名规律：用 `czsc._native.signals.list_signal_names()`
  （共 222 个信号名）过滤出与 `beichi`/`mmd`/`bs`/`zs`/`div` 相关的候选，共 24 个，摘录如下：
  ```
  bar_vol_bs1_V230224
  byi_second_bs_V230324
  byi_symmetry_zs_V221107
  cxt_bs_V240526
  cxt_bs_V240527
  cxt_double_zs_V230311
  cxt_second_bs_V230320
  cxt_second_bs_V240524
  cxt_third_bs_V230318
  cxt_third_bs_V230319
  tas_dma_bs_V240608
  tas_first_bs_V230217
  tas_macd_bs1_V230312
  tas_macd_bs1_V230313
  tas_macd_bs1_V230411
  tas_macd_bs1_V230412
  tas_macd_first_bs_V221201
  tas_macd_first_bs_V221216
  tas_macd_second_bs_V221201
  tas_second_bs_V230228
  tas_second_bs_V230303
  zdy_macd_bs1_V230422
  zdy_zs_V230423
  zdy_zs_space_V230421
  ```
  命名规律：`<模块前缀>_<语义片段>_V<年月日版本号>`。`bs`（buy/sell，一/二/三类买卖点，
  用 `first`/`second`/`third` 区分）、`zs`（中枢相关，如 `double_zs` 双中枢、`zs_space`
  中枢空间）是核心关键词；未直接搜到英文 `beichi`/`divergence` 字样，背驰应是通过
  `tas_macd_*`（MACD 相关技术指标信号）间接表达，而非独立以“背驰”命名。这一点需要在
  下一阶段深入阅读具体信号函数的返回值语义（如 `tas_macd_bs1_V230312` 是否直接给出
  背驰判定），本次 spike 只做了名录级探测，未验证语义。

## 结论：Go / No-Go

**结论：Go（有条件）。**

理由：
1. **硬性阻塞项不存在** —— `uv add czsc` 在 Python 3.13 环境下成功安装，走的是预编译
   wheel，没有触发本地 Rust 编译，安装耗时长但纯粹是下载体积大导致，不是环境不兼容。
   这是本任务定义的 go/no-go 硬门槛，已通过。
2. `CZSC` 基础构造、`fx_list` 均可正常使用，`czsc._native.signals` 命名空间和 222 个
   信号函数确实存在，具备继续深入的基础。

但发现了两个**非阻塞、但下一阶段必须先处理**的风险点，不能假装没看见：
- `RawBar.dt`/`FX.dt` 实际是 `pd.Timestamp` 而非 `datetime.datetime`，对接现有
  `app/services/chan/` 代码时如果有 `isinstance(x, datetime.datetime)` 之类的类型假设
  需要重新检查（`pd.Timestamp` 是 `datetime.datetime` 子类，多数场景兼容，但序列化/
  JSON 编码路径要单独确认）。
- `generate_czsc_signals` 的 `signals_config` 参数 schema 与 README 示例不一致（需要
  dict 而非字符串），且本次合成数据未能触发任何笔/中枢，也未验证背驰相关信号的真实
  语义。**下一阶段（信号函数接入）开始前，必须先用真实行情数据 + dict 格式的
  signals_config 重新做一轮更细致的探测，特别是 `Mark` 枚举比较方式、`BI.direction`
  真实取值、以及 `tas_macd_bs1_*`/`cxt_*_bs_*` 这些信号函数的准确返回结构。**

即：环境可行性层面无阻塞，可以继续推进重构计划；但 API 细节层面还有多处
“文档/示例与实际运行不符”的坑，后续任务需要预留专门的时间做二次探测，不要直接
照抄 README 或设计文档里的示例代码。
