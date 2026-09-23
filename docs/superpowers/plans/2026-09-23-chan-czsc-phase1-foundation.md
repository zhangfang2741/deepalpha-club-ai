# 缠论接入 czsc（第一阶段：环境预检 + 适配层基础）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 czsc 接入到项目依赖里，验证它在本项目 Python 3.13 环境下能跑起来，并搭好 `bars(list[dict]) → czsc.RawBar → czsc.CZSC` 这条基础适配链路，为后续替换分型/笔/笔级别中枢打地基。

**Architecture:** 新增 `app/services/chan/czsc_adapter.py`，只做两件事：① 把我们的 `bars: list[dict]`（`time/open/high/low/close/volume`）转成 `czsc.RawBar` 列表；② 用这些 `RawBar` 构造 `czsc.CZSC` 对象并暴露出来。这一阶段不改动 `fractal.py`/`stroke.py`/`pivot.py`/`analyzer.py` 等现有文件，适配层先独立存在、独立测试，真正接线到 `analyzer.py` 是下一阶段计划的事。

**Tech Stack:** Python 3.13、uv、czsc（PyPI，Apache-2.0，Rust+PyO3 混合包）、pytest（`asyncio_mode=auto`，本计划全是同步代码不涉及 async）。

**范围说明：** 本计划只对应 spec `docs/superpowers/specs/2026-09-23-czsc-chan-refactor-design.md` 里"实现顺序"第 1 步（Spike）和第 2 步的前半部分（适配层基础）。信号目录（背驰/买卖点具体信号函数名）、`fx_list`/`bi_list`/`zs_list` 到我们自己 `Fractal`/`Stroke`/`Pivot` dataclass 的完整映射、替换 `fractal.py`/`stroke.py`/`pivot.py`、`czsc_signals.py` 买卖点引擎，都依赖 Task 1 spike 的实际运行结果（尤其是 220+ 信号函数编译在 Rust 里、没有可静态阅读的源码目录，必须实际装库后 `dir()`/`parse_signal_doc` 探测），因此**不在本计划内**，会在 Task 1 完成后另起一份计划。

---

### Task 1: 安装 czsc 并跑通环境预检 spike

**Files:**
- Modify: `pyproject.toml`（新增依赖）
- Create: `scripts/czsc_spike.py`（一次性探测脚本，跑完记录结论后可删除或保留供参考）
- Create: `docs/superpowers/specs/2026-09-23-czsc-spike-findings.md`（spike 发现记录，供下一阶段计划引用）

- [ ] **Step 1: 安装 czsc 依赖**

Run: `uv add czsc`

Expected: `pyproject.toml` 和 `uv.lock` 中新增 `czsc` 依赖，命令成功退出（退出码 0）。如果失败（比如没有 Python 3.13 的预编译 wheel、需要本地编译 Rust），**立即停止后续所有 Task，把报错信息记录到 spike 发现文档，这是本次重构的 go/no-go 前提**。

- [ ] **Step 2: 编写探测脚本**

创建 `scripts/czsc_spike.py`：

