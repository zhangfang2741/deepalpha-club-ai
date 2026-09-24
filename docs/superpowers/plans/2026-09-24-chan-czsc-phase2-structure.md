# 缠论接入 czsc（第二阶段：结构识别引擎）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `analyzer.py` 的结构识别（分型/笔/笔级中枢）从自研算法切换到 czsc 引擎，线段/线段级中枢/线段级背驰保留自研（输入换源），对外 schema 完全不变。

**Architecture:** `czsc_adapter.py` 新增 `extract_structures()`：输入 `czsc.CZSC` 对象 + 原始 bars，输出转换回现有 `Fractal`/`Stroke`/`Pivot`/`MergedCandle` dataclass 的四元组。`analyzer.py` 步骤 1-5 改调 adapter，之后的线段/线段中枢/MACD/背驰/买卖点流程不动（dataclass 形状未变，自研下游代码直接消费新数据）。买卖点整体换 czsc signal 体系是第三阶段，不在本计划。

**Tech Stack:** Python 3.13、uv、czsc 1.0.1（已接入）、pytest。

**已验证的 czsc 运行时行为（2026-09-24 第二轮探测，可直接依赖）**：
- `fx.mark == Mark.G` / `bi.direction == Direction.Up` 可直接比较；`.name` 给英文（"G"/"D"/"Up"/"Down"），`.value` 给中文。
- `FX.dt`、`BI.sdt/edt`、`ZS.sdt/edt` 均为 `pd.Timestamp`；`pd.Timestamp(bar['time'])` 构造后 `strftime('%Y-%m-%d')` 可无损还原原始 time 字符串。
- `FX.elements` 是构成分型的 3 根 `NewBar`（去包含K线）；`NewBar.elements` 是被合并的原始 `RawBar` 列表（有 `id` 属性，对应输入序列下标）。
- `CZSC.bars_ubi` 是去包含K线序列（`list[NewBar]`），`NewBar.dt` 在序列内唯一。
- `ZS.bis` 是构成中枢的 `BI` 列表；`zs.sdt == zs.bis[0].sdt`。
- bars 的 `time` 格式为 `"YYYY-MM-DD"`（日线/周线聚合后都是日期字符串）。

**关键映射语义（设计决定，实现时照此执行）**：
- `MergedCandle.idx`：以 `bars_ubi` 的列表位置为 idx（`{nb.dt: pos}` 建映射）；`raw_start/raw_end` 取 `nb.elements[0].id` / `nb.elements[-1].id`；`time` 取 `nb.elements[-1]` 对应原始 bar 的 time 字符串（`id→time` 由输入 bars 建映射）。
- `Fractal`：`type` 由 `fx.mark`（G→top / D→bottom）；`candle/left/right` 取 `fx.elements[1]/[0]/[2]` 转成的 MergedCandle；`idx`/`time`/`price` 均为派生属性，无需额外字段。
- `Stroke`：`direction` 由 `bi.direction`（Up→up）；`start/end` 取 `bi.fx_a/fx_b` 转成的 Fractal；`confirmed` 先全部置 True，由 `analyzer._mark_confirmations` 统一重算（现有逻辑基于「最后一笔未确认」原则，对 czsc 输出同样成立且更保守）。
- `Pivot`（笔级）：`zg/zd/gg/dd` 直接取 `zs.*`；`start_time/end_time` 取 `zs.bis[0].fx_a.dt` / `zs.bis[-1].fx_b.dt` 转 `YYYY-MM-DD`（不能用 `zs.sdt/edt`——`sdt` 是第一笔起点分型时间，与自研 Pivot 的 `start_time`（首元素起点）语义一致，实测两者等价，但用 `bis[0].fx_a.dt` 表达更直白）；`level="stroke"`；`elements` 通过 `bi.fx_a.dt` 与已转换 strokes 的 `start.time` 匹配。
- `analyze()` 新增 `freq: str = "daily"` 参数（"daily"/"weekly" → `Freq.D`/`Freq.W`），API 层 `app/api/v1/chan.py` 两处调用传入；`min_gap` 参数保留签名但不再影响结构识别（czsc 的成笔规则由其内部 `min_bi_len` 决定，默认 0 即 czsc 缺省），docstring 注明。

---

### Task 1: adapter 完整结构映射 extract_structures

**Files:**
- Modify: `app/services/chan/czsc_adapter.py`
- Test: `tests/services/chan/test_czsc_adapter.py`

- [ ] **Step 1: 写失败的测试**（追加到 test_czsc_adapter.py）

