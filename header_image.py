"""头图处理模块

提供带边缘蒙版效果的头图处理：裁切/缩放并在图片边缘应用渐变/装饰蒙版，
使头图与章节内容自然融合。依赖 Pillow（PIL）。
"""

import io
import os
import random
import math
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageChops
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# 边缘样式注册表：key → (中文名, 处理函数)
EDGE_STYLES: list = []
_MASK_FUNCS: dict = {}


def _register(key: str, name: str):
    def decorator(fn):
        EDGE_STYLES.append({"key": key, "name": name})
        _MASK_FUNCS[key] = fn
        return fn
    return decorator


def list_edge_styles() -> list:
    """返回所有可用边缘样式 [{key, name}]。"""
    return list(EDGE_STYLES)


# ── 蒙版生成函数 ──────────────────────────────────────────────────

@_register("none", "无")
def _mask_none(w: int, h: int, seed: int = 0) -> Optional["Image.Image"]:
    return None   # 不加蒙版


@_register("fade", "底部渐隐")
def _mask_fade(w: int, h: int, seed: int = 0) -> "Image.Image":
    mask = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(mask)
    fade_h = int(h * 0.35)
    for y in range(fade_h):
        alpha = int(255 * (y / fade_h))
        draw.line([(0, h - fade_h + y), (w, h - fade_h + y)], fill=alpha)
    return mask


@_register("cloud", "云边")
def _mask_cloud(w: int, h: int, seed: int = 0) -> "Image.Image":
    rng = random.Random(seed)
    mask = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(mask)
    # 底部云朵轮廓（多个半圆拼接）
    base_y = int(h * 0.75)
    draw.rectangle([(0, base_y), (w, h)], fill=0)
    cx = 0
    while cx < w + 60:
        r = rng.randint(30, 70)
        cy = base_y + rng.randint(-10, 10)
        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=255)
        cx += rng.randint(40, 90)
    # 底部完全透明
    draw.rectangle([(0, base_y + 60), (w, h)], fill=0)
    return mask


@_register("mist", "雾边")
def _mask_mist(w: int, h: int, seed: int = 0) -> "Image.Image":
    mask = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(mask)
    fade_h = int(h * 0.5)
    rng = random.Random(seed)
    for y in range(fade_h):
        base = int(255 * (y / fade_h))
        noise = rng.randint(-20, 20)
        alpha = max(0, min(255, base + noise))
        draw.line([(0, h - fade_h + y), (w, h - fade_h + y)], fill=alpha)
    return mask.filter(ImageFilter.GaussianBlur(radius=8))


@_register("torn", "撕纸边")
def _mask_torn(w: int, h: int, seed: int = 0) -> "Image.Image":
    rng = random.Random(seed)
    mask = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(mask)
    tear_y = int(h * 0.78)
    pts = [(0, tear_y)]
    x = 0
    while x < w:
        x += rng.randint(8, 25)
        dy = rng.randint(-18, 18)
        pts.append((min(x, w), tear_y + dy))
    pts.append((w, tear_y))
    pts.append((w, h))
    pts.append((0, h))
    draw.polygon(pts, fill=0)
    return mask


@_register("rough", "粗糙边")
def _mask_rough(w: int, h: int, seed: int = 0) -> "Image.Image":
    rng = random.Random(seed)
    mask = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(mask)
    base_y = int(h * 0.80)
    # 粗糙噪点边缘
    for x in range(w):
        noise = rng.randint(0, 30)
        draw.line([(x, base_y + noise), (x, h)], fill=0)
    return mask.filter(ImageFilter.GaussianBlur(radius=2))


@_register("oval", "椭圆边")
def _mask_oval(w: int, h: int, seed: int = 0) -> "Image.Image":
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    pad_x, pad_y = int(w * 0.05), int(h * 0.08)
    draw.ellipse([(pad_x, pad_y), (w - pad_x, h - pad_y)], fill=255)
    return mask.filter(ImageFilter.GaussianBlur(radius=12))


def _rot_ellipse(w: int, h: int, cx: float, cy: float,
                 rw: float, rh: float, angle: float) -> "Image.Image":
    """生成旋转椭圆透明层（被 brush/watercolor/brushframe 使用）。"""
    layer = Image.new("L", (w, h), 0)
    e = Image.new("L", (int(rw * 2) + 4, int(rh * 2) + 4), 0)
    ImageDraw.Draw(e).ellipse([2, 2, int(rw * 2) + 2, int(rh * 2) + 2], fill=255)
    e = e.rotate(angle, expand=True, resample=Image.BICUBIC)
    layer.paste(e, (int(cx - e.width / 2), int(cy - e.height / 2)), e)
    return layer


@_register("splash", "泼溅边")
def _mask_splash(w: int, h: int, seed: int = 0) -> "Image.Image":
    rnd = random.Random(seed)
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.rectangle([60, 50, w - 60, h - 50], fill=255)
    for _ in range(260):
        side = rnd.choice("tblr")
        if side == "t":   cx, cy = rnd.randint(0, w), int(50 + rnd.gauss(0, 28))
        elif side == "b": cx, cy = rnd.randint(0, w), int(h - 50 + rnd.gauss(0, 28))
        elif side == "l": cx, cy = int(60 + rnd.gauss(0, 28)), rnd.randint(0, h)
        else:             cx, cy = int(w - 60 + rnd.gauss(0, 28)), rnd.randint(0, h)
        r = max(2, int(rnd.gauss(8, 6)))
        md.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    return mask.filter(ImageFilter.GaussianBlur(3))


