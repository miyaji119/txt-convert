"""EasyPub优化模块"""

import os
import re
import json
from typing import Optional, Dict, List, Tuple

from encoding import EncodingDetector
from chapter import ChapterAnalyzer


def _arabic_to_chinese(n: int) -> str:
    """阿拉伯数字 → 中文章节序数（支持 1–9999）。如 12 → '十二'，42 → '四十二'。"""
    if n <= 0:
        return str(n)
    digits = '零一二三四五六七八九'
    units  = ['', '十', '百', '千']
    s = str(n)
    length = len(s)
    result = ''
    prev_zero = False
    for i, ch in enumerate(s):
        d = int(ch)
        pos = length - 1 - i
        if d == 0:
            prev_zero = True
        else:
            if prev_zero and result:
                result += '零'
            result += digits[d] + (units[pos] if pos < len(units) else '')
            prev_zero = False
    if result.startswith('一十'):  # 十一 而非 一十一
        result = result[1:]
    return result


_NUM_FIRST_RE   = re.compile(r'^(\d{1,4})[、，,\.\s]+(.*)$')
_STANDARD_CH_RE = re.compile(r'^第[零一二三四五六七八九十百千万两\d]+[章节回卷]')


def normalize_numeric_chapters(content: str) -> Tuple[str, List[dict]]:
    """将纯数字格式的章节标题转为「第X章」格式。

    仅处理已被 ChapterAnalyzer 识别为章节标题、且尚未是「第X章」格式的行。
    返回 (修改后的文本, 变更列表)，变更列表每项为 {line_num, original, normalized}。
    """
    structure = ChapterAnalyzer.analyze_chapter_structure(content)
    lines = content.split('\n')
    ch_map = {ch['start_line']: ch for ch in structure.get('chapters', [])}
    changes: List[dict] = []

    for i, line in enumerate(lines):
        line_num = i + 1
        if line_num not in ch_map:
            continue
        stripped = line.strip()
        if _STANDARD_CH_RE.match(stripped):
            continue  # 已是标准格式，跳过
        m = _NUM_FIRST_RE.match(stripped)
        if not m:
            continue
        ch = ch_map[line_num]
        num = ch.get('number') or int(m.group(1))
        title_text = (ch.get('title') or m.group(2)).strip()
        normalized = '第{}章'.format(_arabic_to_chinese(num))
        if title_text:
            normalized += ' ' + title_text
        if normalized != stripped:
            changes.append({'line_num': line_num, 'original': stripped, 'normalized': normalized})
            lines[i] = normalized

    return '\n'.join(lines), changes
from display import DirectoryDisplay
from chapter import ChapterAnalyzer
from adfilter import AdFilter
from namecleaner import NameCleaner
from consistency import ConsistencyChecker, ContentMismatchError


