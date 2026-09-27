# 信号雷达形态过滤实施计划（czsc 形态信号剔除假信号）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 czsc 内核的 7 个形态过滤信号（假突破/窄幅震荡×2/收盘位置×2/波动率分层/区间震荡）接入信号雷达，在信号出生时（信号所属笔终点日）一次判定、命中即剔除，只影响雷达榜单，详情页口径不动。

**Architecture:** `scan_bs_events` 一次逐根推进同时产出买卖点事件与逐日形态状态 `shape_states`（与现有 `stroke_done_at` 同构）；`ChanAnalyzer.analyze` 通过 `shape_filters=True` 开启（仅雷达路径）；雷达 `build_signal_history` 给 `RawSignal` 标记 `shape_rejected`，`build_days` 在每-symbol 最新信号确定后丢弃被剔信号（防旧信号顶替上榜）；缓存键 `:shape1:` → `:shape2:`。

**Tech Stack:** Python 3.13 + uv、czsc 1.0.1（Rust 内核，`CzscSignals` 逐根推进）、pytest、SwiftUI（仅文案）。

**设计文档:** `docs/superpowers/specs/2026-09-27-radar-shape-filters-design.md`

---

## 背景知识（执行前必读）

1. **czsc 信号键与取值**（已实测确认，键名由 config 参数渲染，`label` 对日线为 `"日线"`）：

   | config 项 | 信号键 | v1 取值（`cs.s[key].split("_")[0]`） |
   | --- | --- | --- |
   | `{"name": "bar_fake_break_V230204", "freq": label, "di": 1, "n": 20, "m": 5}` | `日线_D1N20M5_假突破`（实测不带版本后缀，其余键都带） | `看空`(=向上假突破) / `看多`(=向下假突破) / `其他` |
   | `{"name": "bar_volatility_V241013", "freq": label, "w": 200, "n": 10}` | `日线_波动率分层W200N10_完全分类V241013` | `低波动` / `中波动` / `高波动` |
   | `{"name": "bar_zfzd_V241013", "freq": label, "n": 10}` | `日线_窄幅震荡N10_形态V241013` | `满足` / `其他` |
   | `{"name": "bar_zfzd_V241014", "freq": label, "n": 10}` | `日线_窄幅震荡N10_形态V241014` | `满足` / `其他` |
   | `{"name": "bar_classify_V240606", "freq": label, "di": 1}` | `日线_D1收盘位置_分类V240606` | `高位` / `中间` / `低位` |
   | `{"name": "bar_classify_V240607", "freq": label, "di": 1}` | `日线_D1K2收盘位置_分类V240607` | `看多` / `看空` / `中性` |
   | `{"name": "cxt_range_oscillation_V230620", "freq": label, "di": 1, "th": 10}` | `日线_D1TH10_区间震荡V230620` | `X笔震荡` / `其他` |

2. **波动率分层的坑**：czsc 内部对数据不足会退化输出（NaN 按 0 分层），所以「K 线总数 < w+n（210）根」必须由我们显式跳过、置 `volatility="未知"`，不能信 czsc 的输出。
3. **czsc 逐根推进模式**：见 `app/services/chan/czsc_signals.py` 的 `scan_bs_events`——`BarGenerator` 预热前 20 根（`_INIT_N`），其余逐根 `cs.update_signals(bar)` 后读 `cs.s`。形态状态从第 21 根起才有记录；czsc 一买至少需要 5 笔，前 20 根不可能有信号，查询缺失返回 None 不剔除（防误杀）。
4. **项目规则**：全中文注释/提交信息；`uv run pytest` 跑测试；提交信息 `feat/fix/refactor(scope): 描述`；每任务一提交。

## 文件结构

- Create: `app/services/chan/shape_filters.py` — ShapeState、参数常量、config、读取与规则判定（纯函数，可独立测试）
- Create: `tests/services/chan/test_shape_filters.py`
- Modify: `app/services/chan/czsc_signals.py` — `scan_bs_events` 加 `shape_states` 传出参数
- Modify: `app/services/chan/analyzer.py` — `ChanAnalysisResult.shape_states` 字段 + `analyze(shape_filters=)`
- Modify: `app/services/signal_radar/service.py` — RawSignal.shape_rejected / build_signal_history 标记 / build_days 过滤 / `_scan_symbol` 开启 / 缓存键 shape2
- Modify: `tests/services/signal_radar/test_shape_filter.py` — 追加雷达层测试
- Modify: `ios/DeepAlphaChan/Views/SignalRadar/SignalRadarView.swift`、`ios/DeepAlphaChan/Resources/en.lproj/Localizable.strings` — 透明过滤说明文案（zh-Hans 不用改：key 即中文，查不到回退 key 本身）

