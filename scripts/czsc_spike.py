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
