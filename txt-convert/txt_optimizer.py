#!/usr/bin/env python3
"""TXT 小说文本格式优化工具

统一处理各种小说文本的格式问题：
- 去重（自动检测 HTML 注释 / EasyPub 元数据标记）
- 广告/水印/元数据过滤
- 章节标题规范化（纯数字→第N章、番外编号统一等）
- 内容分离（标题与正文粘连、引用与正文粘连、警告内容分离等）
- 章节连续编号

规则配置见 clean_rules.py，章节编号由 chapter_numberer.py 处理。

用法:
    python3 txt_optimizer.py 'novel.txt'
    python3 txt_optimizer.py 'novel.txt' -o 'output.txt'
    python3 txt_optimizer.py --rules
"""
from __future__ import annotations

import re
import argparse
from collections import deque
from pathlib import Path

from encoding import EncodingDetector
from clean_rules import (
    SKIP_PATTERNS, SKIP_PATTERNS_COMPILED,
    FANWAI_PREFIX_COMMA, DIRECT_FANWAI, CHAPTER_TITLE,
    FANWAI_NUM_SUFFIX, WAIPIAN_NUM,
    SPECIAL_TITLES, SPECIAL_TITLE_PREFIX,
    WARNING_LINE, SEPARATOR, SEPARATOR_ONLY, LEADING_COMMA,
    QUOTE_PREFIX, QUOTE_SEPARATOR, BODY_START_KEYWORDS, MAX_AUTHOR_LENGTH,
    LONE_PUNCTUATION, MAX_BLANK_LINES, NUM_MAP,
    DEDUP_MARKERS, METADATA_PREFIXES, END_MARKERS,
    PURE_NUMBER, NUMBER_TEXT, LABEL_PATTERN,
    GUOSHI_NUM, GUOSHI_TEXT, ZHIMA_LABEL,
)
from chapter_numberer import add_chapter_numbers

# 模块级预编译，避免循环内重复编译
_CHAPTER_DISPLAY_RE = re.compile(r'^第\d+章')
_DEDUP_MARKERS_TUPLE = tuple(DEDUP_MARKERS)


# ==================== 辅助函数 ====================

def normalize_title(title: str) -> str:
    """规范化番外/外篇标题：数字后缀转中文"""
    # 番外三数字后缀：番外三 xxx1 → 番外三 xxx（一）
    fw3_match = FANWAI_NUM_SUFFIX.match(title)
    if fw3_match:
        title_part = fw3_match.group(1).strip()
        cn_num = NUM_MAP.get(fw3_match.group(2), fw3_match.group(2))
        title = f"{title_part}（{cn_num}）"

    # 外篇数字编号转中文：外篇：xxx（3）→ 外篇：xxx（三）
    wp_match = WAIPIAN_NUM.match(title)
    if wp_match:
        prefix = wp_match.group(1)
        cn_num = NUM_MAP.get(wp_match.group(2), wp_match.group(2))
        title = f"{prefix}（{cn_num}）"

    return title


def process_fanwai_special(title: str) -> list | None:
    """处理番外国师/芝麻糊等特殊情况

    返回输出行列表（不含外围空行），或 None 表示非特殊情况。
    """
    # 国师 num: 番外 国师 2 → 番外 国师（二）
    guoshi_num = GUOSHI_NUM.match(title)
    if guoshi_num:
        cn = NUM_MAP.get(guoshi_num.group(1), guoshi_num.group(1))
        return [f'番外 国师（{cn}）']

    # 国师 text: 番外 国师 放眼望去... → 番外 国师（一） + body
    guoshi_text = GUOSHI_TEXT.match(title)
    if guoshi_text:
        body = guoshi_text.group(1).strip()
        return ['番外 国师（一）', '', body]

    # 芝麻糊 label: 番外 芝麻糊 （人外...） → 番外 芝麻糊
    zhima = ZHIMA_LABEL.match(title)
    if zhima:
        return [zhima.group(1)]

    return None


