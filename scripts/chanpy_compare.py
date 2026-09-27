# pyright: reportMissingImports=false
"""chan.py（Vespa314/chan.py）与本项目缠论引擎的对比 spike。

一次性评估脚本，不进入生产代码路径。同一份前复权日线同时送进两边，
逐项对比：笔、线段、笔级中枢、买卖点（一 / 二 / 三类）。

用法：
    git clone --depth 1 https://github.com/Vespa314/chan.py /tmp/chanpy
    uv run python scripts/chanpy_compare.py [AAPL NVDA ...]
"""
from __future__ import annotations

import asyncio
import sys
import time
from datetime import date, timedelta

CHANPY_PATH = "/tmp/chanpy"
sys.path.insert(0, CHANPY_PATH)

from Chan import CChan  # noqa: E402
from ChanConfig import CChanConfig  # noqa: E402
from Common.CEnum import DATA_FIELD, DATA_SRC, KL_TYPE  # noqa: E402
from Common.CTime import CTime  # noqa: E402
from KLine.KLine_Unit import CKLine_Unit  # noqa: E402

from app.services.chan.analyzer import ChanAnalyzer  # noqa: E402
from app.services.skills.kline import fetch_kline  # noqa: E402

DEFAULT_SYMBOLS = ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN", "META", "GOOGL", "AMD"]
WARMUP_DAYS = 180  # 与详情页日线预热一致

# 尽量贴近缠论原文的 chan.py 配置
CHANPY_CONF = {
    "bi_strict": False,            # 放宽成笔（默认老笔+严格分型检查，笔比 czsc 新笔少一半）
    "bi_fx_check": "loss",
    "seg_algo": "chan",            # 特征序列划分线段
    "zs_algo": "normal",           # 段内笔级中枢
    "min_zs_cnt": 2,               # 一类 = 趋势背驰：段内至少两个（合并后不重叠的）中枢
    "bsp1_only_multibi_zs": True,
    "divergence_rate": 0.9,        # 默认 inf 等于不查背驰，必须显式设置
    "macd_algo": "area",
    "bs1_peak": True,
    "bsp2_follow_1": True,         # 二类必须跟在一类之后
    "bsp3_follow_1": False,        # 原文三类不依赖一类
    "bs_type": "1,2,3a,3b",        # 不要类二（2s）与盘整背驰一类（1p）
    "print_warning": False,
    "trigger_step": True,          # 逐根增量计算（不回看未来），也避免初始化时去拉数据源
}


def _ctime(s: str) -> CTime:
    return CTime(int(s[:4]), int(s[5:7]), int(s[8:10]), 0, 0)


def _day(t: CTime) -> str:
    return f"{t.year:04d}-{t.month:02d}-{t.day:02d}"


def run_chanpy(bars: list[dict], conf: dict) -> CChan:
    """把项目 K 线逐根喂给 chan.py（增量计算），返回 CChan 对象。"""
    chan = CChan(code="X", data_src=DATA_SRC.CSV, lv_list=[KL_TYPE.K_DAY],
                 config=CChanConfig(dict(conf)))
    klus = [
        CKLine_Unit({
            DATA_FIELD.FIELD_TIME: _ctime(b["time"]),
            DATA_FIELD.FIELD_OPEN: float(b["open"]),
            DATA_FIELD.FIELD_HIGH: float(b["high"]),
            DATA_FIELD.FIELD_LOW: float(b["low"]),
            DATA_FIELD.FIELD_CLOSE: float(b["close"]),
            DATA_FIELD.FIELD_VOLUME: float(b.get("volume") or 0),
        })
        for b in bars
    ]
    chan.trigger_load({KL_TYPE.K_DAY: klus})
    return chan