测试数据复用已验证能成笔的大振幅锯齿生成器 `_trending_bars`（80 根，先涨后跌造出 ≥1 个中枢）。断言：
1. 返回的 fractals 顶底分型 `type` 正确、`price` 取 mid candle 对应端、`candle/left/right` 是相邻三根 MergedCandle。
2. strokes 相邻首尾相连（`strokes[i].end is strokes[i+1].start` 或 time 相等）、方向交替。
3. 上升笔 `start.type == "bottom"` 且 `end.type == "top"`。
4. 每根 stroke 的 `start_time/end_time` 是 `YYYY-MM-DD` 格式且在输入 bars 的 time 集合内。
5. stroke_pivots 的 `zg > zd`、`level == "stroke"`、`elements` 与 strokes 是同一对象（identity 相等）。
6. merged_candles 的 `raw_start <= raw_end`、`idx` 严格递增、相邻两根无包含关系（high/low 不互相包含）。
7. 时间单调：merged_candles、strokes 的 time 均随 idx 递增。

```python
def test_extract_structures_maps_to_existing_dataclasses():
    bars = _trending_bars(80, start_price=100.0, up=True)
    c = build_czsc(bars, symbol="TEST", freq=Freq.D)
    structures = extract_structures(c, bars)

    times = {b["time"] for b in bars}
    # 分型
    for f in structures.fractals:
        assert f.type in ("top", "bottom")
        assert f.price == (f.candle.high if f.type == "top" else f.candle.low)
        assert f.left.idx + 1 == f.candle.idx == f.right.idx - 1
        assert f.time in times
    # 笔：首尾相连 + 方向交替
    for a, b in zip(structures.strokes, structures.strokes[1:]):
        assert a.end.time == b.start.time
        assert a.direction != b.direction
    for s in structures.strokes:
        assert s.start_time in times and s.end_time in times
        if s.direction == "up":
            assert s.start.type == "bottom" and s.end.type == "top"
            assert s.end_price > s.start_price
        else:
            assert s.start.type == "top" and s.end.type == "bottom"
            assert s.end_price < s.start_price
    # 笔级中枢
    for p in structures.stroke_pivots:
        assert p.zg > p.zd
        assert p.level == "stroke"
        assert all(any(el is s for s in structures.strokes) for el in p.elements)
    # 合并K线
    mcs = structures.merged_candles
    assert [mc.idx for mc in mcs] == list(range(len(mcs)))
    for a, b in zip(mcs, mcs[1:]):
        assert not (a.high >= b.high and a.low <= b.low)
        assert not (b.high >= a.high and b.low <= a.low)
        assert a.time < b.time
        assert a.raw_start <= a.raw_end
```

- [ ] **Step 2: 跑测试确认失败**（`ImportError: cannot import name 'extract_structures'`）

- [ ] **Step 3: 实现 extract_structures**

```python
@dataclass
class CzscStructures:
    """czsc 结构转换结果：形状与 ChanAnalysisResult 前几步产物一致。"""
    merged_candles: list[MergedCandle]
    fractals: list[Fractal]
    strokes: list[Stroke]
    stroke_pivots: list[Pivot]


def _ts_date(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def extract_structures(c: CZSC, bars: list[dict]) -> CzscStructures:
    """把 czsc 的分型/笔/笔级中枢转换回项目内部 dataclass。

    时间字符串一律从输入 bars 的 time 还原（通过 RawBar.id 映射），
    保证与 _clip_to_window 的字符串比较语义一致。
    """
    time_by_id = {i: b["time"] for i, b in enumerate(bars)}

    # 去包含K线 → MergedCandle（idx 用 bars_ubi 列表位置）
    pos_by_dt = {nb.dt: pos for pos, nb in enumerate(c.bars_ubi)}
    def nb_to_candle(nb) -> MergedCandle:
        raw = nb.elements
        return MergedCandle(
            idx=pos_by_dt[nb.dt],
            time=time_by_id[raw[-1].id],
            open=float(raw[0].open), close=float(raw[-1].close),
            high=float(nb.high), low=float(nb.low),
            raw_start=raw[0].id, raw_end=raw[-1].id,
        )
    merged = [nb_to_candle(nb) for nb in c.bars_ubi]

    def fx_to_fractal(fx) -> Fractal:
        left, mid, right = (nb_to_candle(nb) for nb in fx.elements)
        return Fractal(type="top" if fx.mark == Mark.G else "bottom",
                       candle=mid, left=left, right=right)

    fractals = [fx_to_fractal(fx) for fx in c.fx_list]

    def bi_to_stroke(bi) -> Stroke:
        direction = "up" if bi.direction == Direction.Up else "down"
        return Stroke(direction=direction, start=fx_to_fractal(bi.fx_a),
                      end=fx_to_fractal(bi.fx_b))

    strokes = [bi_to_stroke(bi) for bi in c.bi_list]
    stroke_by_start_time: dict[str, Stroke] = {}
    for s in strokes:
        stroke_by_start_time.setdefault(s.start_time, s)

    pivots = []
    for zs in c.zs_list:
        elements = [stroke_by_start_time[_ts_date(bi.fx_a.dt)] for bi in zs.bis]
        pivots.append(Pivot(
            zg=float(zs.zg), zd=float(zs.zd), gg=float(zs.gg), dd=float(zs.dd),
            start_time=_ts_date(zs.bis[0].fx_a.dt),
            end_time=_ts_date(zs.bis[-1].fx_b.dt),
            level="stroke", elements=elements,
        ))

    return CzscStructures(merged_candles=merged, fractals=fractals,
                          strokes=strokes, stroke_pivots=pivots)
```

