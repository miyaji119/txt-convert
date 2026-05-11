"""章节分析模块"""

import re
from typing import Dict, List


class ChapterAnalyzer:
    """章节分析器"""

    CHAPTER_PATTERNS = [
        (r'^[=]+第(\d+)章\s*(.*?)[=]*$', 'equals'),
        (r'^第([零一二三四五六七八九十百千万\d]+)章\s*(.*)$', 'chinese'),
        (r'^(攻)?第([零一二三四五六七八九十百千万\d]+)章\s*(.*)$', 'prefix'),
        (r'^\d+、第([零一二三四五六七八九十百千万\d]+)章\s*(.*)$', 'number_chinese'),
        (r'^\d+、番外(.*)$', 'number_fanwai'),
        (r'^番外([零一二三四五六七八九十百千万\d]+)(.*)$', 'fanwai'),
        (r'^(\d+)、(.*)$', 'simple_number'),
        (r'^楔子\s*(.*)$', 'xiezi'),
    ]

    NEXT_CHAPTER_PATTERNS = [
        r'^[=]+第\d+章\s*.*[=]*$',
        r'^第[零一二三四五六七八九十百千万\d]+章\s*.*$',
        r'^\d+、[零一二三四五六七八九十百千万\d]+章\s*.*$',
        r'^(攻)?第[零一二三四五六七八九十百千万\d]+章\s*.*$',
    ]

    @staticmethod
    def chinese_to_arabic(cn: str) -> int:
        """中文数字转阿拉伯数字"""
        cn_map = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                  '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
        if cn == '十':
            return 10
        if '十' in cn:
            parts = cn.split('十')
            if parts[0] == '':
                return 10 + cn_map.get(parts[1], 0)
            else:
                return cn_map.get(parts[0], 0) * 10 + cn_map.get(parts[1], 0)
        return cn_map.get(cn, 0)

    @staticmethod
    def normalize_chapter_num(num_str: str) -> int:
        """规范化章节编号"""
        if num_str.isdigit():
            return int(num_str)
        return ChapterAnalyzer.chinese_to_arabic(num_str)

    @staticmethod
    def parse_chapter_title(line: str, ptype: str, chapter_match) -> tuple:
        """解析章节标题和编号"""
        if ptype == 'equals':
            chapter_num = int(chapter_match.group(1))
            title_part = chapter_match.group(2).strip()
            chapter_title = f"第{chapter_num}章 {title_part}" if title_part else f"第{chapter_num}章"
        elif ptype == 'chinese':
            chapter_num = ChapterAnalyzer.normalize_chapter_num(chapter_match.group(1))
            title_part = chapter_match.group(2).strip()
            chapter_title = f"第{chapter_num}章 {title_part}" if title_part else f"第{chapter_num}章"
        elif ptype == 'prefix':
            chapter_num = ChapterAnalyzer.normalize_chapter_num(chapter_match.group(2))
            title_part = chapter_match.group(3).strip()
            chapter_title = f"第{chapter_num}章 {title_part}" if title_part else f"第{chapter_num}章"
        elif ptype == 'simple_number':
            chapter_num = int(chapter_match.group(1))
            title_part = chapter_match.group(2).strip()
            chapter_title = f"第{chapter_num}章 {title_part}" if title_part else f"第{chapter_num}章"
        elif ptype == 'xiezi':
            chapter_num = 0
            chapter_title = '楔子' + (chapter_match.group(1).strip() if chapter_match.group(1).strip() else '')
        elif ptype == 'number_chinese':
            chapter_num = ChapterAnalyzer.normalize_chapter_num(chapter_match.group(1))
            title_part = chapter_match.group(2).strip()
            chapter_title = f"第{chapter_num}章 {title_part}" if title_part else f"第{chapter_num}章"
        elif ptype == 'number_fanwai':
            chapter_num = 999
            fanwai_title = chapter_match.group(1).strip()
            chapter_title = f"番外 {fanwai_title}" if fanwai_title else "番外"
        elif ptype == 'fanwai':
            chapter_num = 999
            fanwai_num = ChapterAnalyzer.normalize_chapter_num(chapter_match.group(1))
            fanwai_rest = chapter_match.group(2).strip()
            chapter_title = f"番外{fanwai_num}{fanwai_rest}" if fanwai_rest else f"番外{fanwai_num}"
        else:
            chapter_num = None
            chapter_title = ""
        return chapter_num, chapter_title

    @staticmethod
    def analyze_chapter_structure(content: str) -> Dict:
        """分析章节结构"""
        lines = content.split('\n')
        chapters = []
        chapter_count = 0
        line_count = 0

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            line_count += 1

            for pattern, ptype in ChapterAnalyzer.CHAPTER_PATTERNS:
                chapter_match = re.match(pattern, line_stripped)
                if chapter_match:
                    chapter_num, chapter_title = ChapterAnalyzer.parse_chapter_title(line_stripped, ptype, chapter_match)
                    if chapter_num is None:
                        continue

                    start_line = i
                    end_line = len(lines) - 1

                    for j in range(i + 1, len(lines)):
                        next_line = lines[j].strip()
                        for ncp in ChapterAnalyzer.NEXT_CHAPTER_PATTERNS:
                            if re.match(ncp, next_line):
                                end_line = j - 1
                                break
                        else:
                            continue
                        break

                    chapter_lines = end_line - start_line
                    char_count = sum(len(lines[k].strip()) for k in range(start_line, min(end_line + 1, len(lines))))

                    chapters.append({
                        'number': chapter_num,
                        'title': chapter_title if chapter_title else f"第{chapter_num}章",
                        'start_line': start_line + 1,
                        'end_line': end_line + 1,
                        'line_count': chapter_lines,
                        'char_count': char_count
                    })
                    chapter_count += 1
                    break

        return {
            'total_chapters': chapter_count,
            'total_lines': line_count,
            'total_chars': len(content),
            'chapters': chapters
        }