---

### Task 1: `shape_filters.py` — ShapeState 与 reject_reason 规则判定

**Files:**

- Create: `app/services/chan/shape_filters.py`
- Test: `tests/services/chan/test_shape_filters.py`

- [ ] **Step 1: 写失败测试（reject_reason 规则表）**

创建 `tests/services/chan/test_shape_filters.py`：

```python
"""形态过滤：czsc 形态信号 → 雷达剔除规则（纯函数部分）。"""
import pytest

from app.services.chan.shape_filters import ShapeState, reject_reason


def _state(**kwargs) -> ShapeState:
    """构造一个「全部不触发剔除」的基准形态状态，测试里按需覆盖字段。"""
    base = dict(
        fake_break="其他", narrow_range=False,
        close_pos="高位", k2_close_pos="看多",
        volatility="中波动", range_osc="其他",
    )
    base.update(kwargs)
    return ShapeState(**base)


@pytest.mark.parametrize("kwargs", [{"close_pos": "中间"}, {"k2_close_pos": "中性"},
                                    {"close_pos": "低位", "k2_close_pos": "看多"},
                                    {"close_pos": "高位", "k2_close_pos": "看空"}])
def test_buy_kept_when_either_close_signal_strong(kwargs: dict) -> None:
    """买点：收盘位置高位、K2 看多，任一满足即保留。"""
    assert reject_reason(_state(**kwargs), "buy1") is None


def test_buy_rejected_when_both_close_signals_weak() -> None:
    state = _state(close_pos="中间", k2_close_pos="中性")
    assert reject_reason(state, "buy3") == "收盘位置"


def test_sell_kept_when_either_close_signal_weak() -> None:
    assert reject_reason(_state(close_pos="低位"), "sell1") is None
    assert reject_reason(_state(k2_close_pos="看空"), "sell2") is None


def test_sell_rejected_when_both_close_signals_strong() -> None:
    state = _state(close_pos="高位", k2_close_pos="看多")
    assert reject_reason(state, "sell1") == "收盘位置"


def test_buy_rejected_on_upward_fake_break_only() -> None:
    """买点剔除向上假突破（看空）；向下假突破（看多）常是买点自身形态，不剔。"""
    assert reject_reason(_state(fake_break="看空"), "buy1") == "假突破"
    assert reject_reason(_state(fake_break="看多"), "buy1") is None


def test_sell_rejected_on_downward_fake_break_only() -> None:
    assert reject_reason(_state(fake_break="看多"), "sell1") == "假突破"
    assert reject_reason(_state(fake_break="看空"), "sell1") is None


def test_narrow_range_rejects_all_types() -> None:
    for t in ("buy1", "buy2", "buy3", "sell1", "sell2", "sell3"):
        assert reject_reason(_state(narrow_range=True), t) == "窄幅震荡"


def test_low_volatility_rejects_all_types() -> None:
    for t in ("buy1", "sell3"):
        assert reject_reason(_state(volatility="低波动"), t) == "低波动"


def test_unknown_volatility_never_rejects() -> None:
    """K 线不足导致波动率未知时跳过该过滤，不误杀。"""
    for t in ("buy1", "sell1"):
        assert reject_reason(_state(volatility="未知"), t) is None


@pytest.mark.parametrize("signal_type", ["buy1", "sell1"])
def test_range_oscillation_rejects_first_bs_only(signal_type: str) -> None:
    """一类买卖点额外要求趋势环境：区间震荡中的一类剔除，二 / 三类保留。"""
    assert reject_reason(_state(range_osc="3笔震荡"), signal_type) == "区间震荡"
    assert reject_reason(_state(range_osc="3笔震荡"), "buy2") is None
    assert reject_reason(_state(range_osc="3笔震荡"), "sell3") is None


def test_none_state_never_rejects() -> None:
    """形态状态缺失（如信号日早于预热段）不剔除，防误杀。"""
    assert reject_reason(None, "buy1") is None


def test_rules_short_circuit_in_documented_order() -> None:
    """多条件同时命中时返回首个（假突破 > 窄幅震荡 > 收盘位置 > 低波动 > 区间震荡）。"""
    state = _state(fake_break="看空", narrow_range=True, close_pos="中间",
                   k2_close_pos="中性", volatility="低波动", range_osc="3笔震荡")
    assert reject_reason(state, "buy1") == "假突破"
    assert reject_reason(_state(narrow_range=True, close_pos="中间"), "buy1") == "窄幅震荡"
    assert reject_reason(_state(close_pos="中间", volatility="低波动"), "buy1") == "收盘位置"
    assert reject_reason(_state(volatility="低波动", range_osc="3笔震荡"), "buy1") == "低波动"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/services/chan/test_shape_filters.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.services.chan.shape_filters'`）

