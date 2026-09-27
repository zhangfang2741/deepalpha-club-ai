# 信号雷达形态过滤设计（czsc 形态信号剔除假信号）

日期：2026-09-27
状态：**已暂停应用**（2026-09-27，代码保留，开关 `signal_radar.service._SHAPE_FILTERS_ENABLED=False`）。
全量 nasdaq100 实测：关掉形态过滤，最近 10 个交易日每天在场信号数完全不变（最新日 2 条）；
雷达变空主要来自「未确认不上榜」（关掉该要求最新日 13 条）。产品决定先不做这层过滤。
规则以下节「校准后调整」为准。

## 背景与目标

雷达扫全市场成分股跑缠论，上榜信号里混有「假信号」：窄幅震荡里硬凑出来的买卖点、
突破当天就是假突破的信号、低波动阴跌市里的弱信号、收盘偏弱的买点、震荡市里缺乏
趋势前提的一类信号。czsc 1.0.1 Rust 内核自带 7 个形态过滤信号模板，逐根推进即可
得到「每天当时的形态状态」。本设计把这些信号接入雷达，在信号出生时一次判定、命中
即剔除。

**范围**：只影响雷达三类缓存（每日快照、自选、示例日）。详情页、次级别确认、
其他模块的买卖点口径完全不动。

## 校准后调整（2026-09-27，以此为准）

实施到最后一步用 40 只 nasdaq100 成分股真实日线（雷达同一取数窗口，约 310 根，
宽松口径 241 条信号）校准，原设计会让雷达几乎清空：

| 方案 | 判定日 | 全部保留 | 最近 30 根保留 |
| --- | --- | --- | --- |
| 原设计五条 | 笔终点日 | 24% | 5/36 |
| 五条 | 成立日 | 37% | 10/39 |
| 去掉收盘位置 | 成立日 | 54% | 13/39 |
| **假突破 + 窄幅震荡 + 低波动（采用）** | **成立日** | **88%** | **25/39** |

用户据此选定：

1. **判定日改为信号成立日**（`detected_time`，缺失回退笔终点日），即雷达展示的日期，
   同样不回看未来。笔终点日是分型极值那根K线，买点那根天然收在低位、卖点天然收在高位，
   用它判定形态会系统性误剔（原设计收盘位置一条就剔 54%）。
2. **只保留三条硬剔除**：同向假突破、窄幅震荡、低波动。
3. **移除收盘位置**（`bar_classify_V240606/07`）：单根收盘位置近似随机，在任何判定日
   都会无差别砍掉约 1/4 信号。
4. **移除区间震荡**（`cxt_range_oscillation_V230620`）：在成立日砍掉一半一类信号，
   th=5/10/15 结果几乎不变（对阈值不敏感），且与一类自身的趋势前提重复。
5. 两个被移除的 czsc 信号不再计算（config / ShapeState 字段一并删除，不留死代码）。

最终代码实测：保留 88%（剔除中低波动 9%、窄幅震荡 3%；成立日样本里假突破 0 条，
它要求当天是长实体K线，属低频兜底）；所有信号成立日都能在形态状态表查到。

下文保留原始设计过程供追溯；其中关于收盘位置、区间震荡、笔终点日的内容已被本节取代。

## 信号语义（Rust 源码确认）

| 信号 | 参数（本项目取值） | 取值 | 语义 |
| --- | --- | --- | --- |
| `bar_fake_break_V230204` | di=1, n=20, m=5 | 看多 / 看空 / 其他 | 近 n 根找 m 窗口重叠中枢；**看空=向上假突破**（长实体突破中枢上沿 GG 后收回），**看多=向下假突破**（跌破下沿 DD 后收回） |
| `bar_volatility_V241013` | w=120, n=10 | 低波动 / 中波动 / 高波动 | 近 n 根收盘极差，对近 w 根缓存值三分位分层。分档值从第 ≈ w+130 根起产出（w=100~200 五点实测 220/240/250/270/320）；分层还需序列本身有波动率对比，波动恒定的序列恒「其他」属正常退化（与 w 无关）。w=120 取值依据：产出更早且 500 根雷达窗口内有效覆盖更长 |
| `bar_zfzd_V241013` | n=10 | 满足 / 其他 | 近 10 根K线高低区间全重叠（窄幅震荡） |
| `bar_zfzd_V241014` | n=10 | 满足 / 其他 | 近 10 根最大实体重叠版 |
| `bar_classify_V240606` | di=1 | 高位 / 中间 / 低位 | 单根K线收盘位置三分位 |
| `bar_classify_V240607` | di=1 | 看多 / 看空 / 中性 | 两根K线收盘位置 |
| `cxt_range_oscillation_V230620` | di=1, th=10 | X笔震荡_向上/向下 / 其他 | 近 12 笔中心振幅 < th% 的连续笔数统计（czsc 默认 th=2 对美股日线几乎不触发，本项目取 10） |

