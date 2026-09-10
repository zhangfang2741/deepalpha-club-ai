"""窗口锚定测试：缠论结构不随用户所选起始日期漂移。

核心保证：在用户可见起点之前多取一段 warmup K 线、在完整序列上计算再裁剪回
可见窗口后，可见区内的笔/线段应与「用足够长历史算出」的基准一致；且所有返回
结构都落在可见窗口内（跨界结构保留、K线左延覆盖）。
"""
from __future__ import annotations

import random

from app.services.chan.analyzer import ChanAnalyzer


def _walk(n: int, seed: int, start: float = 100.0, vol: float = 0.03) -> list[dict]:
    rng = random.Random(seed)
    bars: list[dict] = []
    price = start
    base = 1_600_000_000
    for t in range(n):
        c = max(1.0, price * (1 + rng.gauss(0, vol)))
        o = max(1.0, price * (1 + rng.gauss(0, vol * 0.5)))
        h = max(o, c) * (1 + abs(rng.gauss(0, vol * 0.5)))
        low = min(o, c) * (1 - abs(rng.gauss(0, vol * 0.5)))
        # 递增的 YYYY-MM-DD 时间戳（用连续日期即可，缠论只比较字符串大小）
        y = 2020 + t // 300
        doy = t % 300
        bars.append({
            "time": f"{y}-{1 + doy // 28:02d}-{1 + doy % 28:02d}",
            "open": round(o, 2), "high": round(h, 2), "low": round(low, 2),
            "close": round(c, 2), "volume": 1000 + base % 7,
        })
        price = c
    return bars


def _visible_strokes(result, cut: str):
    return [
        (s.direction, s.start_time, round(s.start_price, 2), s.end_time, round(s.end_price, 2))
        for s in result.strokes if s.end_time >= cut
    ]


def test_visible_structure_is_window_independent():
    analyzer = ChanAnalyzer()
    matched = 0
    for seed in range(1, 12):
        full = _walk(400, seed)
        cut = full[200]["time"]
        # 基准：用全历史计算，再看可见区
        base = _visible_strokes(analyzer.analyze("T", full, visible_from=cut), cut)
        # 锚定：只多取 120 根 warmup
        anchored = analyzer.analyze("T", full[80:], visible_from=cut)
        anchored_v = _visible_strokes(anchored, cut)
        if anchored_v == base:
            matched += 1
        # 返回的笔必须都落在可见窗口内（结束时间 >= cut）
        assert all(s.end_time >= cut for s in anchored.strokes)
        # 合并K线需覆盖所有保留笔的端点（不出现悬空点）：
        # 最早的合并K线不晚于最早保留笔的起点
        if anchored.merged_candles and anchored.strokes:
            earliest_stroke = min(s.start_time for s in anchored.strokes)
            assert anchored.merged_candles[0].time <= earliest_stroke
    # 120 根 warmup 应让绝大多数 seed 的可见结构与基准完全一致
    assert matched >= 10, f"锚定后可见结构与基准一致的 seed 仅 {matched}/11"


def test_clip_keeps_summary_counts_consistent():
    analyzer = ChanAnalyzer()
    full = _walk(300, seed=5)
    cut = full[150]["time"]
    r = analyzer.analyze("T", full, visible_from=cut)
    # 摘要里的合并K线/笔计数应与裁剪后的实际列表长度一致
    assert f"{len(r.merged_candles)} 根合并K线" in r.summary
    assert f"{len(r.strokes)} 笔" in r.summary
    # 所有可见结构不早于窗口
    assert all(f.time >= cut for f in r.fractals)
    assert all(sig.time >= cut for sig in r.signals)


def test_no_visible_from_is_unchanged():
    analyzer = ChanAnalyzer()
    full = _walk(200, seed=3)
    a = analyzer.analyze("T", full)
    b = analyzer.analyze("T", full, visible_from=None)
    assert len(a.strokes) == len(b.strokes)
    assert len(a.merged_candles) == len(b.merged_candles)
