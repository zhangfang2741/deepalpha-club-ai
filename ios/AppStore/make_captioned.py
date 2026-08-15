#!/usr/bin/env python3
"""给 App Store 截图加标题文案，输出可直接上传的 1242×2688 图。

用法（不需要装依赖到项目里）：
    uv run --with pillow --no-project python ios/AppStore/make_captioned.py

设计上刻意保持克制：深色渐变背景 + 一句主标题 + 一句副标题 + 圆角机身。
App Store 搜索结果只展示前 3 张的缩略图，标题必须在缩到很小的时候还能读，
所以字号给得很大、每行字数压到 12 个字以内。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE = Path(__file__).parent
SRC = BASE / "screenshots-6.5"
OUT = BASE / "screenshots-6.5-captioned"

W, H = 1242, 2688

# Hiragino Sans GB：index 2 = W6（粗，做标题），index 0 = W3（细，做副标题）。
FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"
FONT_TITLE = ImageFont.truetype(FONT_PATH, 88, index=2)
FONT_SUB = ImageFont.truetype(FONT_PATH, 42, index=0)

# 与 App 内 Theme 保持一致，让商店页和 App 本身看起来是一套东西。
INK = (240, 246, 252)
MUTED = (150, 165, 185)

# 每张图一个主色，整体仍是深色调，只在顶部透出一点色相变化，
# 避免 7 张图刷下来全是一模一样的黑。
SHOTS = [
    ("04_home.png", "拍张照\n生词自动进单词本", "课本、试卷、外刊，整页一次识别", (59, 130, 246)),
    ("02_wordlist.png", "你的生词\n自动分好类", "不认识 · 模糊 · 认识，进度一目了然", (34, 197, 94)),
    ("05_word_detail.png", "音标 · 释义\n词根 · 例句", "懂词根，比死记硬背牢十倍", (168, 85, 247)),
    ("01_review_card.png", "听着背\n像听歌一样过单词", "锁屏也能继续，通勤路上就记完了", (245, 158, 11)),
    ("03_settings.png", "你的数据\n你说了算", "不含广告，可随时彻底删除账号", (100, 116, 139)),
    ("07_dictation.png", "说出来\nApp 帮你判对错", "逐个字母念，自动识别对错", (236, 72, 153)),
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
    dev_w = 776
    dev_h = round(dev_w * shot.height / shot.width)
    dev_x = (W - dev_w) // 2
    dev_y = H - dev_h - 96

    canvas = gradient(accent)
    glow(canvas, accent, W // 2, dev_y + dev_h // 3, 560)

    body = rounded(shot.resize((dev_w, dev_h), Image.LANCZOS), 58)

    # 机身描边：一圈极淡的白，把屏幕从背景里"抠"出来。
    ring = Image.new("RGBA", (dev_w + 6, dev_h + 6), (0, 0, 0, 0))
    ImageDraw.Draw(ring).rounded_rectangle(
        [0, 0, dev_w + 5, dev_h + 5], radius=61, outline=(255, 255, 255, 46), width=3
    )
    canvas.paste(ring, (dev_x - 3, dev_y - 3), ring)
    canvas.paste(body, (dev_x, dev_y), body)

    draw = ImageDraw.Draw(canvas)

    # 标题：两行，行距 1.18；整体按可用高度垂直居中，不同长度的标题不会跳。
    lines = title.split("\n")
    lh = 104
    block_h = lh * len(lines)
    ty = (dev_y - 120 - block_h) // 2 + 40
    for i, line in enumerate(lines):
        w = draw.textlength(line, font=FONT_TITLE)
        draw.text(((W - w) / 2, ty + i * lh), line, font=FONT_TITLE, fill=INK)

    sw = draw.textlength(sub, font=FONT_SUB)
    draw.text(((W - sw) / 2, ty + block_h + 26), sub, font=FONT_SUB, fill=MUTED)

    OUT.mkdir(exist_ok=True)
    dst = OUT / name
    canvas.save(dst, "PNG", optimize=True)
    print(f"  ✓ {dst.name}  {canvas.width}×{canvas.height}")


def main() -> None:
    print(f"输出到 {OUT}/")
    for name, title, sub, accent in SHOTS:
        if (SRC / name).exists():
            build(name, title, sub, accent)
        else:
            print(f"  ✗ 缺少源文件 {name}")


if __name__ == "__main__":
    main()