```python
"""czsc 接入 spike：验证基础可用性、探测真实字段类型、探测信号目录。

一次性脚本，运行后把输出整理进
docs/superpowers/specs/2026-09-23-czsc-spike-findings.md，不进入生产代码路径。
"""
from __future__ import annotations

import datetime as dt

from czsc import CZSC, Freq, RawBar


def _make_bars(n: int = 60) -> list[RawBar]:
    """构造一段可预测的合成 K 线：先涨后跌，保证能形成至少几笔和一个中枢。"""
    bars: list[RawBar] = []
    price = 100.0
    base_dt = dt.datetime(2024, 1, 1)
    for i in range(n):
        # 前 30 根上涨，后 30 根下跌，中间加小幅震荡制造分型
        if i < 30:
            delta = 1.0 if i % 3 != 0 else -0.3
        else:
            delta = -1.0 if i % 3 != 0 else 0.3
        open_ = price
        close = price + delta
        high = max(open_, close) + 0.2
        low = min(open_, close) - 0.2
        price = close
        bars.append(
            RawBar(
                symbol="TEST",
                dt=base_dt + dt.timedelta(days=i),
                freq=Freq.D,
                open=open_,
                close=close,
                high=high,
                low=low,
                vol=1000.0,
                amount=close * 1000.0,
                id=i,
            )
        )
    return bars


def main() -> None:
    bars = _make_bars()
    print(f"[1] 构造 RawBar 成功，数量={len(bars)}，dt 类型={type(bars[0].dt)}")

    c = CZSC(bars)
    print(f"[2] CZSC 构造成功：fx_list={len(c.fx_list)}, bi_list={len(c.bi_list)}, zs_list={len(c.zs_list)}")

    if c.fx_list:
        fx = c.fx_list[0]
        print(f"[3] FX 样例：mark={fx.mark}, dt类型={type(fx.dt)}, dt值={fx.dt}, high={fx.high}, low={fx.low}, fx={fx.fx}")

    if c.bi_list:
        bi = c.bi_list[0]
        print(
            f"[4] BI 样例：direction={bi.direction}, sdt={bi.sdt}({type(bi.sdt)}), "
            f"edt={bi.edt}, high={bi.high}, low={bi.low}, power={bi.power}, length={bi.length}"
        )

    if c.zs_list:
        zs = c.zs_list[0]
        print(f"[5] ZS 样例：zg={zs.zg}, zd={zs.zd}, gg={zs.gg}, dd={zs.dd}, bis数量={len(zs.bis)}")

    # 探测信号目录：找和背驰/买卖点相关的信号函数
    import czsc._native as native

    signals_ns = getattr(native, "signals", None)
    print(f"[6] czsc._native.signals 是否存在: {signals_ns is not None}")
    if signals_ns is not None:
        names = [n for n in dir(signals_ns) if not n.startswith("_")]
        print(f"[7] signals 命名空间下的子模块/函数数量: {len(names)}")
        print(f"[8] 子模块列表: {names}")

    # 用文档里出现过的信号函数名验证 generate_czsc_signals 能否正常跑
    from czsc import generate_czsc_signals

    try:
        seq = [
            "czsc._native.signals.bar.bar_end_V230331",
            "czsc._native.signals.cxt.cxt_bi_status_V230101",
        ]
        results = generate_czsc_signals(bars, seq)
        print(f"[9] generate_czsc_signals 跑通，返回类型={type(results)}")
        print(f"[10] 结果预览: {results[:3] if hasattr(results, '__getitem__') else results}")
    except Exception as e:  # noqa: BLE001  spike 脚本允许宽泛捕获，目的是记录报错信息
        print(f"[9-ERROR] generate_czsc_signals 调用失败: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 运行 spike 脚本，记录真实输出**

Run: `uv run python scripts/czsc_spike.py`

Expected: 脚本跑完不抛未捕获异常，打印出 `[1]` 到 `[10]`（或 `[9-ERROR]`）的全部探测结果。把完整终端输出原样保存下来（下一步要用）。

- [ ] **Step 4: 把探测结果整理成 spike 发现文档**

创建 `docs/superpowers/specs/2026-09-23-czsc-spike-findings.md`，内容包含（用 Step 3 的真实输出填写，不要编造）：

```markdown
# czsc 接入 spike 发现记录

日期：2026-09-23（实际运行日期以 git log 为准）

## 环境验证
- `uv add czsc` 是否成功：<填 Step 1 实际结果，含版本号>
- Python 3.13 + 本机环境是否用了预编译 wheel（无需本地 Rust 工具链）：<填实际情况>

## 数据类型确认
- `RawBar.dt` / `FX.dt` / `BI.sdt` 实际 Python 类型：<填 Step 3 输出，如 datetime/pd.Timestamp/字符串>
- `fx.mark` 的实际取值与比较方式（如 `fx.mark == Mark.G` 是否可行）：<填实际情况>

## 结构识别验证（合成数据）
- `CZSC(bars).fx_list/bi_list/zs_list` 数量：<填 Step 3 输出>
- `BI.direction` 取值：<填实际枚举值>

## 信号目录探测
- `czsc._native.signals` 命名空间下有哪些子模块：<填 Step 3 [8] 输出>
- `generate_czsc_signals` 用 README 给出的两个信号名（`bar_end_V230331`/`cxt_bi_status_V230101`）能否跑通，返回结构是什么：<填 Step 3 [9]/[10] 输出，如果报错记录报错信息>
- 背驰/买卖点相关信号函数的命名规律：<需要在 signals 命名空间下进一步搜索，比如是否有 `byi`/`beichi`/`mmd`（买卖点）相关子模块或函数名前缀，把找到的候选列出来>