def split_quote_and_body(stripped: str) -> list:
    """分离引用(——《书名》／作者)与粘连正文"""
    # 先尝试找第二个引用 ——《
    next_quote_pos = stripped.find(QUOTE_PREFIX, 2)
    if next_quote_pos > 0:
        first_quote = stripped[:next_quote_pos].strip()
        second_part = stripped[next_quote_pos:].strip()

        second_book_end = second_part.find(QUOTE_SEPARATOR)
        author_end = -1
        if second_book_end > 0:
            for i in range(second_book_end + 2, len(second_part)):
                if second_part[i] in BODY_START_KEYWORDS:
                    author_end = i
                    break
            if author_end < 0 and len(second_part) - 3 > second_book_end + MAX_AUTHOR_LENGTH:
                author_end = second_book_end + 30

        result = [first_quote]
        if author_end > 0:
            second_q = second_part[:author_end].strip()
            body_text = second_part[author_end:].strip()
            result.append(second_q)
            if body_text:
                result.append('')
                result.append(body_text)
        else:
            result.append(second_part)
        return result

    # 只有一个引用，检查后面是否跟了正文
    book_end = stripped.find(QUOTE_SEPARATOR)
    if book_end > 0:
        author_start = book_end + 2
        body_start = -1
        for i in range(author_start, len(stripped)):
            ch = stripped[i]
            if ch in BODY_START_KEYWORDS:
                before = stripped[author_start:i]
                if '）' in before and before.rfind('）') < i - author_start - 1:
                    body_start = i
                    break
            if i - author_start > MAX_AUTHOR_LENGTH and body_start < 0:
                body_start = i
                break

        if body_start > 0:
            quote_part = stripped[:body_start].strip()
            body_part = stripped[body_start:].strip()
            result = [quote_part]
            if body_part:
                result.append('')
                result.append(body_part)
            return result

    return [stripped]


# ==================== 核心清理函数 ====================

def dedup_lines(lines: list) -> list:
    """去重：检测到 HTML 注释 / EasyPub 元数据标记时截断后续内容"""
    for i, line in enumerate(lines):
        if any(marker in line for marker in _DEDUP_MARKERS_TUPLE):
            return lines[:i]
    return lines