## 已确认的产品决策

1. **过滤策略**（五条全上）：
   - 假突破：**仅同向剔除**——买点日=看空（向上假突破）剔、卖点日=看多（向下假突破）
     剔；反向假突破（跌破后收回）常正是一/二买自身形态，不剔。
   - 窄幅震荡：V241013 / V241014 任一=满足 → 剔。
   - 收盘位置：买点日须 V240606=高位 **或** V240607=看多（任一满足即可保留）；卖点
     反之（低位 / 看空）；否则剔。「中间 + 中性」也剔。
   - 波动率分层：信号日=低波动 → 剔；K 线不足 w+n 根（三分位退化）时**跳过此过滤**，
     不误杀。
   - 区间震荡：信号日处于「X笔震荡」且信号为一类（buy1/sell1）→ 剔；二 / 三类保留。
2. **时点语义**：出生时一次判定。用「信号所属笔终点日」（`sig.time`）当天的形态状态，
   命中过滤器则该信号所有展示日都不出现。形态信号逐根推进、不回看未来，查任意历史
   日期都是当时可知信息，无未来函数；历史日回放天然稳定。
3. **App 配合**：透明过滤。后端直接剔除，气泡变少；iOS「上榜排序怎么算」说明区补三
   行文案 + Localizable.strings 中英文。
4. **实现方式**：方案 A——复用 `scan_bs_events` 一次推进，形态信号与买卖点信号共用
   同一个 `CzscSignals` 实例，零重复构建。

## 数据流

```text
K线（雷达取数，前复权，窗口不变）
 └─ ChanAnalyzer.analyze()
     └─ czsc_signals.scan_bs_events(bars, ..., shape_states={})   ← config 追加形态信号族
         ├─ 买卖点事件（不变）
         ├─ stroke_done_at（不变）
         └─ shape_states: dict[日期, ShapeState]（新增）
             ↓ 挂到 ChanAnalysisResult.shape_states（详情页不读，口径不动）
信号雷达 service
 └─ build_signal_history(): RawSignal 增加 shape_rejected: str | None（首个命中的过滤器名）
 └─ build_days(): 每-symbol 最新信号确定后，shape_rejected 非空 → 该 symbol 当日无信号
```text

## 模块设计

### `app/services/chan/shape_filters.py`（新文件）

- `@dataclass ShapeState`：`fake_break: str`、`narrow_range: bool`、`close_pos: str`、
  `k2_close_pos: str`、`volatility: str`（低/中/高/未知）、`range_osc: str`。
- 形态信号参数集中在文件顶部常量（含 `th=10`、`w=120`、`n` 等），`shape_config()`
  产出 czsc 信号 config 列表，`shape_keys()` 产出读取用的信号键。
- `read_shape_state(cs, label, date)`：从 CzscSignals 状态字典读出当日各信号取值，
  组装 ShapeState。K 线不足 w+n 根时 `volatility="未知"`。
- `reject_reason(state, signal_type) -> str | None`：纯函数，按短路顺序套五条规则，
  返回首个命中的过滤器名（"假突破" / "窄幅震荡" / "收盘位置" / "低波动" / "区间震荡"），
  未命中返回 None。供雷达层调用，规则集中可测。

### `app/services/chan/czsc_signals.py`

- `scan_bs_events` 加参数 `shape_states: dict[str, ShapeState] | None = None`；传入时
  config 合并形态信号，逐根推进时写入 `shape_states[当根日期]`（与 `stroke_done_at`
  同构）。None 时行为与现状完全一致。

### `app/services/chan/analyzer.py`

- `ChanAnalysisResult` 加 `shape_states: dict[str, ShapeState] = field(default_factory=dict)`
  （默认空 dict，详情页与既有调用不受影响）。
