"""章节分析模块"""

import bisect
import re
from typing import Dict

from chapter_config import ChapterConfig


class ChapterAnalyzer:
    """章节分析器"""

    # 标准章节模式配置: ptype -> (章节号group, 标题group, 单位, 是否中文数字)
    _STANDARD = {
        'equals':            (1, 2, '章', False),
        'chinese':           (1, 2, '章', True),
        'prefix':            (2, 3, '章', True),
        'simple_number':     (1, 2, '章', False),
        'number_chinese':    (1, 2, '章', True),
        'number_dot_chapter':(2, 3, '章', False),
        'number_dot_title':  (1, 2, '章', False),
        'special_prefix':    (1, 2, '章', False),
        'bracket_number':    (1, 2, '章', False),
        'standalone_number': (1, None, '章', False),
        'volume':            (1, 2, '卷', True),
        'chinese_volume':    (1, 2, '卷', True),
        'case_volume':       (1, 2, '案', True),
        'part':              (1, 2, '部分', True),
        'section':           (1, 2, '节', True),
    }

    def __init__(self, config_name: str = 'default'):
        self.config = ChapterConfig(config_name)
        self.CHAPTER_PATTERNS = self.config.CHAPTER_PATTERNS
        self.NEXT_CHAPTER_PATTERNS = self.config.NEXT_CHAPTER_PATTERNS
        self.FILTER_RULES = self.config.FILTER_RULES

    # ------------------------------------------------------------------
    # 数字转换
    # ------------------------------------------------------------------
    @staticmethod
    def chinese_to_arabic(cn: str) -> int:
        """中文数字转阿拉伯数字"""
        cn_map = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                  '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
        if cn == '十':
            return 10
        if '十' in cn:
            parts = cn.split('十')
            left = cn_map.get(parts[0], 0) if parts[0] else 1
            return left * 10 + cn_map.get(parts[1], 0) if len(parts) > 1 and parts[1] else left * 10
        return cn_map.get(cn, 0)

    @staticmethod
    def normalize_chapter_num(num_str: str) -> int:
        """规范化章节编号"""
        if num_str.isdigit():
            return int(num_str)
        return ChapterAnalyzer.chinese_to_arabic(num_str)

    # ------------------------------------------------------------------
    # 章节标题解析
    # ------------------------------------------------------------------
    @staticmethod
    def parse_chapter_title(line: str, ptype: str, chapter_match) -> tuple:
        """解析章节标题和编号"""
        # 标准模式：第X{unit} {title}
        cfg = ChapterAnalyzer._STANDARD.get(ptype)
        if cfg:
            num_grp, title_grp, unit, normalize = cfg
            raw = chapter_match.group(num_grp)
            chapter_num = ChapterAnalyzer.normalize_chapter_num(raw) if normalize else int(raw)
            title_part = chapter_match.group(title_grp).strip() if title_grp else ""
            unit_str = f"第{chapter_num}{unit}"
            return chapter_num, f"{unit_str} {title_part}" if title_part else unit_str

        # 特殊模式
        if ptype == 'xiezi':
            sub = chapter_match.group(1).strip()
            return 0, f"楔子{sub}" if sub else "楔子"

        if ptype == 'number_fanwai':
            sub = chapter_match.group(1).strip()
            return 999, f"番外 {sub}" if sub else "番外"

        if ptype == 'fanwai':
            num = ChapterAnalyzer.normalize_chapter_num(chapter_match.group(1))
            rest = chapter_match.group(2).strip()
            return 999, f"番外{num}{rest}" if rest else f"番外{num}"

        if ptype == 'number_dot_fanwai':
            seq = int(chapter_match.group(1))
            sub = chapter_match.group(2).strip()
            return seq, f"番外 {sub}" if sub else f"第{seq}章 番外"

        return None, ""

    @staticmethod
    def _get_title_part(ptype: str, chapter_match) -> str:
        """获取标题部分用于过滤检查"""
        cfg = ChapterAnalyzer._STANDARD.get(ptype)
        if cfg:
            title_grp = cfg[1]
            if title_grp and chapter_match.lastindex >= title_grp:
                return chapter_match.group(title_grp).strip()
        if ptype in ('number_fanwai', 'number_dot_fanwai') and chapter_match.lastindex >= 2:
            return chapter_match.group(2).strip()
        if ptype == 'fanwai' and chapter_match.lastindex >= 2:
            return chapter_match.group(2).strip()
        return ""

    # ------------------------------------------------------------------
    # 章节结构分析
    # ------------------------------------------------------------------
    @staticmethod
    def analyze_chapter_structure(content: str, config_name: str = 'default') -> Dict:
        """分析章节结构"""
        config = ChapterConfig(config_name)
        chapter_patterns = config.CHAPTER_PATTERNS
        filter_rules = config.FILTER_RULES

        # 预编译 next_chapter_patterns 避免循环内重复编译
        next_chapter_compiled = [re.compile(p) for p in config.NEXT_CHAPTER_PATTERNS]

        lines = content.split('\n')
        chapters = []
        seen_chapter_nums = set()

        # 第一遍：找出所有章节起始行索引，用于 bisect 查找下一章节
        chapter_start_indices = []
        for i, line in enumerate(lines):
            s = line.strip()
            if any(ncp.match(s) for ncp in next_chapter_compiled):
                chapter_start_indices.append(i)

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            for pattern, ptype in chapter_patterns:
                chapter_match = re.match(pattern, line_stripped)
                if not chapter_match:
                    continue

                # 过滤检查
                title_part = ChapterAnalyzer._get_title_part(ptype, chapter_match)
                if any(f['func'](title_part=title_part, ptype=ptype,
                                 chapter_match=chapter_match,
                                 seen_chapter_nums=seen_chapter_nums)
                       for f in filter_rules):
                    break

                chapter_num, chapter_title = ChapterAnalyzer.parse_chapter_title(
                    line_stripped, ptype, chapter_match)
                if chapter_num is None or chapter_num in seen_chapter_nums:
                    break

                seen_chapter_nums.add(chapter_num)

                # O(log n) 查找下一章节起始行
                pos = bisect.bisect_right(chapter_start_indices, i)
                end_line = (chapter_start_indices[pos] - 1
                            if pos < len(chapter_start_indices)
                            else len(lines) - 1)

                char_count = sum(len(lines[k].strip())
                                 for k in range(i, min(end_line + 1, len(lines))))

                chapters.append({
                    'number': chapter_num,
                    'title': chapter_title or f"第{chapter_num}章",
                    'start_line': i + 1,
                    'end_line': end_line + 1,
                    'line_count': end_line - i,
                    'char_count': char_count
                })
                break

        return {
            'total_chapters': len(chapters),
            'total_lines': len(lines),
            'total_chars': len(content),
            'chapters': chapters
        }