## 结论：Go / No-Go
<基于以上，明确写出这次重构是否可行，如果有阻塞项写清楚是什么>
```

- [ ] **Step 5: 提交**

```bash
git add pyproject.toml uv.lock scripts/czsc_spike.py docs/superpowers/specs/2026-09-23-czsc-spike-findings.md
git commit -m "chore(chan): 接入 czsc 依赖并完成环境预检 spike"
```

---

### Task 2: RawBar 转换适配器

**Files:**
- Create: `app/services/chan/czsc_adapter.py`
- Test: `tests/services/chan/test_czsc_adapter.py`

- [ ] **Step 1: 写失败的测试**

创建 `tests/services/chan/test_czsc_adapter.py`：

```python
"""czsc 适配层单元测试：bars(list[dict]) -> czsc.RawBar 的转换。"""
from __future__ import annotations

from czsc import Freq

from app.services.chan.czsc_adapter import bars_to_raw_bars


def _bar(time: str, o: float, h: float, low: float, c: float, v: float = 1000.0) -> dict:
    return {"time": time, "open": o, "high": h, "low": low, "close": c, "volume": v}


def test_bars_to_raw_bars_preserves_ohlcv_and_order():
    bars = [
        _bar("2024-01-01", 10, 12, 9, 11, 500),
        _bar("2024-01-02", 11, 13, 10, 12.5, 600),
    ]
    raw_bars = bars_to_raw_bars(bars, symbol="TEST", freq=Freq.D)

    assert len(raw_bars) == 2
    assert raw_bars[0].symbol == "TEST"
    assert raw_bars[0].open == 10
    assert raw_bars[0].high == 12
    assert raw_bars[0].low == 9
    assert raw_bars[0].close == 11
    assert raw_bars[0].vol == 500
    assert raw_bars[0].id == 0
    assert raw_bars[1].id == 1


def test_bars_to_raw_bars_dt_is_chronologically_ordered():
    bars = [
        _bar("2024-01-01", 10, 12, 9, 11),
        _bar("2024-01-02", 11, 13, 10, 12.5),
    ]
    raw_bars = bars_to_raw_bars(bars, symbol="TEST", freq=Freq.D)

    assert raw_bars[0].dt < raw_bars[1].dt


def test_bars_to_raw_bars_empty_input_returns_empty_list():
    assert bars_to_raw_bars([], symbol="TEST", freq=Freq.D) == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/services/chan/test_czsc_adapter.py -v`
Expected: `FAIL`，报 `ModuleNotFoundError: No module named 'app.services.chan.czsc_adapter'`（文件还没创建）。

- [ ] **Step 3: 实现最小适配代码**

创建 `app/services/chan/czsc_adapter.py`：

```python
"""czsc 接入适配层：把项目内部 bars 格式转换为 czsc 原生对象。

只负责格式转换，不做任何缠论结构判断——结构判断交给 czsc 自身。
"""
from __future__ import annotations

import pandas as pd
from czsc import Freq, RawBar


def bars_to_raw_bars(bars: list[dict], *, symbol: str, freq: Freq) -> list[RawBar]:
    """把项目内部 bars（time/open/high/low/close/volume）转成 czsc.RawBar 列表。

    bars 必须已按时间升序排列（analyzer.py 现有调用方保证了这一点）。
    czsc.RawBar 没有对应"成交额"的数据源，amount 用 close*volume 近似。
    """
    raw_bars: list[RawBar] = []
    for idx, bar in enumerate(bars):
        raw_bars.append(
            RawBar(
                symbol=symbol,
                dt=pd.Timestamp(bar["time"]),
                freq=freq,
                open=float(bar["open"]),
                close=float(bar["close"]),
                high=float(bar["high"]),
                low=float(bar["low"]),
                vol=float(bar["volume"]),
                amount=float(bar["close"]) * float(bar["volume"]),
                id=idx,
            )
        )
    return raw_bars
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/services/chan/test_czsc_adapter.py -v`
Expected: `PASS`（3 个测试全部通过）。

- [ ] **Step 5: 提交**

```bash
git add app/services/chan/czsc_adapter.py tests/services/chan/test_czsc_adapter.py
git commit -m "feat(chan): 添加 bars 到 czsc.RawBar 的转换适配器"
```

---

### Task 3: CZSC 对象构造与原始结构访问

**Files:**
- Modify: `app/services/chan/czsc_adapter.py`
- Test: `tests/services/chan/test_czsc_adapter.py`

- [ ] **Step 1: 写失败的测试**

在 `tests/services/chan/test_czsc_adapter.py` 末尾追加：

```python
from app.services.chan.czsc_adapter import build_czsc


