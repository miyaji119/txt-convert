"""自动封面生成模块 — 参照 BookCrafter 风格

使用 Pillow 从书名/作者生成 EPUB 封面，无需外部资源。
提供 5 种预设风格，自动适配系统 CJK 字体。
"""
from __future__ import annotations

import io
import os
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

COVER_W = 600
COVER_H = 900
THUMB_W = 120
THUMB_H = 180

# ── 风格元数据 ────────────────────────────────────────────────────
STYLE_PRESETS: dict[str, dict] = {
    "minimal_light": {
        "name": "留白·默认",
        "desc": "暖米白底，大标题居中，细横线分割，经典留白",
        "thumb_bg": "#f5f0e8",
        "thumb_bg_end": "#f5f0e8",
        "thumb_text_color": "#1a1a1a",
        "thumb_sub_color": "#777777",
        "thumb_accent": "#c8bba8",
        "mock_title": "书名",
        "mock_author": "作者",
    },
    "dark_elegance": {
        "name": "装帧·典藏",
        "desc": "深绿布面，居中奶白标签，图书馆装帧感",
        "thumb_bg": "#1f3329",
        "thumb_bg_end": "#1f3329",
        "thumb_text_color": "#f5f0e8",
        "thumb_sub_color": "#c8bba8",
        "thumb_accent": "#f5f0e8",
        "mock_title": "书名",
        "mock_author": "作者",
    },
    "gradient_vivid": {
        "name": "现代·编辑",
        "desc": "黑色版头嵌标题，白色书面，横纹纹理",
        "thumb_bg": "#181818",
        "thumb_bg_end": "#f5f5f5",
        "thumb_text_color": "#f5f0e8",
        "thumb_sub_color": "#444444",
        "thumb_accent": "#cccccc",
        "mock_title": "书名",
        "mock_author": "作者",
    },
    "ink_classical": {
        "name": "版框·古风",
        "desc": "纸色底，双重版框，朱红印章，宋体标题",
        "thumb_bg": "#e8d4a8",
        "thumb_bg_end": "#e8d4a8",
        "thumb_text_color": "#2c1800",
        "thumb_sub_color": "#8b4513",
        "thumb_accent": "#c0392b",
        "mock_title": "书名",
        "mock_author": "作者",
    },
    "literary_warm": {
        "name": "日常·治愈",
        "desc": "暖米底，金色圆形，温柔素净质感",
        "thumb_bg": "#f2e8cf",
        "thumb_bg_end": "#f2e8cf",
        "thumb_text_color": "#2c1800",
        "thumb_sub_color": "#7a5c2a",
        "thumb_accent": "#c49a3c",
        "mock_title": "书名",
        "mock_author": "作者",
    },
}

# ── 字体查找 ──────────────────────────────────────────────────────
_SANS_CANDIDATES = [
    ("/System/Library/Fonts/PingFang.ttc", 5),
    ("/System/Library/Fonts/PingFang.ttc", 4),
    ("/System/Library/Fonts/PingFang.ttc", 0),
    ("/System/Library/Fonts/STHeiti Medium.ttc", 0),
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
    ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
]
_SANS_LIGHT_CANDIDATES = [
    ("/System/Library/Fonts/PingFang.ttc", 3),
    ("/System/Library/Fonts/PingFang.ttc", 0),
    ("/System/Library/Fonts/STHeiti Light.ttc", 0),
]
_SERIF_CANDIDATES = [
    ("/System/Library/Fonts/Songti.ttc", 0),
    ("/System/Library/Fonts/STSong.ttf", 0),
    ("/usr/share/fonts/truetype/arphic/ukai.ttc", 0),
]

_font_cache: dict = {}


def _resolve_font_path(candidates: list) -> tuple[Optional[str], int]:
    key = candidates[0][0] if candidates else ''
    if key in _font_cache:
        return _font_cache[key]
    for path, idx in candidates:
        if os.path.exists(path):
            _font_cache[key] = (path, idx)
            return path, idx
    _font_cache[key] = (None, 0)
    return None, 0