- [ ] **Step 3: 写最小实现**

创建 `app/services/chan/shape_filters.py`：

```python
"""雷达形态过滤：czsc 形态信号 → 逐日形态状态 → 剔除规则。

只服务信号雷达的「假信号剔除」（设计见
docs/superpowers/specs/2026-09-27-radar-shape-filters-design.md），
不改变详情页买卖点口径。五条规则（按短路顺序）：

1. 假突破（bar_fake_break_V230204）：买点日=向上假突破（看空）剔、卖点日=向下
   假突破（看多）剔；反向假突破（跌破后收回）常正是一 / 二买自身形态，不剔。
2. 窄幅震荡（bar_zfzd_V241013 / V241014 任一满足）：横盘里没有可做的买卖点，剔。
3. 收盘位置（bar_classify_V240606 / V240607）：买点须收盘偏强（高位 或 看多，
   任一即可）、卖点须偏弱（低位 或 看空），否则剔。
4. 波动率分层（bar_volatility_V241013）：低波动组的信号质量差，剔；K 线不足
   w+n 根（三分位退化）时置「未知」跳过，不误杀。
5. 区间震荡（cxt_range_oscillation_V230620）：一类买卖点需要趋势前提，信号当天
   处于笔级区间震荡中的一类剔除；二 / 三类保留。

形态信号逐根推进、不回看未来，按「信号所属笔终点日」查表即为当时可知信息，
无未来函数。
"""
from __future__ import annotations

from dataclasses import dataclass

from czsc import CzscSignals

# czsc 形态信号参数（键名由这些参数渲染，改参数必须同步 read_shape_state 的键）。
_FAKE_BREAK_N = 20
_FAKE_BREAK_M = 5
_NARROW_N = 10
_VOLATILITY_W = 200
_VOLATILITY_N = 10
_RANGE_OSC_TH = 10  # czsc 默认 th=2（2% 中心振幅）对美股日线几乎不触发，取 10

_FIRST_BS = ("buy1", "sell1")


@dataclass(frozen=True)
class ShapeState:
    """某根K线（= 某个交易日）当时的形态状态。"""

    fake_break: str = "其他"    # 看多=向下假突破 / 看空=向上假突破 / 其他
    narrow_range: bool = False  # 窄幅震荡（V241013 / V241014 任一满足）
    close_pos: str = "中间"     # 高位 / 中间 / 低位
    k2_close_pos: str = "中性"  # 看多 / 看空 / 中性
    volatility: str = "未知"    # 低波动 / 中波动 / 高波动 / 未知（K 线不足）
    range_osc: str = "其他"     # X笔震荡 / 其他


def shape_config(label: str) -> list[dict]:
    """追加进 CzscSignals 的形态信号 config（与买卖点信号共用一次逐根推进）。"""
    return [
        {"name": "bar_fake_break_V230204", "freq": label, "di": 1,
         "n": _FAKE_BREAK_N, "m": _FAKE_BREAK_M},
        {"name": "bar_volatility_V241013", "freq": label,
         "w": _VOLATILITY_W, "n": _VOLATILITY_N},
        {"name": "bar_zfzd_V241013", "freq": label, "n": _NARROW_N},
        {"name": "bar_zfzd_V241014", "freq": label, "n": _NARROW_N},
        {"name": "bar_classify_V240606", "freq": label, "di": 1},
        {"name": "bar_classify_V240607", "freq": label, "di": 1},
        {"name": "cxt_range_oscillation_V230620", "freq": label,
         "di": 1, "th": _RANGE_OSC_TH},
    ]


def read_shape_state(cs: CzscSignals, label: str, *, total_bars: int) -> ShapeState:
    """从逐根推进到当根的 CzscSignals 读出当日形态状态。

    total_bars 是本次推进的K线总数（不是已推进根数）：波动率分层需要 w+n 根
    缓存才有意义，不足时 czsc 会基于退化数据照常输出某档，必须显式置「未知」。
    """
    def v1(key: str) -> str:
        return cs.s.get(key, "其他_任意_任意_0").split("_")[0]

    narrow = (v1(f"{label}_窄幅震荡N{_NARROW_N}_形态V241013") == "满足"
              or v1(f"{label}_窄幅震荡N{_NARROW_N}_形态V241014") == "满足")
    volatility = ("未知" if total_bars < _VOLATILITY_W + _VOLATILITY_N else
                  v1(f"{label}_波动率分层W{_VOLATILITY_W}N{_VOLATILITY_N}_完全分类V241013"))
    return ShapeState(
        fake_break=v1(f"{label}_D1N{_FAKE_BREAK_N}M{_FAKE_BREAK_M}_假突破V230204"),
        narrow_range=narrow,
        close_pos=v1(f"{label}_D1收盘位置_分类V240606"),
        k2_close_pos=v1(f"{label}_D1K2收盘位置_分类V240607"),
        volatility=volatility,
        range_osc=v1(f"{label}_D1TH{_RANGE_OSC_TH}_区间震荡V230620"),
    )


def reject_reason(state: ShapeState | None, signal_type: str) -> str | None:
    """按五条规则判定一条买卖点是否该被雷达剔除，返回首个命中的过滤器名。

    state 为 None（信号日早于逐根推进起点、查不到形态状态）时不剔除，防误杀。
    """
    if state is None:
        return None
    is_buy = signal_type.startswith("buy")
    if is_buy and state.fake_break == "看空":
        return "假突破"
    if not is_buy and state.fake_break == "看多":
        return "假突破"
    if state.narrow_range:
        return "窄幅震荡"
    if is_buy:
        if state.close_pos != "高位" and state.k2_close_pos != "看多":
            return "收盘位置"
    elif state.close_pos != "低位" and state.k2_close_pos != "看空":
        return "收盘位置"
    if state.volatility == "低波动":
        return "低波动"
    if signal_type in _FIRST_BS and state.range_osc != "其他":
        return "区间震荡"
    return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/services/chan/test_shape_filters.py -q`
