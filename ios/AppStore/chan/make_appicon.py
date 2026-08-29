#!/usr/bin/env python3
"""生成 App 图标（1024×1024），直接覆盖 Assets 里的 icon-1024.png。

用法：
    uv run --with pillow --no-project python ios/AppStore/chan/make_appicon.py

构图沿用原图标：深色底 + 五根蜡烛 + 中枢矩形 + 一条蓝色的「笔」走成 M 形。
改的是**比例**——原图内容只占画布约 60% 且整体偏下，缩到桌面实际显示的
60×60 之后蜡烛和折线会糊成一团。这里把内容放大到 78% 并垂直居中，
线宽随之加粗。

两条硬约束：
- **不能有 Alpha 通道**，带透明度的图标 App Store 直接拒；故全程 RGB 作画。
- 内容留在 78% 的安全区内，iOS 会把图标裁成圆角，贴边的东西会被切掉。

配色取自 App 内的 Theme，商店页、图标和 App 本身才是一套。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = (Path(__file__).parent.parent.parent
       / "DeepAlphaChan/Resources/Assets.xcassets/AppIcon.appiconset/icon-1024.png")

S = 1024
CONTENT = 0.78          # 内容占画布比例
BG_TOP = (16, 21, 32)   # 比 Theme.background 略亮，顶部透一点层次
BG_BOTTOM = (8, 10, 15)
UP = (246, 70, 93)      # Theme.up   涨=红
DOWN = (46, 189, 133)   # Theme.down 跌=绿
STROKE = (96, 165, 250)  # Theme.stroke 笔
PIVOT = (139, 92, 246)  # Theme.pivotFill 中枢

# 五根 K 线的 (low, open, close, high)，值域 0–1，0 在底部。
# 走势刻意排成 M 形：起涨 → 见顶 → 回落见底 → 再冲高 → 收在中段，
# 这样一条「笔」就能同时展示顶分型、底分型和两段趋势。
# 涨跌刻意排成红绿相间：连着三根同色会让图标看起来像色块而不像 K 线。
CANDLES = [
    (0.18, 0.24, 0.48, 0.56),   # 涨 红
    (0.30, 0.70, 0.42, 0.88),   # 跌 绿 ← 第一个峰
    (0.10, 0.18, 0.34, 0.40),   # 涨 红 ← 谷
    (0.32, 0.66, 0.44, 0.82),   # 跌 绿 ← 第二个峰
    (0.34, 0.52, 0.78, 0.90),   # 涨 红
]
# 「笔」的转折点：起点低 → 第2根的高 → 第3根的低 → 第4根的高 → 第5根的低
PATH = [(0, "low"), (1, "high"), (2, "low"), (3, "high"), (4, "low")]


def background() -> Image.Image:
    img = Image.new("RGB", (1, S))
    px = img.load()
    for y in range(S):
        t = (y / S) ** 0.8
        px[0, y] = tuple(round(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3))
    return img.resize((S, S))


def main() -> None:
    inset = S * (1 - CONTENT) / 2
    span = S * CONTENT
    # 五根蜡烛 + 四个间隔，实体宽 : 间隔 = 2 : 1
    body_w = span / 7
    gap = body_w / 2
    wick_w = round(body_w * 0.16)

    def cx(i: int) -> float:
        return inset + i * (body_w + gap) + body_w / 2

    def cy(v: float) -> float:
        return inset + span * (1 - v)

    img = background()
    d = ImageDraw.Draw(img)

    # 中枢：第 2–4 根之间的价格重叠区，垫在蜡烛下面
    zg, zd = 0.50, 0.40
    d.rectangle(
        [cx(1) - body_w / 2, cy(zg), cx(3) + body_w / 2, cy(zd)],
        fill=tuple(round(BG_TOP[i] + (PIVOT[i] - BG_TOP[i]) * 0.42) for i in range(3)),
    )

    for i, (low, op, cl, high) in enumerate(CANDLES):
        # 与 App 内一致：涨=红（Theme.up）、跌=绿（Theme.down）
        color = UP if cl >= op else DOWN
        x = cx(i)
        d.rectangle([x - wick_w / 2, cy(high), x + wick_w / 2, cy(low)], fill=color)
        top, bottom = max(op, cl), min(op, cl)
        d.rectangle([x - body_w / 2, cy(top), x + body_w / 2, cy(bottom)], fill=color)

    # 「笔」最后画，压在蜡烛之上。线宽刻意压到实体的 1/6：再粗就盖住蜡烛，
    # 图标会变成「一条折线」而不是「K 线图上画了一条笔」。
    pts = [(cx(i), cy(CANDLES[i][0] if k == "low" else CANDLES[i][3])) for i, k in PATH]
    d.line(pts, fill=STROKE, width=round(body_w * 0.16), joint="curve")

    img.save(OUT, "PNG", optimize=True)
    print(f"✓ {OUT.name}  {img.size[0]}×{img.size[1]}  mode={img.mode}（无 Alpha）")


if __name__ == "__main__":
    main()