def clean_novel_content(text: str) -> str:
    """清理小说文本中的广告和格式问题"""
    lines = text.split('\n')

    # 第一步：去重
    lines = dedup_lines(lines)

    # 第二步：逐行处理
    cleaned_lines = []
    pending_warning_text = None

    def flush_pending():
        """将暂存的警告内容输出到 cleaned_lines"""
        nonlocal pending_warning_text
        if pending_warning_text:
            cleaned_lines.append(pending_warning_text)
            cleaned_lines.append('')
            pending_warning_text = None

    for line in lines:
        stripped = line.strip()

        # 空行保留
        if not stripped:
            flush_pending()
            cleaned_lines.append('')
            continue

        # 单独的标点行直接跳过
        if stripped in LONE_PUNCTUATION:
            continue

        # 广告行过滤
        if any(p.search(stripped) for p in SKIP_PATTERNS_COMPILED):
            continue

        # 元数据 / END 标记行跳过
        if stripped.startswith(tuple(METADATA_PREFIXES)):
            continue
        if stripped in END_MARKERS:
            continue

        # 去掉行首多余逗号（非标题行）
        is_potential_title = (
            FANWAI_PREFIX_COMMA.match(stripped)
            or DIRECT_FANWAI.match(stripped)
            or CHAPTER_TITLE.match(stripped)
            or stripped in SPECIAL_TITLES
            or SPECIAL_TITLE_PREFIX.match(stripped)
            or stripped.startswith('番外')
            or stripped.startswith('外篇')
        )
        if not is_potential_title and LEADING_COMMA.match(stripped):
            stripped = re.sub(r'^[，,]\s*', '', stripped)

        # --- 数字章节转换 ---

        # 标签行（1 一发完结）→ 原样保留
        if LABEL_PATTERN.match(stripped):
            flush_pending()
            cleaned_lines.extend(['', stripped, ''])
            continue

        # 纯数字行 → 第N章
        if PURE_NUMBER.match(stripped):
            flush_pending()
            cleaned_lines.extend(['', f'第{stripped}章', ''])
            continue

        # 数字+空格+正文 → 分离为 第N章 + 正文
        num_text_match = NUMBER_TEXT.match(stripped)
        if num_text_match and not LABEL_PATTERN.match(stripped):
            flush_pending()
            num = num_text_match.group(1)
            body = num_text_match.group(2).strip()
            cleaned_lines.extend(['', f'第{num}章', '', body])
            continue

        # --- 标题处理 ---

        # 番外/外篇标题（带逗号前缀）
        fanwai_match = FANWAI_PREFIX_COMMA.match(stripped)
        if fanwai_match:
            title = fanwai_match.group(1).strip()
            special = process_fanwai_special(title)
            flush_pending()
            if special:
                # 含正文的结果（多元素）不加尾部空行
                tail = [''] if len(special) == 1 else []
                cleaned_lines.extend([''] + special + tail)
            else:
                cleaned_lines.extend(['', normalize_title(title), ''])
            continue

        # 外篇标题（无逗号前缀）
        direct_match = DIRECT_FANWAI.match(stripped)
        if direct_match:
            title = direct_match.group(1).strip()
            special = process_fanwai_special(title)
            flush_pending()
            if special:
                tail = [''] if len(special) == 1 else []
                cleaned_lines.extend([''] + special + tail)
            else:
                cleaned_lines.extend(['', normalize_title(title), ''])
            continue

        # 番外标题（无逗号前缀，以"番外"开头）
        if stripped.startswith('番外'):
            special = process_fanwai_special(stripped)
            flush_pending()
            if special:
                tail = [''] if len(special) == 1 else []
                cleaned_lines.extend([''] + special + tail)
            else:
                cleaned_lines.extend(['', normalize_title(stripped), ''])
            continue

        # 章节标题（第X章）
        if CHAPTER_TITLE.match(stripped):
            flush_pending()
            cleaned_lines.extend(['', stripped, ''])
            continue

        # 特殊章节标题（终章、楔子等）
        if stripped in SPECIAL_TITLES:
            flush_pending()
            cleaned_lines.extend(['', stripped, ''])
            continue

        # 特殊标题前缀修正（，番外停更通知 → 番外停更通知）
        special_prefix_match = SPECIAL_TITLE_PREFIX.match(stripped)
        if special_prefix_match:
            flush_pending()
            cleaned_lines.extend(['', special_prefix_match.group(1), ''])
            continue

        # --- 内容分离 ---

        # 警告内容行（可能和正文粘连）
        if WARNING_LINE.match(line):
            warning_content = stripped
            sep_match = SEPARATOR.search(warning_content)
            if sep_match:
                warn_part = warning_content[:sep_match.start()].strip()
                after_sep = warning_content[sep_match.end():].strip()
                pending_warning_text = warn_part
                if after_sep:
                    flush_pending()
                    cleaned_lines.append(after_sep)
            else:
                pending_warning_text = warning_content
            continue

        # 带分隔符粘连的普通正文（如：----正文内容）
        sep_in_line = SEPARATOR.search(stripped)
        if sep_in_line and not WARNING_LINE.match(line):
            after_sep = stripped[sep_in_line.end():].strip()
            before_sep = stripped[:sep_in_line.start()].strip()
            flush_pending()
            if before_sep:
                cleaned_lines.append(before_sep)
            if after_sep:
                cleaned_lines.append(after_sep)
            continue

        # 纯分隔符行
        if SEPARATOR_ONLY.match(stripped):
            continue

        # 引用与正文粘连（——《书名》／作者 正文）
        if stripped.startswith(QUOTE_PREFIX):
            parts = split_quote_and_body(stripped)
            flush_pending()
            cleaned_lines.extend(parts)
            continue

        # --- 普通正文行 ---

        flush_pending()
        cleaned_lines.append(stripped)

    # 处理剩余的 pending 内容
    if pending_warning_text:
        cleaned_lines.append(pending_warning_text)

    # 合并过多空行
    result_lines = []
    empty_count = 0
    for line in cleaned_lines:
        if not line:
            empty_count += 1
            if empty_count <= MAX_BLANK_LINES:
                result_lines.append(line)
        else:
            empty_count = 0
            result_lines.append(line)

    # 移除首尾空行
    dq = deque(result_lines)
    while dq and not dq[0]:
        dq.popleft()
    while dq and not dq[-1]:
        dq.pop()
    result_lines = list(dq)

    # 为章节标题添加连续编号
    result_lines = add_chapter_numbers(result_lines)

    return '\n'.join(result_lines) + '\n'


# ==================== 规则展示 ====================

