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
    # 前三张主打缠论 + 三个市场（搜索结果缩略图只露前三张）
    ("01_chan_structure.png", "缠论结构\n一键自动画出",
     "美股 · A股 · 港股，分型 笔 线段 中枢 买卖点全部标出", (139, 92, 246)),  # Theme.pivotFill 中枢
    ("02_three_markets.png", "美股 A股 港股\n一个 App 全覆盖",
     "代码按各市场习惯输入，同一套缠论结构分析", (46, 189, 133)),          # Theme.down
    ("03_fullscreen.png", "横屏全屏\n结构一目了然",
     "MACD 与成交量同屏，图层可以逐个开关", (245, 158, 11)),               # Theme.segment 线段
    ("04_radar.png", "每天的买卖点\n一张雷达图看完",
     "标普 500 · 沪深 300 · 恒生指数等成分股每天自动扫描", (96, 165, 250)),  # Theme.stroke 笔
    ("05_signal_explain.png", "每个买卖点\n都有据可查",
     "背驰力度、成立日期，真实数字逐条列出", (46, 189, 133)),
    ("06_fundamentals.png", "基本面体检\nA+ 到 F 一眼看懂",
     "估值 · 成长 · 盈利 · 动量 · 预期修正，同行业里比", (236, 72, 153)),
    ("07_report_ai.png", "上百页财报\nAI 帮你划重点",
     "关键数字、变化与风险，一切以原文为准", (245, 158, 11)),
    ("08_lesson.png", "零基础\n也能学会缠论",
     "新手入门 + 9 篇图解课程 + 名词小词典", (96, 165, 250)),
    ("09_watchlist.png", "三个市场的自选股\n结构阶段随时看",
     "技术分析与学习工具，不构成投资建议", (100, 116, 139)),
]


# 一张图里放多台手机（三市场对比）：输出文件名 → [(源图, 角标), ...]，中间那台在最前。
MULTI = {
    "02_three_markets.png": [
        ("02a_cn.png", "A股"),
        ("02b_us.png", "美股"),
        ("02c_hk.png", "港股"),
    ],
}


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


def device(p: Preset, shot: Image.Image, dev_w: int) -> tuple[Image.Image, Image.Image]:
    """按宽度缩放截图，返回（圆角机身, 描边）。"""
    s = p.scale
    dev_h = round(dev_w * shot.height / shot.width)
    body = rounded(shot.resize((dev_w, dev_h), Image.LANCZOS), round(61 * s * dev_w / (818 * s)))
    ring = Image.new("RGBA", (dev_w + 6, dev_h + 6), (0, 0, 0, 0))
    ImageDraw.Draw(ring).rounded_rectangle(
        [0, 0, dev_w + 5, dev_h + 5], radius=round(64 * s * dev_w / (818 * s)),
        outline=(255, 255, 255, 46), width=3
    )
    return body, ring


