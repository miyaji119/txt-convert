"""章节编号器

为文本中的章节标题添加连续阿拉伯编号，统一为「第N章 标题」格式。
独立模块，不依赖 clean_rules.py，可复用于任意小说。

支持的标题格式（默认规则）:
    第一章 / 第十二章 / 第3章        → 第N章（替换原编号）
    终章 / 序章 / 楔子 / 尾声 / 后记  → 第N章 终章
    番外 / 番外一 / 番外三 标题       → 第N章 番外...
    外篇：标题 / 外篇 标题            → 第N章 外篇...
    Chapter 1 / Chapter 2            → 第N章

用法:
    # 1. 作为模块导入
    from chapter_numberer import add_chapter_numbers
    lines = text.splitlines()
    numbered = add_chapter_numbers(lines)

    # 2. 直接处理文件
    from chapter_numberer import number_chapters_in_file
    number_chapters_in_file('novel.txt', 'output.txt')

    # 3. 命令行
    $ python3 chapter_numberer.py novel.txt -o output.txt
"""

import re
import argparse
from pathlib import Path
from typing import List, Optional, Set, Pattern


# ==================== 默认识别规则 ====================

# 章节标题正则模式（匹配整行即视为标题）
# 注意：第X章后必须单独成行或跟空格分隔的标题，避免误匹配"第三章可引用。"等正文
DEFAULT_TITLE_PATTERNS: List[Pattern] = [
    re.compile(r'^第[零一二三四五六七八九十百千万\d]+章\s*$'),        # 第X章（单独成行）
    re.compile(r'^第[零一二三四五六七八九十百千万\d]+章\s+\S'),       # 第X章 标题（章后有空格）
    re.compile(r'^[Cc]hapter\s*\d+', re.IGNORECASE),               # Chapter 1
    re.compile(r'^卷[零一二三四五六七八九十百千万\d]+\s*$'),           # 卷一（单独成行）
    re.compile(r'^卷[零一二三四五六七八九十百千万\d]+\s+\S'),          # 卷一 标题
]

# 标题前缀（行首匹配）
DEFAULT_TITLE_PREFIXES = ('番外', '外篇', '楔子', '序章', '终章', '尾声', '后记', '引子')

# 特殊标题（精确匹配）
DEFAULT_SPECIAL_TITLES: Set[str] = {'终章', '楔子', '序章', '尾声', '后记', '引子', '正文', '完结'}

# 需要去掉的原有前缀模式（编号时清除旧的「第X章」前缀）
OLD_PREFIX_RE = re.compile(
    r'^('
    r'第[零一二三四五六七八九十百千万\d]+章'   # 第X章
    r'|[Cc]hapter\s*\d+'                       # Chapter N
    r'|卷[零一二三四五六七八九十百千万\d]+'     # 卷X
    r')\s*'
)

_NUMBERED_CHAPTER_RE = re.compile(r'^第\d+章')


def is_chapter_title(line: str,
                     patterns: List[Pattern] = None,
                     prefixes: tuple = None,
                     specials: Set[str] = None) -> bool:
    """判断一行是否为章节标题"""
    patterns = patterns or DEFAULT_TITLE_PATTERNS
    prefixes = prefixes or DEFAULT_TITLE_PREFIXES
    specials = specials or DEFAULT_SPECIAL_TITLES

    s = line.strip()
    if not s:
        return False
    if any(p.match(s) for p in patterns):
        return True
    if s in specials:
        return True
    if any(s.startswith(prefix) for prefix in prefixes):
        return True
    return False


def add_chapter_numbers(lines: List[str],
                        patterns: List[Pattern] = None,
                        prefixes: tuple = None,
                        specials: Set[str] = None,
                        start: int = 1) -> List[str]:
    """为章节标题添加连续阿拉伯编号，统一为「第N章 标题」格式

    Args:
        lines: 文本行列表
        patterns: 自定义标题正则模式列表（默认 DEFAULT_TITLE_PATTERNS）
        prefixes: 自定义标题前缀元组（默认 DEFAULT_TITLE_PREFIXES）
        specials: 自定义特殊标题集合（默认 DEFAULT_SPECIAL_TITLES）
        start: 起始编号（默认 1）

    Returns:
        编号后的行列表
    """
    counter = start - 1
    result = []
    for line in lines:
        s = line.strip()
        if not s:
            result.append(line)
            continue

        if not is_chapter_title(s, patterns, prefixes, specials):
            result.append(line)
            continue

        counter += 1
        # 去掉原有前缀，保留标题部分
        title_part = OLD_PREFIX_RE.sub('', s).strip()
        if title_part:
            result.append(f'第{counter}章 {title_part}')
        else:
            result.append(f'第{counter}章')

    return result


def number_chapters_in_file(input_path: str,
                            output_path: str = None,
                            encoding: str = 'utf-8-sig',
                            **kwargs) -> str:
    """处理文件中的章节编号

    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径（默认在原文件名后加 _编号）
        encoding: 文件编码
        **kwargs: 传递给 add_chapter_numbers 的额外参数

    Returns:
        输出文件路径
    """
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.with_name(input_path.stem + '_编号' + input_path.suffix)
    else:
        output_path = Path(output_path)

    with open(input_path, 'r', encoding=encoding) as f:
        lines = f.read().splitlines()

    numbered = add_chapter_numbers(lines, **kwargs)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(numbered) + '\n')

    return str(output_path)


# ==================== CLI ====================

def main():
    parser = argparse.ArgumentParser(
        description='为TXT文件中的章节标题添加连续编号',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 chapter_numberer.py novel.txt
  python3 chapter_numberer.py novel.txt -o output.txt
  python3 chapter_numberer.py novel.txt --start 0
        """)
    parser.add_argument('input', help='输入TXT文件路径')
    parser.add_argument('-o', '--output', help='输出文件路径')
    parser.add_argument('--start', type=int, default=1, help='起始编号 (默认: 1)')
    parser.add_argument('--preview', action='store_true', help='仅预览编号结果，不写文件')
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f'❌ 文件不存在: {input_path}')
        return

    # 尝试自动检测编码
    try:
        from encoding import EncodingDetector
        text, enc = EncodingDetector.read_file_with_auto_encoding(str(input_path))
    except ImportError:
        enc = 'utf-8-sig'
        with open(input_path, 'r', encoding=enc) as f:
            text = f.read()

    lines = text.splitlines()
    numbered = add_chapter_numbers(lines, start=args.start)

    # 统计
    count = sum(1 for l in numbered if _NUMBERED_CHAPTER_RE.match(l.strip()))

    if args.preview:
        print(f'📖 {input_path.name} (编码: {enc})')
        print(f'📚 检测到 {count} 个章节标题:\n')
        for line in numbered:
            s = line.strip()
            if _NUMBERED_CHAPTER_RE.match(s):
                print(f'  {s}')
        return

    output_path = args.output or str(
        input_path.with_name(input_path.stem + '_编号' + input_path.suffix)
    )
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(numbered) + '\n')

    print(f'✅ 完成！共编号 {count} 个章节')
    print(f'   输出: {output_path}')


if __name__ == '__main__':
    main()