@_register("brush", "拖墨边")
def _mask_brush(w: int, h: int, seed: int = 0) -> "Image.Image":
    rnd = random.Random(seed)
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.rectangle([0, 0, w, h - 55], fill=255)
    for i in range(5):
        cx = w * 0.35 + i * w * 0.14 + rnd.randint(-15, 15)
        layer = _rot_ellipse(w, h, cx, h - 40 + rnd.randint(-12, 12),
                             rnd.randint(140, 260), rnd.randint(10, 22),
                             -6 + rnd.randint(-3, 3))
        mask = ImageChops.lighter(mask, layer)
    return mask.filter(ImageFilter.GaussianBlur(8))


@_register("watercolor", "晕染边")
def _mask_watercolor(w: int, h: int, seed: int = 0) -> "Image.Image":
    rnd = random.Random(seed)
    mask = Image.new("L", (w, h), 0)
    for _ in range(6):
        cx = w / 2 + rnd.randint(-int(w * 0.12), int(w * 0.12))
        cy = h / 2 + rnd.randint(-int(h * 0.14), int(h * 0.14))
        rw = rnd.randint(int(w * 0.30), int(w * 0.46))
        rh = rnd.randint(int(h * 0.28), int(h * 0.44))
        layer = _rot_ellipse(w, h, cx, cy, rw, rh, rnd.randint(-25, 25))
        mask = ImageChops.lighter(mask, layer)
    return mask.filter(ImageFilter.GaussianBlur(18))


@_register("tornframe", "撕框边")
def _mask_tornframe(w: int, h: int, seed: int = 0) -> "Image.Image":
    rnd = random.Random(seed)
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    inx, iny = int(w * 0.05), int(h * 0.08)
    md.rectangle([inx, iny, w - inx, h - iny], fill=255)
    dmax = int(min(w, h) * 0.045)
    for _ in range(130):
        side = rnd.choice("tblr")
        t = rnd.uniform(0.03, 0.97)
        depth = int(rnd.uniform(dmax * 0.3, dmax))
        half = max(3, int(dmax * rnd.uniform(0.6, 1.6)))
        outward = rnd.random() < 0.5
        if side == "t":
            cx, y = int(w * t), iny + rnd.randint(-8, 8)
            peak = y - depth if outward else y + depth
            md.polygon([(cx - half, y), (cx + half, y), (cx, peak)], fill=255 if outward else 0)
        elif side == "b":
            cx, y = int(w * t), h - iny + rnd.randint(-8, 8)
            peak = y + depth if outward else y - depth
            md.polygon([(cx - half, y), (cx + half, y), (cx, peak)], fill=255 if outward else 0)
        elif side == "l":
            cy, x = int(h * t), inx + rnd.randint(-8, 8)
            peak = x - depth if outward else x + depth
            md.polygon([(x, cy - half), (x, cy + half), (peak, cy)], fill=255 if outward else 0)
        else:
            cy, x = int(h * t), w - inx + rnd.randint(-8, 8)
            peak = x + depth if outward else x - depth
            md.polygon([(x, cy - half), (x, cy + half), (peak, cy)], fill=255 if outward else 0)
    for _ in range(150):
        side = rnd.choice("tblr")
        t = rnd.uniform(0, 1)
        ln = rnd.randint(3, 10)
        if side == "t":
            x, y = int(w * t), iny + rnd.randint(-4, 4)
            md.line([(x, y), (x + rnd.randint(-4, 4), y - ln)], fill=255, width=1)
        elif side == "b":
            x, y = int(w * t), h - iny + rnd.randint(-4, 4)
            md.line([(x, y), (x + rnd.randint(-4, 4), y + ln)], fill=255, width=1)
        elif side == "l":
            x, y = inx + rnd.randint(-4, 4), int(h * t)
            md.line([(x, y), (x - ln, y + rnd.randint(-4, 4))], fill=255, width=1)
        else:
            x, y = w - inx + rnd.randint(-4, 4), int(h * t)
            md.line([(x, y), (x + ln, y + rnd.randint(-4, 4))], fill=255, width=1)
    return mask.filter(ImageFilter.GaussianBlur(3))