Expected: PASS（全部用例）

- [ ] **Step 5: 提交**

```bash
git add app/services/chan/shape_filters.py tests/services/chan/test_shape_filters.py
git commit -m "feat(chan): 形态过滤 ShapeState 与五条剔除规则（纯函数）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: `read_shape_state` 与 `scan_bs_events` 集成（逐日形态状态）

**Files:**

- Modify: `app/services/chan/czsc_signals.py`
- Test: `tests/services/chan/test_shape_filters.py`（追加）

- [ ] **Step 1: 写失败测试（追加到 `tests/services/chan/test_shape_filters.py`）**

```python
# ---- 逐根推进集成：scan_bs_events 产出 shape_states ----
from datetime import date, timedelta

from app.services.chan.czsc_adapter import ts_date
from app.services.chan.czsc_signals import scan_bs_events
from czsc import Freq


def _bars(seq: list[tuple[float, float, float, float]]) -> list[dict]:
    """(open, high, low, close) 四元组序列 → 标准日线 dict，日期从 2025-01-01 起。"""
    return [
        {"time": (date(2025, 1, 1) + timedelta(days=i)).isoformat(),
         "open": o, "high": h, "low": low, "close": c, "volume": 1000}
        for i, (o, h, low, c) in enumerate(seq)
    ]


def _trend_then_flat(n_flat: int = 14) -> list[dict]:
    """40 根趋势 + n_flat 根窄幅横盘：横盘段应触发窄幅震荡。"""
    seq: list[tuple[float, float, float, float]] = []
    p = 100.0
    for _ in range(40):
        seq.append((p, p + 0.6, p - 0.2, p + 0.5))
        p += 0.5
    for _ in range(n_flat):
        seq.append((p, p + 0.05, p - 0.05, p + 0.01))
    return _bars(seq)


def test_scan_bs_events_records_shape_states_per_day() -> None:
    bars = _trend_then_flat()
    states: dict[str, ShapeState] = {}
    scan_bs_events(bars, symbol="TEST", freq=Freq.D, shape_states=states)
    # 逐根推进从第 21 根开始，每天（含周末合成日期）都有一条状态
    assert len(states) == len(bars) - 20
    # 窄幅横盘段（最后一根一定在横盘中）触发窄幅震荡
    last_day = bars[-1]["time"]
    assert states[last_day].narrow_range is True
    # 趋势段中段不触发
    mid_day = bars[30]["time"]
    assert states[mid_day].narrow_range is False


def test_shape_states_volatility_unknown_when_bars_insufficient() -> None:
    """K 线不足 w+n（210）根：波动率一律「未知」，不信 czsc 的退化输出。"""
    bars = _trend_then_flat(n_flat=30)
    states: dict[str, ShapeState] = {}
    scan_bs_events(bars, symbol="TEST", freq=Freq.D, shape_states=states)
    assert all(s.volatility == "未知" for s in states.values())


