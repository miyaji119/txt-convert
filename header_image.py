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
    from PIL import Image, ImageDraw, ImageFilter
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