def chanpy_structures(chan: CChan, visible_from: str) -> dict:
    """取出 chan.py 的笔 / 线段 / 中枢 / 买卖点，按可见区过滤。"""
    kl = chan[0]
    strokes = [(_day(b.get_begin_klu().time), _day(b.get_end_klu().time)) for b in kl.bi_list]
    segs = [(_day(s.start_bi.get_begin_klu().time), _day(s.end_bi.get_end_klu().time),
             "up" if s.is_up() else "down") for s in kl.seg_list]
    pivots = [(_day(z.begin_bi.get_begin_klu().time), _day(z.end_bi.get_end_klu().time),
               round(z.low, 2), round(z.high, 2)) for z in kl.zs_list if not z.is_one_bi_zs()]
    sigs = []
    for bsp in chan.get_bsp():
        t = _day(bsp.klu.time)
        side = "buy" if bsp.is_buy else "sell"
        for bt in bsp.type:
            sigs.append((t, f"{side}{bt.main_type()}", bt.value))
    return {
        "strokes": [s for s in strokes if s[1] >= visible_from],
        "segments": [s for s in segs if s[1] >= visible_from],
        "pivots": [p for p in pivots if p[1] >= visible_from],
        "signals": sorted(s for s in sigs if s[0] >= visible_from),
    }


def ours_structures(symbol: str, bars: list[dict], visible_from: str) -> dict:
    """取出本项目引擎的笔 / 线段 / 中枢 / 买卖点，口径与 chanpy_structures 一致。"""
    # 分析器会把左沿前移到跨界线段的起点，这里按与 chan.py 相同的口径重新过滤，保证公平
    r = ChanAnalyzer().analyze(symbol, bars, visible_from=visible_from)
    strokes = [(s.start.time[:10], s.end.time[:10]) for s in r.strokes]
    segs = [(s.strokes[0].start.time[:10], s.strokes[-1].end.time[:10], s.direction) for s in r.segments]
    pivots = [(p.start_time[:10], p.end_time[:10], round(p.zd, 2), round(p.zg, 2)) for p in r.stroke_pivots]
    return {
        "strokes": [s for s in strokes if s[1] >= visible_from],
        "segments": [s for s in segs if s[1] >= visible_from],
        "pivots": [p for p in pivots if p[1] >= visible_from],
        "signals": sorted((s.time[:10], s.type, s.type) for s in r.signals if s.time[:10] >= visible_from),
    }


def _overlap(a: list, b: list) -> str:
    sa, sb = set(a), set(b)
    both = len(sa & sb)
    return f"我们 {len(sa)} / chan.py {len(sb)} / 完全一致 {both}"


async def main(symbols: list[str]) -> None:
    """逐只股票对比并打印汇总。"""
    end = date.today()
    visible_from = (end - timedelta(days=365)).isoformat()
    fetch_from = (end - timedelta(days=365 + WARMUP_DAYS)).isoformat()

    totals = {"ours": 0, "chanpy": 0, "same": 0}
    timing = {"ours": 0.0, "chanpy": 0.0}
    for sym in symbols:
        bars = await fetch_kline(None, sym, fetch_from, end.isoformat(), "daily")
        t0 = time.perf_counter()
        ours = ours_structures(sym, bars, visible_from)
        t1 = time.perf_counter()
        theirs = chanpy_structures(run_chanpy(bars, CHANPY_CONF), visible_from)
        t2 = time.perf_counter()
        timing["ours"] += t1 - t0
        timing["chanpy"] += t2 - t1

        print(f"\n===== {sym}（{len(bars)} 根，可见区 {visible_from} 起）=====")
        for key in ("strokes", "segments", "pivots"):
            print(f"  {key:9s}: {_overlap(ours[key], theirs[key])}")
        print(f"  线段（我们）  : {ours['segments']}")
        print(f"  线段（chan.py）: {theirs['segments']}")
        o_sig = {(t, k) for t, k, _ in ours["signals"]}
        c_sig = {(t, k) for t, k, _ in theirs["signals"]}
        totals["ours"] += len(o_sig)
        totals["chanpy"] += len(c_sig)
        totals["same"] += len(o_sig & c_sig)
        print(f"  买卖点   : 我们 {sorted(o_sig)}")
        print(f"             chan.py {[(t, k, raw) for t, k, raw in theirs['signals']]}")
        print(f"             一致 {sorted(o_sig & c_sig)}")

    print("\n===== 汇总 =====")
    print(f"买卖点：我们 {totals['ours']} 个，chan.py {totals['chanpy']} 个，同日同类一致 {totals['same']} 个")
    print(f"耗时：我们 {timing['ours']:.2f}s，chan.py {timing['chanpy']:.2f}s（{len(symbols)} 只）")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or DEFAULT_SYMBOLS))