def test_scan_bs_events_without_shape_states_unchanged() -> None:
    """不传 shape_states 时行为与现状完全一致（事件数不变）。"""
    bars = _trend_then_flat(n_flat=30)
    baseline = scan_bs_events(bars, symbol="TEST", freq=Freq.D)
    states: dict[str, ShapeState] = {}
    with_states = scan_bs_events(bars, symbol="TEST", freq=Freq.D, shape_states=states)
    assert [(e.type, e.bar_time) for e in with_states] == [(e.type, e.bar_time) for e in baseline]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/services/chan/test_shape_filters.py -q`
Expected: 新增用例 FAIL（`scan_bs_events() got an unexpected keyword argument 'shape_states'`），Task 1 用例仍 PASS

- [ ] **Step 3: 修改 `scan_bs_events`（`app/services/chan/czsc_signals.py`）**

3 处改动：

(a) 顶部 import 区（`from app.services.chan.czsc_adapter import ...` 之后）加：

```python
from app.services.chan.shape_filters import read_shape_state, shape_config
```

(b) 函数签名与 config 组装（原 `def scan_bs_events(...)` 到 `cs = CzscSignals(bg, config)` 一段替换为）：

```python
def scan_bs_events(
    bars: list[dict], *, symbol: str, freq: Freq, stroke_done_at: dict[str, str] | None = None,
    families: Iterable[SignalFamily] = ("first",),
    shape_states: dict[str, ShapeState] | None = None,
) -> list[BsEvent]:
    """逐根推进 czsc 结构信号，返回按亮起时间排序、去重后的买卖点事件。

    families 决定启用哪些信号族，默认只有一类背驰。

    stroke_done_at：传入时逐根记录「笔终点 → 这一笔完成的那根K线」（czsc 的 bi_list
    只含已完成的笔，新出现的末笔即在当根完成），供二 / 三类作检测时间。

    shape_states：传入时 config 追加形态过滤信号（shape_filters），逐根记录
    「日期 → 当日形态状态」，供雷达按信号日查表剔除假信号；None 时不算形态信号，
    行为与现状一致。与 stroke_done_at 同构，一次推进零重复计算。
    """
    raw = bars_to_raw_bars(bars, symbol=symbol, freq=freq)
    if len(raw) <= _INIT_N:
        return []

    label = freq.value
    keys, config = _signal_keys_and_config(label, families)
    if shape_states is not None:
        config = config + shape_config(label)
    bg = BarGenerator(label, [], max_count=len(raw) + 1)
    bg.init_freq_bars(label, raw[:_INIT_N])
    cs = CzscSignals(bg, config)
```

（同时把模块顶部的类型导入区 `from app.services.chan.shape_filters import ...` 后面补一行类型引用——直接在 import 行写成 `from app.services.chan.shape_filters import ShapeState, read_shape_state, shape_config`，类型注解 `dict[str, ShapeState]` 用它。）

(c) 逐根循环体（`cs.update_signals(bar)` 之后、`if stroke_done_at is not None:` 之前）插入：

```python
        if shape_states is not None:
            shape_states[ts_date(bar.dt)] = read_shape_state(cs, label, total_bars=len(raw))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/services/chan/test_shape_filters.py tests/services/chan/ -q`
Expected: 全部 PASS（含既有 chan 回归）

- [ ] **Step 5: 提交**

```bash
git add app/services/chan/czsc_signals.py tests/services/chan/test_shape_filters.py
git commit -m "feat(chan): scan_bs_events 一次推进产出逐日形态状态 shape_states

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: `analyzer` 集成 — `shape_states` 字段与 `shape_filters` 开关

**Files:**

- Modify: `app/services/chan/analyzer.py`
- Test: `tests/services/chan/test_shape_filters.py`（追加）

- [ ] **Step 1: 写失败测试（追加）**

```python
# ---- analyzer 集成 ----
from app.services.chan.analyzer import ChanAnalyzer
from tests.services.chan.test_signals import _decaying_downtrend_bars


def test_analyze_shape_filters_switch() -> None:
    bars = _decaying_downtrend_bars()
    # 默认关闭：不算形态状态、买卖点与既有口径完全一致
    off = ChanAnalyzer().analyze("X", bars, mode="loose")
    assert off.shape_states == {}
    # 开启：有逐日形态状态，且不改变买卖点（详情页口径守护）
    on = ChanAnalyzer().analyze("X", bars, mode="loose", shape_filters=True)
    assert on.shape_states
    assert [(s.type, s.time) for s in on.signals] == [(s.type, s.time) for s in off.signals]
    # 形态状态键与信号日期同格式（纯日期），雷达可直接查表
    assert all(len(k) == 10 for k in on.shape_states)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/services/chan/test_shape_filters.py -q`
Expected: 新用例 FAIL（`ChanAnalysisResult` 无 `shape_states` 属性 / `analyze() got an unexpected keyword argument 'shape_filters'`）

- [ ] **Step 3: 实现（`app/services/chan/analyzer.py`）**

(a) `ChanAnalysisResult` 的 `stroke_done_at` 字段后加：

```python
    # 逐日形态状态（shape_filters），仅供雷达按信号日查表剔除假信号，详情页不读。
    shape_states: dict[str, "ShapeState"] = field(default_factory=dict)
```