def _load_font(size: int, style: str = 'sans') -> 'ImageFont.FreeTypeFont':
    if not _PIL_OK:
        return None
    if style == 'serif':
        path, idx = _resolve_font_path(_SERIF_CANDIDATES)
        if path is None:
            path, idx = _resolve_font_path(_SANS_CANDIDATES)
    elif style == 'light':
        path, idx = _resolve_font_path(_SANS_LIGHT_CANDIDATES)
    else:
        path, idx = _resolve_font_path(_SANS_CANDIDATES)

    if path:
        for try_idx in [idx, 0]:
            try:
                return ImageFont.truetype(path, size, index=try_idx)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


# ── 绘制工具 ──────────────────────────────────────────────────────

def _wrap_title(text: str, max_chars: int = 8) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    mid = (len(text) + 1) // 2
    return [text[:mid], text[mid:]]


def _text_block_h(lines: list, font, line_gap: int = 12) -> int:
    total = 0
    for i, line in enumerate(lines):
        try:
            bb = font.getbbox(line)
        except Exception:
            bb = (0, 0, len(line) * 16, 20)
        total += bb[3] - bb[1]
        if i < len(lines) - 1:
            total += line_gap
    return total


def _draw_lines_centered(draw, lines: list, cx: int, cy: int, font,
                          color, line_gap: int = 12) -> int:
    """以 (cx, cy) 为中心绘制多行文本，返回末行底部 y。"""
    total_h = _text_block_h(lines, font, line_gap)
    y = cy - total_h // 2
    for i, line in enumerate(lines):
        try:
            bb = font.getbbox(line)
            lw, lh = bb[2] - bb[0], bb[3] - bb[1]
        except Exception:
            lw, lh = len(line) * 16, 20
        draw.text((cx - lw // 2, y), line, fill=color, font=font)
        y += lh + (line_gap if i < len(lines) - 1 else 0)
    return cy + total_h // 2


def _title_size(lines: list, avail_w: int, max_size: int = 92) -> int:
    max_len = max(len(l) for l in lines) if lines else 1
    size = int(avail_w * 0.8) // max_len
    return max(38, min(size, max_size))


# ── 5 种风格渲染 ──────────────────────────────────────────────────

def _render_minimal_light(title_lines: list, author: str, w: int, h: int) -> 'Image.Image':
    """留白·默认 — 暖米白，大标题，细横线，对标 BookCrafter 默认经典款"""
    img = Image.new('RGB', (w, h), (245, 240, 232))  # #f5f0e8
    draw = ImageDraw.Draw(img)

    # 单层细外框
    bm = 24
    draw.rectangle([bm, bm, w - bm, h - bm], outline=(200, 187, 168), width=1)

    ts = _title_size(title_lines, w - 100, max_size=94)
    tf = _load_font(ts)
    af = _load_font(max(28, ts // 2), 'light')

    # 标题：居中，约 38% 处
    title_cy = int(h * 0.38)
    bot = _draw_lines_centered(draw, title_lines, w // 2, title_cy, tf, '#1a1a1a')

    # 细横线（等宽于标题约 70% 位置）
    rule_y = bot + 22
    draw.line([(int(w * 0.30), rule_y), (int(w * 0.70), rule_y)],
              fill=(200, 187, 168), width=1)

    # 作者名：横线下方
    author_y = rule_y + 30
    draw.text((w // 2, author_y), author, fill='#777777', font=af, anchor='mm')

    return img


def _render_dark_elegance(title_lines: list, author: str, w: int, h: int) -> 'Image.Image':
    """装帧·典藏 — 深绿布面，居中奶白标签，对标 BookCrafter 文库·装帧"""
    img = Image.new('RGB', (w, h), (31, 51, 41))  # #1f3329 深绿
    draw = ImageDraw.Draw(img)

    # 深绿外框
    bm = 22
    draw.rectangle([bm, bm, w - bm, h - bm], outline=(45, 72, 55), width=1)

    # 居中白色标签
    lx1, ly1 = 72, int(h * 0.30)
    lx2, ly2 = w - 72, int(h * 0.70)
    draw.rectangle([lx1, ly1, lx2, ly2], fill=(248, 244, 236))   # 奶白 #f8f4ec
    draw.rectangle([lx1 + 8, ly1 + 8, lx2 - 8, ly2 - 8],
                   outline=(210, 200, 184), width=1)               # 标签内细框

    # 标签内容
    label_cx = w // 2
    label_cy = (ly1 + ly2) // 2
    avail = lx2 - lx1 - 60

    ts = _title_size(title_lines, avail, max_size=76)
    tf = _load_font(ts)
    af = _load_font(max(24, ts // 2 + 2), 'light')

    # 标题居中于标签（略偏上）
    title_cy = label_cy - 14
    bot = _draw_lines_centered(draw, title_lines, label_cx, title_cy, tf, '#1a1a1a')

    rule_y = bot + 18
    draw.line([(label_cx - 55, rule_y), (label_cx + 55, rule_y)],
              fill=(190, 178, 160), width=1)

    author_y = rule_y + 26
    draw.text((label_cx, author_y), author, fill='#555555', font=af, anchor='mm')

    return img


def _render_gradient_vivid(title_lines: list, author: str, w: int, h: int) -> 'Image.Image':
    """现代·编辑 — 黑色版头色块 + 白色书面 + 横纹纹理，对标 BookCrafter 现代·编辑"""
    img = Image.new('RGB', (w, h), (250, 250, 248))  # 近白
    draw = ImageDraw.Draw(img)

    ts = _title_size(title_lines, w - 80, max_size=76)
    tf = _load_font(ts)
    af = _load_font(max(26, ts // 2 + 4))

    # 计算黑色版头高度（标题高度 + 上下内边距各 38px）
    blk_text_h = _text_block_h(title_lines, tf, line_gap=14)
    blk_h = max(200, blk_text_h + 76)

    # 黑色版头块
    draw.rectangle([0, 0, w, blk_h], fill=(22, 22, 22))

    # 标题居中于版头
    _draw_lines_centered(draw, title_lines, w // 2, blk_h // 2,
                          tf, '#f5f0e8', line_gap=14)

    # 版头下方双横线（报纸风格）
    r1_y = blk_h + 16
    draw.line([(0, r1_y), (w, r1_y)], fill=(22, 22, 22), width=2)
    r2_y = r1_y + 10
    draw.line([(0, r2_y), (w, r2_y)], fill=(22, 22, 22), width=1)

    # 作者名
    author_y = r2_y + 46
    draw.text((w // 2, author_y), author, fill='#2a2a2a', font=af, anchor='mm')

    # 下方等距横纹：从作者下方一直延伸到底部双线之前
    line_start = author_y + 50
    line_gap = 30
    bot_r1 = h - 44
    i = 0
    while True:
        ly = line_start + i * line_gap
        if ly >= bot_r1 - 18:
            break
        draw.line([(36, ly), (w - 36, ly)], fill=(210, 210, 207), width=1)
        i += 1

    # 底部双横线（与顶部对称）
    draw.line([(0, bot_r1), (w, bot_r1)], fill=(22, 22, 22), width=2)
    draw.line([(0, bot_r1 + 10), (w, bot_r1 + 10)], fill=(22, 22, 22), width=1)

    return img


def _render_ink_classical(title_lines: list, author: str, w: int, h: int) -> 'Image.Image':
    """版框·古风 — 纸色底，双重版框，朱红印章，对标 BookCrafter 古风·纸墨"""
    img = Image.new('RGB', (w, h), (232, 212, 168))  # #e8d4a8 纸色
    draw = ImageDraw.Draw(img)

    # 外框（深棕）
    fo = 20
    draw.rectangle([fo, fo, w - fo, h - fo], outline=(92, 56, 32), width=1)
    # 内框（中棕）
    fi = 32
    draw.rectangle([fi, fi, w - fi, h - fi], outline=(139, 90, 52), width=1)

    ts = _title_size(title_lines, w - 90, max_size=86)
    tf = _load_font(ts, 'serif')
    af = _load_font(max(28, ts // 2), 'serif')

    # 标题
    title_cy = int(h * 0.40)
    bot = _draw_lines_centered(draw, title_lines, w // 2, title_cy, tf, '#2c1800')

    # 标题下方细横线
    rule_y = bot + 22
    draw.line([(int(w * 0.26), rule_y), (int(w * 0.74), rule_y)],
              fill=(139, 90, 52), width=1)

    # 作者名
    author_y = int(h * 0.58)
    draw.text((w // 2, author_y), author, fill='#8b4513', font=af, anchor='mm')

    # 朱红印章（内框左下角）
    sx, sy = fi + 22, int(h * 0.80)
    ss = 44
    draw.rectangle([sx, sy, sx + ss, sy + ss], fill=(192, 57, 43))
    draw.rectangle([sx + 5, sy + 5, sx + ss - 5, sy + ss - 5],
                   outline=(240, 210, 200), width=1)
    # 十字纹（简化印章内纹）
    draw.line([(sx + ss // 2, sy + 8), (sx + ss // 2, sy + ss - 8)],
              fill=(240, 210, 200), width=1)
    draw.line([(sx + 8, sy + ss // 2), (sx + ss - 8, sy + ss // 2)],
              fill=(240, 210, 200), width=1)

    return img


def _render_literary_warm(title_lines: list, author: str, w: int, h: int) -> 'Image.Image':
    """日常·治愈 — 暖米底，金色圆形，温柔留白，对标 BookCrafter 治愈·日常"""
    img = Image.new('RGB', (w, h), (242, 232, 207))  # #f2e8cf 暖米
    draw = ImageDraw.Draw(img)

    cx = w // 2

    # 大金色圆形（日光元素），中心约在 28% 高度
    circle_cy = int(h * 0.28)
    circle_r = 98
    draw.ellipse(
        [cx - circle_r, circle_cy - circle_r, cx + circle_r, circle_cy + circle_r],
        fill=(196, 154, 60)   # #c49a3c 金黄
    )

    ts = _title_size(title_lines, w - 80, max_size=86)
    tf = _load_font(ts)
    af = _load_font(max(26, ts // 2), 'light')

    # 标题位于圆下方，约 50% 处
    title_cy = int(h * 0.50)
    bot = _draw_lines_centered(draw, title_lines, cx, title_cy, tf, '#2c1800')

    # 细横线
    rule_y = bot + 20
    draw.line([(int(w * 0.32), rule_y), (int(w * 0.68), rule_y)],
              fill=(196, 154, 60), width=1)

    # 作者名，约 65% 处
    author_y = int(h * 0.65)
    draw.text((cx, author_y), author, fill='#7a5c2a', font=af, anchor='mm')

    # 小金圆底部锚点（约 84%）
    bot_cy = int(h * 0.84)
    bot_r = 22
    draw.ellipse([cx - bot_r, bot_cy - bot_r, cx + bot_r, bot_cy + bot_r],
                 outline=(196, 154, 60), width=2)

    return img


# ── 公开 API ──────────────────────────────────────────────────────

_RENDERERS = {
    'minimal_light':  _render_minimal_light,
    'dark_elegance':  _render_dark_elegance,
    'gradient_vivid': _render_gradient_vivid,
    'ink_classical':  _render_ink_classical,
    'literary_warm':  _render_literary_warm,
}


def list_styles() -> list:
    return [{"key": k, **v} for k, v in STYLE_PRESETS.items()]


def generate_cover(title: str, author: str, style: str = 'minimal_light',
                   thumb: bool = False) -> bytes:
    """生成封面，返回 JPEG bytes。thumb=True 生成 120×180 缩略图。"""
    if not _PIL_OK:
        raise RuntimeError('cover generation requires Pillow — pip install Pillow')

    renderer = _RENDERERS.get(style, _RENDERERS['minimal_light'])
    lines = _wrap_title(title.strip() if title else '书名', max_chars=8)
    auth = (author.strip() if author else '作者') or '作者'

    img = renderer(lines, auth, COVER_W, COVER_H)

    if thumb:
        img = img.resize((THUMB_W, THUMB_H), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=85 if thumb else 92, optimize=True)
    return buf.getvalue()
