"""字体子集化模块

使用 fontTools Python API 对 TTF/OTF 字体按全书字符集裁剪，
大幅缩减内嵌字体体积（通常从 10MB+ 降到几百 KB）。

字体角色（roles）：body / title / dlg / toc
"""

import os
import tempfile
from typing import Optional

try:
    from fontTools import subset as _ft_subset
    from fontTools.ttLib import TTFont
    FONTTOOLS_AVAILABLE = True
except ImportError:
    FONTTOOLS_AVAILABLE = False

# role → CSS font-family 名称
ROLE_FAMILY = {
    "body":  "EmbeddedBody",
    "title": "EmbeddedTitle",
    "dlg":   "EmbeddedDlg",
    "toc":   "EmbeddedToc",
}

# role → CSS font-weight / font-style
ROLE_CSS = {
    "body":  "normal",
    "title": "bold",
    "dlg":   "normal",
    "toc":   "normal",
}


def subset_font(src_path: str, chars: str, out_path: str) -> bool:
    """对字体按字符集子集化，输出到 out_path。

    Args:
        src_path: 原始字体文件路径（TTF/OTF）
        chars:    需要保留的字符字符串（去重后传入效率更高）
        out_path: 输出文件路径

    Returns:
        True 表示成功，False 表示失败（fontTools 不可用或字体读取出错）
    """
    if not FONTTOOLS_AVAILABLE:
        return False
    if not os.path.isfile(src_path):
        return False
    try:
        opts = _ft_subset.Options()
        opts.layout_features = ["*"]
        opts.name_IDs = ["*"]
        opts.ignore_missing_glyphs = True
        font = _ft_subset.load_font(src_path, opts)
        subsetter = _ft_subset.Subsetter(options=opts)
        subsetter.populate(text=chars)
        subsetter.subset(font)
        _ft_subset.save_font(font, out_path, opts)
        return True
    except Exception as e:
        print(f"   ⚠️ 字体子集化失败 {os.path.basename(src_path)}: {e}")
        return False


def collect_chars(chapters: list) -> str:
    """从章节列表中收集全书所有字符（去重，用于子集化）。

    Args:
        chapters: [{"title": str, "content": str}, ...]

    Returns:
        去重后的字符串
    """
    chars: set = set()
    for ch in chapters:
        chars.update(ch.get("title", ""))
        chars.update(ch.get("content", ""))
    return "".join(chars)


def build_font_face_css(role: str, font_filename: str) -> str:
    """生成 @font-face CSS 规则。"""
    family = ROLE_FAMILY.get(role, f"Embedded_{role}")
    weight = ROLE_CSS.get(role, "normal")
    ext = os.path.splitext(font_filename)[1].lower()
    fmt = "opentype" if ext in (".otf", ".cff") else "truetype"
    return (
        f'@font-face{{font-family:"{family}";'
        f'src:url("../fonts/{font_filename}") format("{fmt}");'
        f'font-weight:{weight};font-style:normal}}'
    )


def process_fonts(
    fonts: dict,
    chapters: list,
    tmp_dir: str,
) -> list:
    """子集化所有角色字体，返回 EPUB item 数据列表。

    Args:
        fonts:     {role: font_path}，如 {"body": "/path/body.ttf"}
        chapters:  章节列表（用于收集字符集）
        tmp_dir:   输出子集字体的临时目录

    Returns:
        [{"role": str, "filename": str, "bytes": bytes, "css": str}]
    """
    if not fonts:
        return []
    chars = collect_chars(chapters)
    results = []
    for role, src_path in fonts.items():
        if not src_path or not os.path.isfile(src_path):
            continue
        ext = os.path.splitext(src_path)[1].lower() or ".ttf"
        out_name = f"font_{role}{ext}"
        out_path = os.path.join(tmp_dir, out_name)
        ok = subset_font(src_path, chars, out_path)
        if not ok:
            continue
        with open(out_path, "rb") as f:
            font_bytes = f.read()
        results.append({
            "role":     role,
            "filename": out_name,
            "bytes":    font_bytes,
            "css":      build_font_face_css(role, out_name),
        })
        size_before = os.path.getsize(src_path)
        size_after  = len(font_bytes)
        print(f"   🔠 字体子集化: {role} {os.path.basename(src_path)}"
              f" {size_before // 1024}KB → {size_after // 1024}KB")
    return results