顶部 import 区加 `from app.services.chan.shape_filters import ShapeState`（放在其他 chan 模块 import 旁），字段注解直接写 `dict[str, ShapeState]`。

(b) `analyze` 签名（第 141 行附近）改为：

```python
    def analyze(
        self, symbol: str, bars: list[dict], *, min_gap: int = 4, lang: str = "zh",
        visible_from: str | None = None, freq: str = "daily", mode: str = DEFAULT_MODE,
        shape_filters: bool = False,
    ) -> ChanAnalysisResult:
```

docstring 末尾（`freq:` 说明之后）补一段：

```text
        shape_filters: 是否同时产出逐日形态状态（result.shape_states），供信号雷达
            剔除假信号（假突破 / 窄幅震荡 / 收盘偏弱 / 低波动 / 区间震荡中的一类）。
            只加状态不改买卖点；详情页等非雷达路径不传。
```

(c) 第 8 步 `scan_bs_events` 调用处（第 232-235 行附近）改为：

```python
        policy = get_policy(mode)
        stroke_done_at: dict[str, str] = {}
        shape_states: dict[str, ShapeState] = {}
        events = scan_bs_events(bars, symbol=symbol, freq=czsc_freq, stroke_done_at=stroke_done_at,
                                families=policy.czsc_families,
                                shape_states=shape_states if shape_filters else None)
        result.stroke_done_at = stroke_done_at
        result.shape_states = shape_states
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/services/chan/ -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/chan/analyzer.py tests/services/chan/test_shape_filters.py
git commit -m "feat(chan): analyze 增加 shape_filters 开关产出逐日形态状态

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: 雷达层 — `shape_rejected` 标记与 `build_days` 剔除（防回退）

**Files:**

- Modify: `app/services/signal_radar/service.py`
- Test: `tests/services/signal_radar/test_shape_filter.py`（追加）

- [ ] **Step 1: 写失败测试（追加到 `tests/services/signal_radar/test_shape_filter.py` 末尾）**

```python
# ---- czsc 形态过滤：shape_rejected 出生即剔除、不回退旧信号 ----
from collections import Counter


def test_shape_rejected_latest_signal_excluded_without_fallback() -> None:
    """最新信号被形态过滤剔除后，该 symbol 当日无信号，旧信号不得回锅上榜。"""
    older = _raw("X", "2026-09-20", "buy", 0.8)
    latest = _raw("X", "2026-09-21", "buy", 0.9)
    latest.shape_rejected = "窄幅震荡"
    days = svc.build_days([[older, latest]], ["2026-09-22"], top_n=10)
    assert days[0].signals == []
    # 未被剔除的旧信号单独存在时正常上榜（对照）
    days = svc.build_days([[older]], ["2026-09-22"], top_n=10)
    assert [s.symbol for s in days[0].signals] == ["X"]


def test_shape_rejected_reasons_logged_in_history() -> None:
    """build_signal_history 用 reject_reason 按信号日查表标记（经真实分析验证链路）。"""
    result = ChanAnalyzer().analyze("X", _decaying_downtrend_bars(), mode="loose",
                                    shape_filters=True)
    history = svc.build_signal_history("X", "测试", result)
    # 不崩溃、条数一致；标记值要么 None 要么是五个过滤器名之一
    valid = {None, "假突破", "窄幅震荡", "收盘位置", "低波动", "区间震荡"}
    assert {r.shape_rejected for r in history} <= valid
    assert len(history) == len(result.signals)


def test_build_days_shape_filter_counter_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    """剔除分布按过滤器名计数记 debug 日志（可观测）。"""
    import structlog
    events: list[tuple] = []
    monkeypatch.setattr(
        structlog, "get_logger", lambda *a, **k: type("L", (), {
            "debug": staticmethod(lambda e, **kw: events.append((e, kw))),
            "info": staticmethod(lambda e, **kw: None),
            "warning": staticmethod(lambda e, **kw: None),
        })())
    rejected = _raw("X", "2026-09-20", "buy", 0.8)
    rejected.shape_rejected = "假突破"
    ok = _raw("Y", "2026-09-20", "sell", 0.7)
    svc.build_days([[rejected, ok]], ["2026-09-21"], top_n=10)
    assert any(e == "signal_radar_shape_rejected" for e, _ in events)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/services/signal_radar/test_shape_filter.py -q`
Expected: 新用例 FAIL（`RawSignal` 无 `shape_rejected` 属性 / `analyze() got an unexpected keyword argument 'shape_filters'`），既有用例仍 PASS

- [ ] **Step 3: 实现（`app/services/signal_radar/service.py`）**

(a) import 区：`from collections import Counter` 已有则跳过；加

```python
from app.services.chan.shape_filters import reject_reason
```

（放在文件顶部与其他 `app.services.chan` import 一起。）

(b) `RawSignal` 的 `confirmed_on` 字段后加：

```python
    # 形态过滤命中（假突破/窄幅震荡/收盘位置/低波动/区间震荡），出生即不入雷达榜单
    shape_rejected: str | None = None