def _trending_bars(n: int, start_price: float, up: bool) -> list[dict]:
    """构造一段单调趋势（略带波动以形成分型），用于验证 CZSC 能识别出笔。"""
    bars = []
    price = start_price
    for i in range(n):
        step = 1.0 if (up and i % 4 != 0) or (not up and i % 4 == 0) else -1.0
        o = price
        c = price + step
        h = max(o, c) + 0.3
        low_ = min(o, c) - 0.3
        price = c
        bars.append(_bar(f"2024-01-{i + 1:02d}" if i < 28 else f"2024-02-{i - 27:02d}", o, h, low_, c))
    return bars


def test_build_czsc_returns_object_with_structure_lists():
    bars = _trending_bars(40, start_price=100.0, up=True)
    c = build_czsc(bars, symbol="TEST", freq=Freq.D)

    assert c.symbol == "TEST"
    assert isinstance(c.fx_list, list)
    assert isinstance(c.bi_list, list)
    assert isinstance(c.zs_list, list)
    # 40 根波动 K 线足够形成至少一笔
    assert len(c.bi_list) >= 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/services/chan/test_czsc_adapter.py::test_build_czsc_returns_object_with_structure_lists -v`
Expected: `FAIL`，报 `ImportError: cannot import name 'build_czsc'`。

- [ ] **Step 3: 实现 build_czsc**

在 `app/services/chan/czsc_adapter.py` 追加：

```python
from czsc import CZSC


def build_czsc(bars: list[dict], *, symbol: str, freq: Freq, min_bi_len: int = 0) -> CZSC:
    """构造 czsc.CZSC 分析对象。

    一次性喂入完整 bars 序列（不走流式 update），这样才能复用现有的
    「warmup + visible_from 窗口锚定后裁剪」调用方式：调用方在可见窗口前
    多取一段 warmup K 线一起传进来，本函数不关心窗口裁剪，裁剪逻辑在
    上层 analyzer.py 里做（后续计划的范围）。
    """
    raw_bars = bars_to_raw_bars(bars, symbol=symbol, freq=freq)
    return CZSC(raw_bars, min_bi_len=min_bi_len)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/services/chan/test_czsc_adapter.py -v`
Expected: `PASS`（全部测试通过，含 Task 2 的 3 个 + 本 Task 的 1 个）。

- [ ] **Step 5: 跑一次全量缠论测试确认没有破坏现有功能**

Run: `uv run pytest tests/services/chan/ -v`
Expected: 除新增的 `test_czsc_adapter.py` 外，其余现有测试全部保持 `PASS`（本阶段未改动 `fractal.py`/`stroke.py`/`pivot.py`/`analyzer.py`，不应有回归）。

- [ ] **Step 6: 提交**

```bash
git add app/services/chan/czsc_adapter.py tests/services/chan/test_czsc_adapter.py
git commit -m "feat(chan): 添加 czsc.CZSC 对象构造入口"
```

---

## 本计划完成后的状态

- czsc 已作为正式依赖接入项目，且验证过 Python 3.13 环境可用（或者在 Task 1 就发现不可用并停止——这是本计划最重要的产出之一）。
- `app/services/chan/czsc_adapter.py` 能把项目的 bars 转成 czsc 能理解的 `RawBar`，并构造出 `CZSC` 对象，拿到 `fx_list`/`bi_list`/`zs_list`。
- `docs/superpowers/specs/2026-09-23-czsc-spike-findings.md` 记录了真实的 dt 类型、信号目录探测结果，这些是下一阶段计划（把 `fx_list`/`bi_list`/`zs_list` 映射成我们自己的 `Fractal`/`Stroke`/`Pivot`，替换 `fractal.py`/`stroke.py`/`pivot.py`，实现 `czsc_signals.py` 买卖点引擎）的输入。
- `analyzer.py`、`fractal.py`、`stroke.py`、`pivot.py`、`segment.py`、`divergence.py`、`signals.py`、前端、LangGraph tools **均未改动**，现有功能不受影响。