@_register("deckle", "毛边")
def _mask_deckle(w: int, h: int, seed: int = 0) -> "Image.Image":
    rnd = random.Random(seed)
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    cut = int(h * 0.035)
    md.rectangle([0, 0, w, h - cut], fill=255)
    x = 0
    while x < w:
        ln = rnd.randint(2, cut + int(h * 0.012))
        md.line([(x, h - cut), (x + rnd.randint(-2, 2), h - cut + ln)], fill=255,
                width=rnd.randint(1, 3))
        x += rnd.randint(2, 6)
    for _ in range(60):
        x = rnd.randint(0, w)
        up = rnd.randint(2, cut)
        md.polygon([(x - rnd.randint(2, 6), h - cut), (x + rnd.randint(2, 6), h - cut),
                    (x, h - cut + up)], fill=0)
    x = 0
    while x < w:
        if rnd.random() < 0.5:
            ln = rnd.randint(2, int(cut * 0.8))
            md.line([(x, h - cut - rnd.randint(0, 4)), (x, h - cut + ln)], fill=255, width=1)
        x += rnd.randint(3, 8)
    return mask.filter(ImageFilter.GaussianBlur(1))


@_register("brushframe", "笔刷框")
def _mask_brushframe(w: int, h: int, seed: int = 0) -> "Image.Image":
    rnd = random.Random(seed)
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    x0, y0, x1, y1 = int(w * 0.045), int(h * 0.10), int(w * 0.955), int(h * 0.90)
    md.rounded_rectangle([x0, y0, x1, y1], radius=int(min(w, h) * 0.05), fill=255)
    for _ in range(140):
        side = rnd.choice("tblr")
        t = rnd.uniform(0.02, 0.98)
        th = max(2, int(min(w, h) * rnd.uniform(0.004, 0.014)))
        ln = min(w, h) * rnd.uniform(0.04, 0.16)
        bleed = int(min(w, h) * rnd.uniform(0.005, 0.028))
        if side == "t":
            cx, cy = w * t, y0 + rnd.randint(-5, 5) - bleed
            layer = _rot_ellipse(w, h, cx, cy, ln / 2, th, rnd.uniform(-4, 4))
        elif side == "b":
            cx, cy = w * t, y1 + rnd.randint(-5, 5) + bleed
            layer = _rot_ellipse(w, h, cx, cy, ln / 2, th, rnd.uniform(-4, 4))
        elif side == "l":
            cx, cy = x0 + rnd.randint(-5, 5) - bleed, h * t
            layer = _rot_ellipse(w, h, cx, cy, th, ln / 2, rnd.uniform(-4, 4))
        else:
            cx, cy = x1 + rnd.randint(-5, 5) + bleed, h * t
            layer = _rot_ellipse(w, h, cx, cy, th, ln / 2, rnd.uniform(-4, 4))
        mask = ImageChops.lighter(mask, layer)
    for _ in range(30):
        side = rnd.choice("tblr")
        t = rnd.uniform(0.05, 0.95)
        if side == "t":
            cy = y0 + rnd.randint(2, 10)
            md.line([(w * t - rnd.randint(20, 60), cy), (w * t + rnd.randint(20, 60), cy)],
                    fill=0, width=rnd.randint(1, 3))
        elif side == "b":
            cy = y1 - rnd.randint(2, 10)
            md.line([(w * t - rnd.randint(20, 60), cy), (w * t + rnd.randint(20, 60), cy)],
                    fill=0, width=rnd.randint(1, 3))
        elif side == "l":
            cx = x0 + rnd.randint(2, 10)
            md.line([(cx, h * t - rnd.randint(15, 45)), (cx, h * t + rnd.randint(15, 45))],
                    fill=0, width=rnd.randint(1, 2))
        else:
            cx = x1 - rnd.randint(2, 10)
            md.line([(cx, h * t - rnd.randint(15, 45)), (cx, h * t + rnd.randint(15, 45))],
                    fill=0, width=rnd.randint(1, 2))
    return mask.filter(ImageFilter.GaussianBlur(1.5))


# ── 公开 API ───────────────────────────────────────────────────

def make_header(
    img_path: str,
    edge_style: str = "fade",
    target_w: int = 1200,
    target_h: int = 400,
    quality: int = 85,
    seed: int = 0,
) -> Optional[bytes]:
    """处理头图：裁切/缩放，并应用边缘蒙版，返回 JPEG bytes。

    Args:
        img_path:   原始图片路径
        edge_style: 边缘样式 key（见 list_edge_styles()）
        target_w:   输出宽度（像素）
        target_h:   输出高度（像素）
        quality:    JPEG 压缩质量 1-95
        seed:       随机蒙版的随机种子

    Returns:
        JPEG bytes，或 None（图片不存在或 PIL 不可用时）
    """
    if not PIL_AVAILABLE:
        return None
    if not os.path.isfile(img_path):
        return None
    try:
        img = Image.open(img_path).convert("RGBA")
    except Exception:
        return None

    # 等比缩放并居中裁切到 target_w x target_h
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top  = (new_h - target_h) // 2
    img = img.crop((left, top, left + target_w, top + target_h))

    # 应用边缘蒙版
    mask_fn = _MASK_FUNCS.get(edge_style, _mask_none)
    mask = mask_fn(target_w, target_h, seed)
    if mask is not None:
        img.putalpha(mask)

    # 转 RGB（JPEG 不支持 alpha）
    bg = Image.new("RGB", (target_w, target_h), (255, 255, 255))
    if img.mode == "RGBA":
        bg.paste(img, mask=img.split()[3])
    else:
        bg.paste(img)

    buf = io.BytesIO()
    bg.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()
