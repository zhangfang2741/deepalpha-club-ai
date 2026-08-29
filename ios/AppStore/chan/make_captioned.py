#!/usr/bin/env python3
"""给缠论 App 的截图加标题文案，输出可直接上传 App Store 的图。

用法（不需要装依赖到项目里）：
    # 两种尺寸都出
    uv run --with pillow --no-project python ios/AppStore/chan/make_captioned.py
    # 只出某一种
    uv run --with pillow --no-project python ios/AppStore/chan/make_captioned.py 6.5

沿用 ../make_captioned.py 那套视觉：深色渐变 + 大标题 + 圆角机身 + 柔光。

**为什么要出两种尺寸**：App Store Connect 的 iPhone 截图按显示尺寸分区上传，
6.9 寸区收 1320×2868，6.5 寸区只收 1242×2688 / 1284×2778，传错区会报
「截屏尺寸存在错误」。这里画布尺寸与源截图解耦——机身是把源图按比例缩放后
贴上去的，换画布不会让截图变形，只是背景留白多少的差别。

金融类 App 的额外约束：标题里不能出现任何暗示收益或荐股的词。这里全部说的是
「画出结构」「给出依据」这类工具属性，最后一张直接把免责讲在标题上——
审核员翻截图时第一眼就能看到我们没在卖预测。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE = Path(__file__).parent
SRC = BASE / "screenshots-6.9"   # 源图统一用模拟器截出的 1320×2868

# Hiragino Sans GB：index 2 = W6（粗，做标题），index 0 = W3（细，做副标题）。
FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"


@dataclass(frozen=True)
class Preset:
    """一种上传尺寸的全部排版参数。字号与间距按画布宽度等比缩放。"""
    name: str
    w: int
    h: int
    out: str

    @property
    def scale(self) -> float:
        return self.w / 1320

    @property
    def font_title(self) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(FONT_PATH, round(93 * self.scale), index=2)

    @property
    def font_sub(self) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(FONT_PATH, round(45 * self.scale), index=0)


PRESETS = {
    # 6.9 寸（iPhone 16/17 Pro Max）
    "6.9": Preset("6.9", 1320, 2868, "screenshots-6.9-captioned"),
    # 6.5 寸（iPhone 11 Pro Max / XS Max）。ASC 的 6.5 区也接受 1284×2778，
    # 但 1242×2688 兼容面更广，与 WordLens 那套保持一致。
    "6.5": Preset("6.5", 1242, 2688, "screenshots-6.5-captioned"),
}

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


def gradient(p: Preset, accent: tuple[int, int, int]) -> Image.Image:
    """顶部透出主色、向下收敛到接近纯黑的竖向渐变。"""
    top = tuple(int(c * 0.22 + 11) for c in accent)
    bottom = (8, 10, 15)
    grad = Image.new("RGB", (1, p.h))
    px = grad.load()
    for y in range(p.h):
        t = (y / p.h) ** 0.75  # 前段变化快一些，色彩集中在标题区
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return grad.resize((p.w, p.h))


def glow(
    p: Preset, canvas: Image.Image, accent: tuple[int, int, int], cx: int, cy: int, r: int
) -> None:
    """机身后面垫一团柔光，避免深色截图直接糊在深色背景上分不出层次。"""
    layer = Image.new("RGB", (p.w, p.h), (0, 0, 0))
    ImageDraw.Draw(layer).ellipse([cx - r, cy - r // 2, cx + r, cy + r // 2], fill=accent)
    layer = layer.filter(ImageFilter.GaussianBlur(round(200 * p.scale)))
    canvas.paste(Image.blend(canvas, Image.blend(canvas, layer, 0.30), 1.0), (0, 0))


def rounded(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, *img.size], radius=radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def build(p: Preset, name: str, title: str, sub: str, accent: tuple[int, int, int]) -> None:
    shot = Image.open(SRC / name).convert("RGB")
    s = p.scale
    font_title, font_sub = p.font_title, p.font_sub

    # 机身宽度定在 62%：留足顶部空间放两行大标题，同时底部不贴边。
    # 高度按**源图**比例算，所以换画布尺寸不会把截图拉变形。
    dev_w = round(818 * s)
    dev_h = round(dev_w * shot.height / shot.width)
    dev_x = (p.w - dev_w) // 2
    dev_y = p.h - dev_h - round(102 * s)

    canvas = gradient(p, accent)
    glow(p, canvas, accent, p.w // 2, dev_y + dev_h // 3, round(595 * s))

    body = rounded(shot.resize((dev_w, dev_h), Image.LANCZOS), round(61 * s))

    # 机身描边：一圈极淡的白，把屏幕从背景里「抠」出来。
    ring = Image.new("RGBA", (dev_w + 6, dev_h + 6), (0, 0, 0, 0))
    ImageDraw.Draw(ring).rounded_rectangle(
        [0, 0, dev_w + 5, dev_h + 5], radius=round(64 * s), outline=(255, 255, 255, 46), width=3
    )
    canvas.paste(ring, (dev_x - 3, dev_y - 3), ring)
    canvas.paste(body, (dev_x, dev_y), body)

    draw = ImageDraw.Draw(canvas)

    # 标题：两行，行距 1.18；整体按可用高度垂直居中，不同长度的标题不会跳。
    lines = title.split("\n")
    lh = round(110 * s)
    block_h = lh * len(lines)
    ty = (dev_y - round(128 * s) - block_h) // 2 + round(42 * s)
    for i, line in enumerate(lines):
        w = draw.textlength(line, font=font_title)
        draw.text(((p.w - w) / 2, ty + i * lh), line, font=font_title, fill=INK)

    sw = draw.textlength(sub, font=font_sub)
    draw.text(((p.w - sw) / 2, ty + block_h + round(28 * s)), sub, font=font_sub, fill=MUTED)

    out_dir = BASE / p.out
    out_dir.mkdir(exist_ok=True)
    dst = out_dir / name
    canvas.save(dst, "PNG", optimize=True)
    print(f"  ✓ {dst.name}  {canvas.width}×{canvas.height}")


def main() -> None:
    wanted = sys.argv[1:] or list(PRESETS)
    unknown = [k for k in wanted if k not in PRESETS]
    if unknown:
        raise SystemExit(f"未知尺寸 {unknown}，可选：{list(PRESETS)}")

    missing = [name for name, *_ in SHOTS if not (SRC / name).exists()]
    if missing:
        raise SystemExit(f"缺少 {len(missing)} 张源截图：{missing}")

    for key in wanted:
        p = PRESETS[key]
        print(f"\n{p.name} 寸 → {p.out}/  ({p.w}×{p.h})")
        for name, title, sub, accent in SHOTS:
            build(p, name, title, sub, accent)


if __name__ == "__main__":
    main()