注意：`Mark`/`Direction` 需要从 `czsc` 导入；`Fractal`/`MergedCandle`/`Stroke`/`Pivot` 从对应自研模块导入（本阶段这些 dataclass 定义仍保留在原文件）。

- [ ] **Step 4: 跑测试确认通过**（若 czsc 实际输出的 `FX.elements` 不是恰好 3 根 NewBar，按实际结构调整 `fx_to_fractal`，但必须保持对外行为断言不变）
- [ ] **Step 5: 提交** `feat(chan): czsc 结构完整映射到现有 dataclass`

### Task 2: analyzer 改接 czsc + 清理自研结构算法

**Files:**
- Modify: `app/services/chan/analyzer.py`（步骤 1-5）、`app/services/chan/fractal.py`、`stroke.py`、`pivot.py`（删除函数、保留 dataclass）、`app/api/v1/chan.py`（传 freq）
- Delete/rewrite tests: `tests/services/chan/test_fractal.py`、`test_stroke.py`、`test_pivot.py` 中针对已删函数的用例

- [ ] **Step 1**: `analyze()` 签名加 `freq: str = "daily"`；开头 `bars < 10` / `fractals < 2` / `strokes < 3` 的早退分支保留，但计数改为基于 `extract_structures` 的结果。步骤 1-5 替换为：

```python
czsc_obj = build_czsc(bars, symbol=symbol, freq=Freq.D if freq == "daily" else Freq.W)
structures = extract_structures(czsc_obj, bars)
result.merged_candles = structures.merged_candles
result.fractals = structures.fractals
result.strokes = structures.strokes
```

分型不足/笔不足的早退判断用 `structures.fractals`/`structures.strokes`；线段/线段中枢（`find_segments`/`find_segment_pivots`）、MACD、背驰、买卖点、确认标注、裁剪、叙事全部不动。`find_stroke_pivots` 调用点替换为 `structures.stroke_pivots`。`min_gap` 参数保留但 docstring 注明已废弃（czsc 内部规则决定）。
- [ ] **Step 2**: `fractal.py`/`stroke.py` 删除 `merge_candles`/`find_fractals`/`find_strokes` 及私有辅助（保留 `MergedCandle`/`Fractal`/`Stroke` dataclass）；`pivot.py` 删除 `find_stroke_pivots` 及其私有辅助（保留 `Pivot`、`find_segment_pivots`、`classify_walk_type`）。
- [ ] **Step 3**: `app/api/v1/chan.py` 两处 `analyze(...)` 调用加 `freq=...`（gap 端点用 body.freq）。
- [ ] **Step 4**: 更新测试：删除针对已删函数的用例；`test_window_anchor.py`/`test_confirmations.py`/`test_trend_outlook.py`/`test_recommendation.py`/`test_narrative.py`/`test_pivot_phase.py`/`test_replay.py`/`test_structure_layers.py`/`test_divergence.py`/`test_signals.py` 若基于旧算法的具体结构断言失败，按 czsc 实际行为调整期望（不变量类断言如「笔首尾相连」「中枢zg>zd」应保留）。
- [ ] **Step 5**: 全量 `uv run pytest tests/services/chan/ -v` + `make check` 通过后提交 `refactor(chan): 分型/笔/笔级中枢识别切换到 czsc 引擎`

### Task 3: 真实数据核对 + 收尾

- [ ] **Step 1**: 本地起后端 `make dev`，curl `GET /api/v1/chan/analysis?symbol=AAPL&freq=daily`（及几只熟悉的股票 NVDA/MSFT/腾讯等），肉眼核对响应里 strokes/segments/stroke_pivots/segment_pivots 数量合理、时间/价格无 NaN、divergences/signals 正常产出（仍走旧逻辑，验证数据形状兼容）。
- [ ] **Step 2**: `uv run pytest tests/`（全仓库）+ `make check` 全绿后提交并合并推送 master。