- `analyze()` 加参数 `shape_filters: bool = False` 控制是否向 `scan_bs_events` 传
  `shape_states`；雷达路径传 True，详情页 / replay / sub-level 不传。

### `app/services/signal_radar/service.py`

- `_scan_symbol()`（及其内部调 `analyze` 的位置）传 `shape_filters=True`。
- `build_signal_history()`：对每个信号查 `result.shape_states.get(sig.time)`，
  `reject_reason(...)` 命中则 `RawSignal.shape_rejected = 过滤器名`。
- `build_days()`：每-symbol 最新候选确定**之后**，`shape_rejected` 非空则该 symbol 当日
  无信号——不让被剔的新信号背后的旧信号顶替上榜（沿用「先选最新再筛选」既有模式）。
- 缓存键 `:shape1:` → `:shape2:`（形态过滤改变雷达结果，三类缓存：每日快照 / 自选 /
  示例日全部换键）；`_mode_ns` 注释同步更新。
- `shape_rejected` 不下发前端（`RadarSignalOut` 不加字段）；记 structlog 日志观测
  剔除分布（按过滤器名计数，`logger.debug`）。

### iOS（透明过滤 + 文案）

`SignalRadarView.rankingInfoLines` 追加两行 + `en.lproj/Localizable.strings`（中文 key 即显示文案）：

- 「形态过滤剔除假信号：信号出现当天若处于窄幅震荡、同向假突破或低波动，则不上榜。」
- 「详情页仍显示全部买卖点，形态过滤只影响雷达榜单。」

## 边界与错误处理

- **无未来函数**：形态信号逐根推进，历史日期查表均为当时可知状态。
- **K 线不足 w+n 根**：波动率分层跳过（`volatility="未知"`，不剔）。w 取 120（非
  初稿的 200）：分档值从第 ≈ w+130 根起产出（w=100~200 五点实测 220/240/250/270/320），
  w 越大产出越晚、500 根雷达窗口内有效覆盖越短；分层还需序列本身有波动率对比，
  波动恒定的序列（趋势+横盘合成）恒「其他」属正常退化，与 w 无关。
  read_shape_state 按截至当根的已见根数（`bars_seen`，含预热段）判断：不足
  w+n=130 根时置「未知」跳过，不依赖 czsc 对早期日期的退化输出，双保险不误杀。
- **示例日 / 补算**：`compute_demo_day`、`_backfill` 与全量扫描共用同一 `analyze` 路径，
  自动带过滤，无需单独处理。
- **性能**：每只成分股 CzscSignals 信号数从 ~4 增至 ~11，Rust 内核滚动计算。实测
  基线：`scan_bs_events` 500 根序列约 17ms → 81ms（+64ms/只，其中 ~42ms 为 Rust
  内核 7 个形态信号计算、~21ms 为 Python 侧逐根读取）；雷达数百只成分股增量约
  几十秒级，对分钟级全量扫描可接受；K线缓存不受影响。
- **th=10 校准**：实现时跑真实成分股数据看一类信号的剔除率，目标 10%~30%；过高调
  大 th，过低调小。

## 测试策略（TDD）

- `tests/services/chan/test_shape_filters.py`（新）：
  - 合成K线分别触发假突破 / 窄幅震荡 / 收盘位置 / 区间震荡取值 → `shape_states`
    逐日记录正确。
  - `reject_reason` 规则表：同向假突破剔、反向不剔；窄幅震荡剔；买点收盘
    高位 或 看多保留、中间+中性剔；低波动剔、未知跳过；区间震荡只剔一类。
  - K 线不足 → volatility=未知、不剔。
- `tests/services/signal_radar/test_shape_filter.py`（追加）：
  - `shape_rejected` 信号不上榜且**不回退旧信号**；缓存键 `:shape2:`；
    `result.signals` 不受影响（详情页口径守护）。
- 回归：`uv run pytest tests/services/signal_radar/ tests/services/chan/` 全绿；
  `make check` 通过。

## 明确不做（YAGNI）

- 不给 `RadarSignalOut` 加过滤原因字段、不做灰名单展示。
- 不做用户开关（避免按开关维度翻倍缓存）。
- 不把波动率分层 / 区间震荡做成排序加权（只做剔除）。
- 不改 signal_policy 口径体系（形态过滤是雷达展示层行为，不是「什么算买卖点」）。