```

(c) `build_signal_history` 构造处（`confirmed_on=...` 行后）加一行，并在函数结尾（`history.sort(...)` 后）加日志：

```python
            shape_rejected=reject_reason(result.shape_states.get(sig.time[:10]), sig.type),
```

```python
    history.sort(key=lambda r: r.date)
    reasons = [r.shape_rejected for r in history if r.shape_rejected]
    if reasons:
        logger.debug("signal_radar_shape_rejected", symbol=symbol,
                     counts=dict(Counter(reasons)))
    return history
```

(d) `build_days` 的候选过滤链（`if candidate.invalidated_on ...` 判断之前）插入：

```python
                if candidate.shape_rejected is not None:
                    continue  # 形态过滤命中（出生即剔除），不让被剔信号背后的旧信号回锅
```

并在 docstring 的形态筛选说明句后补：`形态过滤（shape_rejected）同理在最新信号确定后剔除。`

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/services/signal_radar/ -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/signal_radar/service.py tests/services/signal_radar/test_shape_filter.py
git commit -m "feat(signal-radar): 信号出生时按形态状态标记剔除，防旧信号回锅

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: 雷达开启形态过滤与缓存键 `:shape2:`

**Files:**

- Modify: `app/services/signal_radar/service.py`
- Test: `tests/services/signal_radar/test_shape_filter.py`（修改既有缓存键断言）

- [ ] **Step 1: 更新缓存键测试（`test_shape_filter_invalidates_all_radar_cache_types` 里的 `":shape1:"` 改为 `":shape2:"`）**

```python
def test_shape_filter_invalidates_all_radar_cache_types() -> None:
    assert all(":shape2:" in key for key in [
        svc._cache_key("us", "nasdaq100"),
        svc.watchlist_cache_key("us", 7, [("X", "测试")]),
        svc._demo_cache_key("us", "nasdaq100", "2026-09-01"),
    ])
```

并追加扫描路径测试：

```python
async def test_scan_symbol_enables_shape_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    """雷达扫描路径的 analyze 必须开 shape_filters（形态状态进入历史标记链路）。"""
    seen: dict[str, bool] = {}

    class _SpyAnalyzer:
        def analyze(self, symbol, bars, **kwargs):
            seen["shape_filters"] = kwargs.get("shape_filters")
            return ChanAnalysisResult(symbol=symbol, bars_count=len(bars))

    async def fake_fetch(**kwargs):
        return [{"time": "2026-09-20", "open": 10, "high": 11, "low": 9, "close": 10,
                 "volume": 100}]

    monkeypatch.setattr(svc, "_analyzer", _SpyAnalyzer())
    monkeypatch.setattr(svc, "fetch_kline", fake_fetch)
    await svc._scan_symbol("X", "测试", user_id=None, start_date="2026-08-01",
                           end_date="2026-09-20", redis=_FakeRedis())
    assert seen["shape_filters"] is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/services/signal_radar/test_shape_filter.py -q`
Expected: 缓存键断言 FAIL（当前是 `:shape1:`）、spy 测试 FAIL（`shape_filters` 为 None）

- [ ] **Step 3: 实现（`app/services/signal_radar/service.py`）**

(a) `_mode_ns`（第 98-99 行附近）：

```python
def _mode_ns(mode: str) -> str:
    return f"{get_policy(mode).version}:shape2"
```

上方注释行同步改为：

```python
# 否则部署后缓存里还是旧口径的气泡。shape2 = 已确认 + 价格失效 + czsc 形态过滤
# （假突破 / 窄幅震荡 / 收盘偏弱 / 低波动 / 区间震荡中的一类），仅隔离雷达筛选，
# 不改变详情口径。
```

(b) `_scan_symbol` 里的 analyze 调用（第 600 行附近）改为：

```python
        result = _analyzer.analyze(symbol, bars, lang="zh", mode=mode, shape_filters=True)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/services/signal_radar/ -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/signal_radar/service.py tests/services/signal_radar/test_shape_filter.py
git commit -m "feat(signal-radar): 扫描开启形态过滤，缓存键升级 shape2

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: iOS 说明文案（透明过滤）

**Files:**

- Modify: `ios/DeepAlphaChan/Views/SignalRadar/SignalRadarView.swift`（`rankingInfoLines`）
- Modify: `ios/DeepAlphaChan/Resources/en.lproj/Localizable.strings`