class EasyPubOptimizer:
    """EasyPub专用优化器"""

    EASYPUB_CHAPTER_PATTERNS = [
        (r'^.*第([零一二三四五六七八九十百千万两\d]+)[章节回][：:，,]?\s*(.*)$', r'第\1章 \2'),
        (r'^.*[Cc]hapter\s*([\d零一二三四五六七八九十百千万两]+)[：:，,]?\s*(.*)$', r'第\1章 \2'),
        (r'^.*第([零一二三四五六七八九十百千万两\d]+)卷[：:，,]?\s*(.*)$', r'第\1卷 \2'),
        (r'^\d+\s*[·•・]\s*第\s*(\d+)\s*章\s*(.*)$', r'第\1章 \2'),
        (r'^(\d+)\s*[·•・]\s*(.+)$', r'第\1章 \2'),
        (r'^(\d+)[\.、]\s*(.*)$', r'第\1章 \2'),
        (r'^【(\d+)】\s*(.*)$', r'第\1章 \2'),
        (r'^（(\d+)）\s*(.*)$', r'第\1章 \2'),
    ]

    CHINESE_NUM_MAP = {
        '零': 0, '〇': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
        '十': 10, '百': 100, '千': 1000, '万': 10000, '两': 2, '壹': 1, '贰': 2, '叁': 3, '肆': 4,
        '伍': 5, '陆': 6, '柒': 7, '捌': 8, '玖': 9, '拾': 10, '佰': 100, '仟': 1000
    }

    @staticmethod
    def chinese_to_arabic(chinese_num: str) -> Optional[int]:
        if chinese_num.isdigit():
            return int(chinese_num)
        try:
            result = 0
            temp = 0
            for char in chinese_num:
                if char in EasyPubOptimizer.CHINESE_NUM_MAP:
                    value = EasyPubOptimizer.CHINESE_NUM_MAP[char]
                    if value < 10:
                        temp = value
                    elif value >= 10:
                        if temp == 0:
                            temp = 1
                        result += temp * value
                        temp = 0
            return result + temp
        except:
            return None

    @staticmethod
    def optimize_for_epub(text: str, book_title: str = "", author: str = "", chapter_info: Dict = None) -> Tuple[str, Dict]:
        """优化文本为EasyPub格式
        
        Args:
            text: 原始文本内容
            book_title: 书名
            author: 作者
            chapter_info: 章节信息（来自ChapterAnalyzer），用于过滤误识别的章节
        
        Returns:
            (优化后的文本, 分析结果)
        """
        lines = text.split('\n')
        optimized_lines = []
        chapters = []
        current_chapter = 0
        in_paragraph = False
        
        # 获取有效的章节信息（用于过滤误识别的章节）
        valid_chapters_map = {}
        if chapter_info and 'chapters' in chapter_info:
            for ch in chapter_info['chapters']:
                if ch['number'] not in valid_chapters_map:
                    valid_chapters_map[ch['number']] = ch
            print(f"   ⚠️ 使用ChapterAnalyzer章节信息过滤，有效章节: {len(valid_chapters_map)}个")

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                if in_paragraph and optimized_lines and optimized_lines[-1] != '':
                    optimized_lines.append('')
                in_paragraph = False
                continue

            is_chapter = False
            for pattern, replacement in EasyPubOptimizer.EASYPUB_CHAPTER_PATTERNS:
                match = re.match(pattern, line)
                if match:
                    chapter_num = match.group(1)
                    chapter_num_int = int(chapter_num) if chapter_num.isdigit() else (EasyPubOptimizer.chinese_to_arabic(chapter_num) or current_chapter + 1)
                    chapter_title = match.group(2).strip() if len(match.groups()) > 1 else ""
                    
                    # 如果有章节信息，检查这个章节号和标题是否匹配
                    if valid_chapters_map:
                        if chapter_num_int not in valid_chapters_map:
                            # 章节号不在有效列表中，跳过
                            continue
                        
                        valid_ch = valid_chapters_map[chapter_num_int]
                        valid_title = valid_ch.get('title', '')
                        if chapter_title and valid_title:
                            if chapter_title not in valid_title and valid_title not in chapter_title:
                                # 标题不匹配，跳过
                                continue
                    
                    # 所有检查通过，标记为章节
                    is_chapter = True
                    current_chapter += 1
                    standard_line = f"第{chapter_num_int}章 {chapter_title}" if chapter_title else f"第{chapter_num_int}章"
                    chapters.append({
                        'original_line': i + 1, 'number': chapter_num_int,
                        'title': chapter_title, 'standard_line': standard_line
                    })
                    optimized_lines.extend(['', standard_line, ''])
                    in_paragraph = False
                    # 跳过正文中紧跟章节标题完全相同的第一行
                    _next = i + 1
                    while _next < len(lines) and not lines[_next].strip():
                        _next += 1
                    if _next < len(lines) and lines[_next].strip() in (standard_line, chapter_title):
                        lines[_next] = ''
                    break

            if not is_chapter:
                if re.match(r'^[\*＊·•\s]+$', line) and len(line.strip()) <= 5:
                    if optimized_lines and optimized_lines[-1] != '':
                        optimized_lines.append('')
                    optimized_lines.append(line)
                    in_paragraph = False
                elif not in_paragraph:
                    optimized_lines.append(line)
                    in_paragraph = True
                else:
                    if line.startswith(('「', '『', '“', '”')) or optimized_lines[-1].endswith(('。', '！', '？', '」', '』', '”')):
                        optimized_lines.extend(['', line])
                    elif optimized_lines[-1]:
                        optimized_lines[-1] += ' ' + line

        optimized_text = '\n'.join(optimized_lines)
        optimized_text = re.sub(r'\n{3,}', '\n\n', optimized_text)
        
        # 如果有章节信息，使用准确的章节数
        total_chapters = len(valid_chapters_map) if valid_chapters_map else len(chapters)
        
        return optimized_text, {'total_chapters': total_chapters, 'chapters': chapters, 'total_lines': len(optimized_lines), 'total_chars': len(optimized_text)}