def print_rules():
    """打印当前规则配置"""
    print("=" * 60)
    print("文本清理规则配置 (clean_rules.py)")
    print("=" * 60)

    print("\n【1. 去重】检测到以下标记时截断后续内容:")
    print(f"  {DEDUP_MARKERS}")

    print("\n【2. 广告/垃圾行过滤】匹配即删除:")
    for i, p in enumerate(SKIP_PATTERNS, 1):
        print(f"  {i}. {p}")

    print("\n【3. 元数据/标记行过滤】")
    print(f"  前缀匹配: {METADATA_PREFIXES}")
    print(f"  精确匹配: {END_MARKERS}")

    print("\n【4. 数字章节转换】")
    print(f"  纯数字:   {PURE_NUMBER.pattern}")
    print(f"  数字+正文: {NUMBER_TEXT.pattern}")
    print(f"  标签行:   {LABEL_PATTERN.pattern}")

    print("\n【5. 标题修正】")
    print(f"  番外前缀逗号: {FANWAI_PREFIX_COMMA.pattern}")
    print(f"  外篇直接匹配: {DIRECT_FANWAI.pattern}")
    print(f"  章节标题:     {CHAPTER_TITLE.pattern}")
    print(f"  番外数字后缀: {FANWAI_NUM_SUFFIX.pattern}")
    print(f"  外篇数字编号: {WAIPIAN_NUM.pattern}")
    print(f"  特殊标题:     {SPECIAL_TITLES}")
    print(f"  特殊标题前缀: {SPECIAL_TITLE_PREFIX.pattern}")

    print("\n【6. 番外国师/芝麻糊】")
    print(f"  国师编号: {GUOSHI_NUM.pattern}")
    print(f"  国师正文: {GUOSHI_TEXT.pattern}")
    print(f"  芝麻糊标签: {ZHIMA_LABEL.pattern}")

    print("\n【7. 内容分离】")
    print(f"  警告行:       {WARNING_LINE.pattern}")
    print(f"  分隔符:       {SEPARATOR.pattern}")
    print(f"  纯分隔符行:   {SEPARATOR_ONLY.pattern}")
    print(f"  行首逗号:     {LEADING_COMMA.pattern}")

    print("\n【8. 引用分离】")
    print(f"  引用前缀:     {QUOTE_PREFIX}")
    print(f"  引用分隔标记: {QUOTE_SEPARATOR}")
    print(f"  正文关键词:   {BODY_START_KEYWORDS}")
    print(f"  作者名最大长度: {MAX_AUTHOR_LENGTH}")

    print("\n【9. 行清理】")
    print(f"  单独标点删除: {LONE_PUNCTUATION}")
    print(f"  最大连续空行: {MAX_BLANK_LINES}")

    print("\n【10. 数字映射】")
    print(f"  {NUM_MAP}")
    print()


# ==================== CLI ====================

def main():
    parser = argparse.ArgumentParser(
        description='TXT 小说文本格式优化工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 txt_optimizer.py 'novel.txt'
  python3 txt_optimizer.py 'novel.txt' -o 'optimized.txt'
  python3 txt_optimizer.py --rules
        """)
    parser.add_argument('input', nargs='?', help='输入文件路径')
    parser.add_argument('-o', '--output', help='输出文件路径')
    parser.add_argument('--rules', action='store_true', help='查看当前规则配置')
    args = parser.parse_args()

    if args.rules:
        print_rules()
        return

    if not args.input:
        parser.print_help()
        return

    input_path = Path(args.input)
    if not input_path.exists():
        print(f'❌ 文件不存在: {input_path}')
        return

    output_path = Path(args.output) if args.output else input_path.with_name(
        input_path.stem + '_优化版' + input_path.suffix
    )

    print(f"📖 读取文件: {input_path}")
    content, encoding = EncodingDetector.read_file_with_auto_encoding(str(input_path))
    print(f"   检测编码: {encoding}")
    print(f"   原始行数: {len(content.splitlines())}")

    print("\n🔧 开始优化文本格式...")
    optimized = clean_novel_content(content)
    print(f"   优化后行数: {len(optimized.splitlines())}")

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(optimized)
    print(f"\n✅ 优化完成！输出: {output_path}")

    # 章节检测
    print("\n📚 章节目录:")
    for line in optimized.splitlines():
        s = line.strip()
        if _CHAPTER_DISPLAY_RE.match(s):
            print(f"   {s}")


if __name__ == '__main__':
    main()
