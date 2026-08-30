"""交易台 App 图标：多路观点汇聚成一条结论。

缠论 App 的图标已经是「K 线 + 缠论笔」，交易台再画 K 线会撞脸。这里画的是
产品自己的差异点——多个 agent 各持立场（绿=看多 / 橙=中性 / 红=看空），
汇聚到一个节点后输出一条向上的裁决。

两个实现要点：
- 4 倍超采样再缩小：PIL 画线没有抗锯齿，不这么做边缘全是锯齿。
- 线端补圆点：PIL 的 line 是方头，直连处会露出直角小毛刺。
"""
import math
from PIL import Image, ImageDraw, ImageFilter

S, SS = 1024, 4
W = S * SS

BG = (11, 14, 20)           # Theme.background
BULL = (46, 189, 133)       # Theme.bull
NEUTRAL = (245, 158, 11)    # Theme.neutral
BEAR = (246, 70, 93)        # Theme.bear
ACCENT = (59, 130, 246)     # Theme.accent


def sc(v):
    return int(round(v * SS))


def round_line(draw, p0, p1, color, width):
    """圆头线段：方头线 + 两端补圆，避免拐角/端点出现直角毛刺。"""
    draw.line([sc(p0[0]), sc(p0[1]), sc(p1[0]), sc(p1[1])],
              fill=color, width=sc(width))
    r = sc(width / 2)
    for (x, y) in (p0, p1):
        draw.ellipse([sc(x) - r, sc(y) - r, sc(x) + r, sc(y) + r], fill=color)


img = Image.new("RGB", (W, W), BG)

# ── 背景光晕：单独图层高斯模糊，避免同心圆画出「年轮」──────────
glow = Image.new("RGB", (W, W), BG)
gd = ImageDraw.Draw(glow)
gr = sc(300)
gd.ellipse([sc(512) - gr, sc(512) - gr, sc(512) + gr, sc(512) + gr],
           fill=(32, 44, 64))
img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(sc(90))), 1.0)

d = ImageDraw.Draw(img, "RGBA")

HUB = (498, 528)
DOT_X = 232
inputs = [((DOT_X, 318), BULL), ((DOT_X, 528), NEUTRAL), ((DOT_X, 738), BEAR)]

# ── 三路观点直连汇聚点。直连比折线在小尺寸下更清晰 ──────────────
for (x, y), color in inputs:
    round_line(d, (x, y), HUB, color + (255,), 30)
for (x, y), color in inputs:
    r = sc(45)                       # 起点圆点画在连线之上，边缘更干净
    d.ellipse([sc(x) - r, sc(y) - r, sc(x) + r, sc(y) + r], fill=color + (255,))

# ── 输出：向右上冲出的裁决线 + 箭头 ───────────────────────────
TIP = (836, 344)
SHAFT = 58
ang = math.atan2(TIP[1] - HUB[1], TIP[0] - HUB[0])
HEAD_L, HEAD_HW = 146, 96            # 箭头长度 / 半宽：略大于线宽即可，不要压过线
# 线画到箭头根部，免得线头从三角形侧面透出来
bx, by = TIP[0] - HEAD_L * math.cos(ang), TIP[1] - HEAD_L * math.sin(ang)
round_line(d, HUB, (bx, by), ACCENT + (255,), SHAFT)

px, py = -math.sin(ang), math.cos(ang)
d.polygon([
    (sc(TIP[0]), sc(TIP[1])),
    (sc(bx + px * HEAD_HW), sc(by + py * HEAD_HW)),
    (sc(bx - px * HEAD_HW), sc(by - py * HEAD_HW)),
], fill=ACCENT + (255,))

# ── 汇聚节点：盖在所有线之上，让「多路收束于此」读得出来 ─────────
halo = sc(104)
d.ellipse([sc(HUB[0]) - halo, sc(HUB[1]) - halo,
           sc(HUB[0]) + halo, sc(HUB[1]) + halo], fill=ACCENT + (46,))
core = sc(74)
d.ellipse([sc(HUB[0]) - core, sc(HUB[1]) - core,
           sc(HUB[0]) + core, sc(HUB[1]) + core], fill=ACCENT + (255,))
inner = sc(30)
d.ellipse([sc(HUB[0]) - inner, sc(HUB[1]) - inner,
           sc(HUB[0]) + inner, sc(HUB[1]) + inner], fill=(232, 240, 254, 255))

# 主体占比偏小，居中裁掉一圈再放回 1024（等效整体放大约 13%）。
# iOS 图标主体通常要占到七成以上，留白太多会显得"缩水"。
inset = int(W * 0.058)
img = img.crop((inset, inset, W - inset, W - inset))

img.resize((S, S), Image.LANCZOS).save("/tmp/iconwork/icon-1024.png")

# 顺带出一张 120px 的缩略图，检查小尺寸下还认不认得出
img.resize((120, 120), Image.LANCZOS).save("/tmp/iconwork/icon-120.png")
print("已生成 icon-1024.png 与 icon-120.png")

# 用法：
#   cd ios/DeepAlphaClub
#   uv run --with pillow python Tools/make_icon.py
#   cp /tmp/iconwork/icon-1024.png App/Assets.xcassets/AppIcon.appiconset/


def build_tinted():
    """iOS 18+「着色」模式专用版。

    系统在这个模式下会取图标的明度信息、用用户选的单色重新着色。直接拿彩色版
    去转，三条同亮度的彩色线会糊成一团分不开——所以这里改用明度分层：
    结论箭头最亮，三路观点按看多/中性/看空递减，形状层次靠明度而不是色相撑。
    """
    img = Image.new("RGB", (W, W), (0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")

    lum = [(232, 232, 232), (176, 176, 176), (128, 128, 128)]
    for ((x, y), _), grey in zip(inputs, lum):
        round_line(d, (x, y), HUB, grey + (255,), 30)
    for ((x, y), _), grey in zip(inputs, lum):
        r = sc(45)
        d.ellipse([sc(x) - r, sc(y) - r, sc(x) + r, sc(y) + r], fill=grey + (255,))

    white = (255, 255, 255)
    round_line(d, HUB, (bx, by), white + (255,), SHAFT)
    d.polygon([
        (sc(TIP[0]), sc(TIP[1])),
        (sc(bx + px * HEAD_HW), sc(by + py * HEAD_HW)),
        (sc(bx - px * HEAD_HW), sc(by - py * HEAD_HW)),
    ], fill=white + (255,))
    core = sc(74)
    d.ellipse([sc(HUB[0]) - core, sc(HUB[1]) - core,
               sc(HUB[0]) + core, sc(HUB[1]) + core], fill=white + (255,))

    inset2 = int(W * 0.058)
    out = img.crop((inset2, inset2, W - inset2, W - inset2))
    out.resize((S, S), Image.LANCZOS).save("/tmp/iconwork/icon-tinted.png")
    print("已生成 icon-tinted.png")


build_tinted()