def _normalize_punctuation(text: str) -> str:
    """标点规范化：直引号→弯引号、...→……、~→～、不间断空格→普通空格"""
    # \xa0 和全角空格 → 普通空格
    text = text.replace('\xa0', ' ').replace('　', ' ')

    # 三个及以上连续英文点 → 省略号（先处理长串再处理三点）
    text = re.sub(r'\.{3,}', '……', text)

    # 半角波浪号 → 全角（只转孤立的 ~，不动 ~~~ 装饰行，那由 adfilter 处理）
    text = re.sub(r'(?<![~])~(?![~])', '～', text)

    # 英文直双引号 → 中文弯引号（按奇偶切换）
    def _replace_double(m):
        _replace_double.count += 1
        return '“' if _replace_double.count % 2 == 1 else '”'
    _replace_double.count = 0
    text = re.sub(r'"', _replace_double, text)

    # 英文直单引号 → 中文弯引号（跳过缩写中的撇号：don't、it's 等）
    def _replace_single(m):
        before, after = m.group(1), m.group(3)
        # 夹在字母之间 → 撇号，保持原样
        if re.match(r'[A-Za-z]', before or '') and re.match(r'[A-Za-z]', after or ''):
            return m.group(0)
        _replace_single.count += 1
        return '‘' if _replace_single.count % 2 == 1 else '’'
    _replace_single.count = 0
    text = re.sub(r"(.?)(')(.?)", _replace_single, text)

    return text


def convert_for_easypub(input_file: str, output_file: str = None, book_title: str = "", author: str = "", show_catalog: bool = True, ignore_mismatch: bool = False, filter_ads: bool = True, ad_rules: dict = None, normalize_punct: bool = True) -> Tuple[Optional[str], Optional[Dict]]:
    if output_file is None:
        base_name = os.path.splitext(input_file)[0]
        output_file = f"{base_name}_epub_ready.txt"

    print(f"\n📁 正在处理: {os.path.basename(input_file)}")
    print(f"   输入: {input_file}")

    try:
        content, encoding = EncodingDetector.read_file_with_auto_encoding(input_file)
        print(f"   编码检测: 使用{encoding}编码")
    except Exception as e:
        print(f"   ❌ 无法读取文件: {e}")
        return None, None

    if normalize_punct:
        content = _normalize_punctuation(content)

    content = ChapterAnalyzer.fix_broken_numbering(content)

    if filter_ads:
        _rules = ad_rules or {}
        content, ad_count = AdFilter.filter_content(
            content,
            threshold=_rules.get('threshold', 0.68),
            hard_kw=_rules.get('hard_kw'),
            soft_kw=_rules.get('soft_kw'),
        )
        if ad_count:
            print(f"   🧹 过滤广告行: {ad_count} 行")
    content, wm_count, wm_list = NameCleaner.clean(content)
    if wm_count:
        preview = '、'.join(wm_list[:5])
        suffix = f' 等 {wm_count} 处' if wm_count > 5 else f' 共 {wm_count} 处'
        print(f"   🔤 清理独立行水印: {preview}{suffix}")

    # 使用ChapterAnalyzer获取准确的章节信息
    chapter_structure = ChapterAnalyzer.analyze_chapter_structure(content, config_name='default')
    accurate_chapters = chapter_structure['total_chapters']
    print(f"   原始章节: {accurate_chapters}个")

    # 跨章节内容一致性检测
    if not ignore_mismatch:
        mismatch = ConsistencyChecker.check(content, chapter_structure)
        if mismatch:
            raise ContentMismatchError(mismatch)

    # 传递章节信息给optimize_for_epub，让它过滤误识别的章节
    optimized_content, analysis = EasyPubOptimizer.optimize_for_epub(content, book_title, author, chapter_structure)

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(optimized_content)
    except PermissionError:
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        output_file = os.path.join(os.path.dirname(__file__), f"{base_name}_epub_ready.txt")
        print(f"   ⚠️ 原目录无写入权限，输出到脚本目录: {output_file}")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(optimized_content)

    print(f"   ✅ 优化完成!")
    print(f"   输出: {output_file}")
    print(f"   大小: {DirectoryDisplay.format_size(os.path.getsize(output_file))}")
    print(f"   章节: {analysis['total_chapters']}个")
    print(f"   行数: {analysis['total_lines']:,}行")
    print(f"   字数: {analysis['total_chars']:,}字")

    if show_catalog:
        print("\n" + "=" * 60)
        catalog = DirectoryDisplay.display_chapter_catalog(output_file, max_chapters=10)
        print(catalog)

    analysis_file = output_file.replace('.txt', '_analysis.json')
    with open(analysis_file, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)

    print(f"\n   分析结果已保存: {analysis_file}")
    return output_file, analysis


