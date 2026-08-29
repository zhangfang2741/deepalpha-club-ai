#!/usr/bin/env python3
"""给缠论 App 的截图加标题文案，输出可直接上传的 1320×2868（6.9 英寸）图。

用法（不需要装依赖到项目里）：
    uv run --with pillow --no-project python ios/AppStore/chan/make_captioned.py

沿用 ../make_captioned.py 那套视觉（深色渐变 + 大标题 + 圆角机身 + 柔光），
尺寸从 6.5 英寸的 1242×2688 换成 6.9 英寸的 1320×2868，字号按比例放大。

金融类 App 的额外约束：标题里不能出现任何暗示收益或荐股的词。这里全部说的是
「画出结构」「给出依据」这类工具属性，最后一张直接把免责讲在标题上——
审核员翻截图时第一眼就能看到我们没在卖预测。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE = Path(__file__).parent
SRC = BASE / "screenshots-6.9"
OUT = BASE / "screenshots-6.9-captioned"

W, H = 1320, 2868

# Hiragino Sans GB：index 2 = W6（粗，做标题），index 0 = W3（细，做副标题）。
FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"
FONT_TITLE = ImageFont.truetype(FONT_PATH, 93, index=2)
FONT_SUB = ImageFont.truetype(FONT_PATH, 45, index=0)

# 与 App 内 Theme 保持一致，让商店页和 App 本身看起来是一套东西。
INK = (240, 246, 252)
MUTED = (150, 165, 185)

# 顺序即上传顺序，列表页只展示前 3 张的缩略图，所以最能说明「这是什么」的排前面。
# 每张一个主色，避免 6 张刷下来全是一模一样的黑；主色取自 App 内的图层配色。
SHOTS = [
    ("01_analysis_us.png", "缠论结构\n自动画在图上",
     "分型 · 笔 · 线段 · 中枢 · 背驰", (96, 165, 250)),        # Theme.stroke 笔
    ("06_fullscreen.png", "横屏全屏\n看更多 K 线",
     "五个结构图层，可以逐个开关", (139, 92, 246)),            # Theme.pivotFill 中枢
    ("02_analysis_hk.png", "美股 A股 港股\n一套结构分析",
     "日线与周线，代码各按各市场输入", (46, 189, 133)),        # Theme.down 跌绿
    ("03_learn.png", "看不懂\n那就先学",
     "9 篇入门词条，每篇配一张示意图", (245, 158, 11)),        # Theme.segment 线段
    ("04_lesson_detail.png", "术语点一下\n就有解释",
     "图例和买卖点标签都能点开词条", (236, 72, 153)),
    ("05_query.png", "技术信号\n不等于投资建议",
     "每次分析前都把这句话摆在你面前", (100, 116, 139)),
]


def gradient(accent: tuple[int, int, int]) -> Image.Image:
    """顶部透出主色、向下收敛到接近纯黑的竖向渐变。"""
    top = tuple(int(c * 0.22 + 11) for c in accent)
    bottom = (8, 10, 15)
    grad = Image.new("RGB", (1, H))
    px = grad.load()
    for y in range(H):
        t = (y / H) ** 0.75  # 前段变化快一些，色彩集中在标题区
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return grad.resize((W, H))


def glow(canvas: Image.Image, accent: tuple[int, int, int], cx: int, cy: int, r: int) -> None:
    """机身后面垫一团柔光，避免深色截图直接糊在深色背景上分不出层次。"""
    layer = Image.new("RGB", (W, H), (0, 0, 0))
    ImageDraw.Draw(layer).ellipse([cx - r, cy - r // 2, cx + r, cy + r // 2], fill=accent)
    layer = layer.filter(ImageFilter.GaussianBlur(200))
    canvas.paste(Image.blend(canvas, Image.blend(canvas, layer, 0.30), 1.0), (0, 0))


def rounded(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, *img.size], radius=radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def build(name: str, title: str, sub: str, accent: tuple[int, int, int]) -> None:
    shot = Image.open(SRC / name).convert("RGB")

    # 机身宽度定在 62%：留足顶部空间放两行大标题，同时底部不贴边。
    dev_w = 818
    dev_h = round(dev_w * shot.height / shot.width)
    dev_x = (W - dev_w) // 2
    dev_y = H - dev_h - 102

    canvas = gradient(accent)
    glow(canvas, accent, W // 2, dev_y + dev_h // 3, 595)

    body = rounded(shot.resize((dev_w, dev_h), Image.LANCZOS), 61)

    # 机身描边：一圈极淡的白，把屏幕从背景里「抠」出来。
    ring = Image.new("RGBA", (dev_w + 6, dev_h + 6), (0, 0, 0, 0))
    ImageDraw.Draw(ring).rounded_rectangle(
        [0, 0, dev_w + 5, dev_h + 5], radius=64, outline=(255, 255, 255, 46), width=3
    )
    canvas.paste(ring, (dev_x - 3, dev_y - 3), ring)
    canvas.paste(body, (dev_x, dev_y), body)

    draw = ImageDraw.Draw(canvas)

    # 标题：两行，行距 1.18；整体按可用高度垂直居中，不同长度的标题不会跳。
    lines = title.split("\n")
    lh = 110
    block_h = lh * len(lines)
    ty = (dev_y - 128 - block_h) // 2 + 42
    for i, line in enumerate(lines):
        w = draw.textlength(line, font=FONT_TITLE)
        draw.text(((W - w) / 2, ty + i * lh), line, font=FONT_TITLE, fill=INK)

    sw = draw.textlength(sub, font=FONT_SUB)
    draw.text(((W - sw) / 2, ty + block_h + 28), sub, font=FONT_SUB, fill=MUTED)

    OUT.mkdir(exist_ok=True)
    dst = OUT / name
    canvas.save(dst, "PNG", optimize=True)
    print(f"  ✓ {dst.name}  {canvas.width}×{canvas.height}")


def main() -> None:
    print(f"输出到 {OUT}/")
    missing = []
    for name, title, sub, accent in SHOTS:
        if (SRC / name).exists():
            build(name, title, sub, accent)
        else:
            missing.append(name)
            print(f"  ✗ 缺少源文件 {name}")
    if missing:
        raise SystemExit(f"\n缺少 {len(missing)} 张源截图，先补齐再跑。")


if __name__ == "__main__":
    main()