zh-Hans 不用改：`L()` 的 key 即中文，查不到时回退 key 本身（既有模式，见上一轮只改 en.lproj 的先例）。

- [ ] **Step 1: `SignalRadarView.swift` 的 `rankingInfoLines` 尾部（`lines += [...]` 数组内、「每类买卖点先保底…」之前）插入三行**

```swift
        lines += [
            L("形态过滤剔除假信号：信号出现当天若处于窄幅震荡、同向假突破、低波动或收盘偏弱，则不上榜。"),
            L("一类买卖点额外要求趋势环境：信号当天处于区间震荡中的一类信号不上榜。"),
            L("详情页仍显示全部买卖点，形态过滤只影响雷达榜单。"),
            L("每类买卖点先保底最多 2 个名额，其余按综合分从高到低补满，共取前 10 名。"),
            L("当前为「%@」模式，可在「我的 → 买卖点模式」切换。", signalMode.currentOption?.label ?? L("宽松")),
        ]
```

（即把现有数组的后两项纳入同一数组，前插三行新的。）

- [ ] **Step 2: `en.lproj/Localizable.strings` 末尾（`/* 雷达形态有效性筛选 */` 区块之后）追加**

```text
/* 雷达 czsc 形态过滤 */
"形态过滤剔除假信号：信号出现当天若处于窄幅震荡、同向假突破、低波动或收盘偏弱，则不上榜。" = "Fake-signal screening: a signal stays off the radar if its pattern day shows a narrow range, a same-direction fake break, low volatility, or a weak close.";
"一类买卖点额外要求趋势环境：信号当天处于区间震荡中的一类信号不上榜。" = "First-order signals also require a trending environment: first-order signals born inside a range oscillation stay off the radar.";
"详情页仍显示全部买卖点，形态过滤只影响雷达榜单。" = "The details page still shows every signal; screening only filters the radar list.";
```

- [ ] **Step 3: Swift 语法检查（本机有 Xcode 时）**

Run: `xcrun swiftc -parse ios/DeepAlphaChan/Views/SignalRadar/SignalRadarView.swift 2>&1 | head -20`（单文件 parse 可能因跨文件类型报错，仅确认无本文件语法错误；无 Xcode 环境则跳过，由用户在 Xcode 中构建确认）

- [ ] **Step 4: 提交**

```bash
git add ios/DeepAlphaChan/Views/SignalRadar/SignalRadarView.swift ios/DeepAlphaChan/Resources/en.lproj/Localizable.strings
git commit -m "feat(ios): 雷达上榜说明补充形态过滤规则文案

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: 全量回归与代码检查

- [ ] **Step 1: 全量测试**

Run: `uv run pytest tests/services/signal_radar/ tests/services/chan/ -q`
Expected: 全部 PASS

- [ ] **Step 2: 代码检查**

Run: `make check`
Expected: ruff + pyright 无错误（若有未使用 import 等，按提示修复后重跑）

- [ ] **Step 3: 真实数据校准 th（可选，需要 FMP_API_KEY）**

若本机 `FMP_API_KEY` 可用：取 nasdaq100 里若干真实成分股跑 `analyze(shape_filters=True)`，统计一类信号被「区间震荡」剔除的比例，目标 10%~30%；偏离则调整 `shape_filters.py` 的 `_RANGE_OSC_TH` 重跑。无 key 则跳过（`th=10` 保守可用，后续线上观察日志 `signal_radar_shape_rejected` 的分布再调）。

Run: `FMP_API_KEY=<key> uv run python -c "..."`（临时脚本，不入库）

- [ ] **Step 4: 最终提交（如有零散修复）**

```bash
git add -A && git commit -m "chore(signal-radar): 形态过滤回归修复

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

（无修复则跳过。）

---

## 自审记录

- **Spec 覆盖**：五条过滤规则 → Task 1；逐日状态产出 → Task 2；analyzer 开关 → Task 3；雷达标记/剔除/防回退/日志 → Task 4；`_scan_symbol` 开启 + 缓存键 shape2 → Task 5；iOS 文案 → Task 6；th 校准 → Task 7。波动率「K 线不足跳过」→ Task 1（未知不剔）+ Task 2（不足置未知）。详情页口径守护 → Task 3 测试（开/关 signals 一致）。
- **占位符**：无 TBD/TODO；Task 5 Step 3(b) 已给出完整正确代码。
- **类型一致性**：`ShapeState` / `reject_reason(state, signal_type) -> str | None` / `shape_config(label)` / `read_shape_state(cs, label, *, total_bars)` 各任务引用一致；`scan_bs_events(..., shape_states=...)` 与 analyzer、service 调用一致。