def build_multi(p: Preset, name: str, title: str, sub: str, accent: tuple[int, int, int]) -> None:
    """三台手机：两侧略小、靠后、压暗，中间一台在最前；每台头顶一个市场角标。"""
    s = p.scale
    font_title, font_sub = p.font_title, p.font_sub
    font_tag = ImageFont.truetype(FONT_PATH, round(46 * s), index=2)
    items = [(Image.open(SRC / f).convert("RGB"), tag) for f, tag in MULTI[name]]

    side_w, mid_w = round(600 * s), round(740 * s)
    mid_h = round(mid_w * items[1][0].height / items[1][0].width)
    mid_y = p.h - mid_h - round(110 * s)
    side_y = mid_y + round(170 * s)
    mid_x = (p.w - mid_w) // 2
    side_xs = [round(-60 * s), p.w - side_w + round(60 * s)]

    lines = title.split("\n")
    lh = round(110 * s)
    block_h = lh * len(lines)
    sub_gap = round(28 * s)
    tag_h = round(76 * s)
    ty = (mid_y - tag_h - round(60 * s) - block_h - sub_gap - round(45 * s)) // 2 + round(30 * s)

    canvas = gradient(p, accent)
    glow(p, canvas, accent, p.w // 2, mid_y + mid_h // 3, round(640 * s))
    draw = ImageDraw.Draw(canvas)

    def tag(text: str, cx: int, top: int, strong: bool) -> None:
        w = draw.textlength(text, font=font_tag) + round(56 * s)
        margin = round(36 * s)
        cx = min(max(cx, margin + w / 2), p.w - margin - w / 2)  # 不出画布
        box = [cx - w / 2, top, cx + w / 2, top + tag_h]
        fill = tuple(min(255, int(c * 0.9 + 20)) for c in accent) if strong else (38, 46, 62)
        draw.rounded_rectangle(box, radius=tag_h // 2, fill=fill)
        tw = draw.textlength(text, font=font_tag)
        draw.text((cx - tw / 2, top + round(12 * s)), text, font=font_tag, fill=INK)

    # 两侧（先画，被中间那台压住一部分），压暗 25% 拉开前后层次
    for (shot, label), x in zip([items[0], items[2]], side_xs):
        body, ring = device(p, shot, side_w)
        dim = Image.new("RGBA", body.size, (0, 0, 0, 0))
        dim.putalpha(body.getchannel("A").point(lambda a: a * 64 // 255))
        canvas.paste(ring, (x - 3, side_y - 3), ring)
        canvas.paste(body, (x, side_y), body)
        canvas.paste(dim, (x, side_y), dim)
    # 中间
    shot, label = items[1]
    body, ring = device(p, shot, mid_w)
    shadow = Image.new("RGBA", (mid_w + 80, mid_h + 80), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([40, 40, mid_w + 40, mid_h + 40], radius=round(70 * s), fill=(0, 0, 0, 170))
    shadow = shadow.filter(ImageFilter.GaussianBlur(round(30 * s)))
    canvas.paste(shadow, (mid_x - 40, mid_y - 30), shadow)
    canvas.paste(ring, (mid_x - 3, mid_y - 3), ring)
    canvas.paste(body, (mid_x, mid_y), body)
    # 角标最后画，不会被机身挡住；两侧的居中在露出来的那一截上
    tag(label, p.w // 2, mid_y - tag_h - round(28 * s), True)
    left_vis = (max(side_xs[0], 0) + mid_x) // 2
    right_vis = (mid_x + mid_w + min(side_xs[1] + side_w, p.w)) // 2
    tag(items[0][1], left_vis, side_y - tag_h - round(28 * s), False)
    tag(items[2][1], right_vis, side_y - tag_h - round(28 * s), False)

    for i, line in enumerate(lines):
        w = draw.textlength(line, font=font_title)
        draw.text(((p.w - w) / 2, ty + i * lh), line, font=font_title, fill=INK)
    sw = draw.textlength(sub, font=font_sub)
    draw.text(((p.w - sw) / 2, ty + block_h + sub_gap), sub, font=font_sub, fill=MUTED)

    out_dir = BASE / p.out
    out_dir.mkdir(exist_ok=True)
    canvas.save(out_dir / name, "PNG", optimize=True)
    print(f"  ✓ {name}  {canvas.width}×{canvas.height}（三机位）")


def build(p: Preset, name: str, title: str, sub: str, accent: tuple[int, int, int]) -> None:
    if name in MULTI:
        build_multi(p, name, title, sub, accent)
        return
    shot = Image.open(SRC / name).convert("RGB")
    s = p.scale
    font_title, font_sub = p.font_title, p.font_sub
    landscape = shot.width > shot.height

    # 竖版：机身宽度 62%，贴着画布底部，上方留给两行大标题。
    # 横版（全屏图表那张）：机身放宽到 92%，否则一条又矮又窄的图什么都看不清；
    # 因为它很矮，贴底会在标题和机身之间留一大片空，改成在下半区居中。
    # 两种情况下高度都按**源图**比例算，所以换画布尺寸不会把截图拉变形。
    dev_w = round((1214 if landscape else 818) * s)
    dev_h = round(dev_w * shot.height / shot.width)
    dev_x = (p.w - dev_w) // 2

    # 标题排版度量。横版要先知道标题块多高才能定机身位置，所以提前算。
    lines = title.split("\n")
    lh = round(110 * s)
    block_h = lh * len(lines)
    sub_gap = round(28 * s)
    title_h = block_h + sub_gap + round(45 * s)

    if landscape:
        # 横版机身只有画布高度的两成，贴底或居中都会在某一侧空出一大片。
        # 把「标题块 + 机身」当成一个整体在画布里垂直居中，上下留白才对称。
        gap = round(150 * s)
        top = (p.h - (title_h + gap + dev_h)) // 2
        ty = top
        dev_y = top + title_h + gap
    else:
        dev_y = p.h - dev_h - round(102 * s)
        # 竖版：标题块在机身上方的空间里居中，不同长度的标题不会跳
        ty = (dev_y - round(128 * s) - block_h) // 2 + round(42 * s)

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

    # 标题：每行行距 1.18，居中排版；位置 ty 在上面按版式算好了。
    for i, line in enumerate(lines):
        w = draw.textlength(line, font=font_title)
        draw.text(((p.w - w) / 2, ty + i * lh), line, font=font_title, fill=INK)

    sw = draw.textlength(sub, font=font_sub)
    draw.text(((p.w - sw) / 2, ty + block_h + sub_gap), sub, font=font_sub, fill=MUTED)

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

    sources = [f for name, *_ in SHOTS for f in ([x for x, _ in MULTI[name]] if name in MULTI else [name])]
    missing = [f for f in sources if not (SRC / f).exists()]
    if missing:
        raise SystemExit(f"缺少 {len(missing)} 张源截图：{missing}")

    for key in wanted:
        p = PRESETS[key]
        print(f"\n{p.name} 寸 → {p.out}/  ({p.w}×{p.h})")
        for name, title, sub, accent in SHOTS:
            build(p, name, title, sub, accent)


if __name__ == "__main__":
    main()