def batch_convert_for_easypub(input_dir: str, output_dir: str = None, metadata_file: str = None, show_summary: bool = True, filter_ads: bool = True, ad_rules: dict = None) -> List[Dict]:
    if output_dir is None:
        output_dir = os.path.join(input_dir, "epub_ready")
    os.makedirs(output_dir, exist_ok=True)

    metadata = {}
    if metadata_file and os.path.exists(metadata_file):
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if ':' in line:
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            metadata[parts[0].strip()] = parts[1].strip()
            print(f"已加载元数据文件: {len(metadata)} 条记录")
        except Exception as e:
            print(f"警告: 无法读取元数据文件: {e}")

    txt_files = [os.path.join(input_dir, f) for f in os.listdir(input_dir) if f.lower().endswith('.txt') and not f.endswith('_epub_ready.txt')]
    if not txt_files:
        print(f"在目录 {input_dir} 中没有找到txt文件")
        return []

    print(f"\n📂 找到 {len(txt_files)} 个txt文件")
    print("=" * 60)

    results = []
    for txt_file in txt_files:
        try:
            filename = os.path.basename(txt_file)
            output_file = os.path.join(output_dir, filename.replace('.txt', '_epub_ready.txt'))
            book_title = metadata.get(filename, os.path.splitext(filename)[0])
            author = "未知"
            if ' - ' in book_title:
                parts = book_title.split(' - ', 1)
                if len(parts) == 2:
                    author, book_title = parts

            output_path, analysis = convert_for_easypub(txt_file, output_file, book_title, author, show_catalog=False, filter_ads=filter_ads, ad_rules=ad_rules)

            if output_path and analysis:
                results.append({
                    'filename': filename, 'input': txt_file, 'output': output_path,
                    'size': os.path.getsize(output_path), 'chapters': analysis['total_chapters'],
                    'lines': analysis['total_lines'], 'chars': analysis['total_chars']
                })
        except Exception as e:
            print(f"\n❌ 处理失败 {filename}: {str(e)}")
            results.append({'filename': filename, 'error': str(e)})

    if show_summary and results:
        print("\n" + "=" * 60)
        summary = DirectoryDisplay.display_batch_summary(results, output_dir)
        print(summary)
        print("\n📁 输出目录结构:")
        print(DirectoryDisplay.display_file_tree(output_dir))

        report_file = os.path.join(output_dir, "batch_report.md")
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("# 批量处理报告\n\n")
            f.write(summary.replace("📊", "#").replace("=" * 60, "---"))
            f.write("\n\n## 文件列表\n\n")
            for result in results:
                if 'error' not in result:
                    f.write(f"### {result['filename']}\n")
                    f.write(f"- 输出文件: {os.path.basename(result['output'])}\n")
                    f.write(f"- 章节数: {result.get('chapters', 0)}\n")
                    f.write(f"- 文件大小: {DirectoryDisplay.format_size(result.get('size', 0))}\n\n")
        print(f"\n📄 详细报告已保存: {report_file}")

    return results