"""章节分析模块"""

import re
from typing import Dict, List

from chapter_config import ChapterConfig, default_config


class ChapterAnalyzer:
    """章节分析器"""

    def __init__(self, config_name: str = 'default'):
        """初始化章节分析器
        
        Args:
            config_name: 配置名称，可选值: 'default', 'bl', 'fantasy', 'detective'
        """
        self.config = ChapterConfig(config_name)
        self.CHAPTER_PATTERNS = self.config.CHAPTER_PATTERNS
        self.NEXT_CHAPTER_PATTERNS = self.config.NEXT_CHAPTER_PATTERNS
        self.FILTER_RULES = self.config.FILTER_RULES

    @staticmethod
    def _get_patterns(config_name: str = 'default'):
        """获取指定配置的章节模式（静态方法兼容旧代码）"""
        config = ChapterConfig(config_name)
        return config.CHAPTER_PATTERNS, config.NEXT_CHAPTER_PATTERNS, config.FILTER_RULES

    # 保持原有的静态变量，用于向后兼容
    _default_patterns, _default_next_patterns, _default_filters = _get_patterns.__func__('default')
    CHAPTER_PATTERNS_STATIC = _default_patterns
    NEXT_CHAPTER_PATTERNS_STATIC = _default_next_patterns
    FILTER_RULES_STATIC = _default_filters

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
        elif ptype == 'special_prefix':
            chapter_num = int(chapter_match.group(1))
            title_part = chapter_match.group(2).strip()
            chapter_title = f"第{chapter_num}章 {title_part}" if title_part else f"第{chapter_num}章"
        elif ptype == 'case_volume':
            chapter_num = ChapterAnalyzer.normalize_chapter_num(chapter_match.group(1))
            title_part = chapter_match.group(2).strip()
            chapter_title = f"第{chapter_num}案 {title_part}" if title_part else f"第{chapter_num}案"
        elif ptype == 'bracket_number':
            chapter_num = int(chapter_match.group(1))
            title_part = chapter_match.group(2).strip()
            chapter_title = f"第{chapter_num}章 {title_part}" if title_part else f"第{chapter_num}章"
        elif ptype == 'standalone_number':
            chapter_num = int(chapter_match.group(1))
            chapter_title = f"第{chapter_num}章"
        elif ptype == 'volume':
            chapter_num = ChapterAnalyzer.normalize_chapter_num(chapter_match.group(1))
            title_part = chapter_match.group(2).strip()
            chapter_title = f"第{chapter_num}卷 {title_part}" if title_part else f"第{chapter_num}卷"
        elif ptype == 'chinese_volume':
            chapter_num = ChapterAnalyzer.normalize_chapter_num(chapter_match.group(1))
            title_part = chapter_match.group(2).strip()
            chapter_title = f"第{chapter_num}卷 {title_part}" if title_part else f"第{chapter_num}卷"
        elif ptype == 'part':
            chapter_num = ChapterAnalyzer.normalize_chapter_num(chapter_match.group(1))
            title_part = chapter_match.group(2).strip()
            chapter_title = f"第{chapter_num}部分 {title_part}" if title_part else f"第{chapter_num}部分"
        elif ptype == 'section':
            chapter_num = ChapterAnalyzer.normalize_chapter_num(chapter_match.group(1))
            title_part = chapter_match.group(2).strip()
            chapter_title = f"第{chapter_num}节 {title_part}" if title_part else f"第{chapter_num}节"
        else:
            chapter_num = None
            chapter_title = ""
        return chapter_num, chapter_title

    @staticmethod
    def _get_title_part(ptype: str, chapter_match) -> str:
        """获取标题部分用于过滤检查"""
        title_part = ""
        if ptype in ['equals', 'chinese', 'special_prefix', 'bracket_number', 'volume', 'chinese_volume', 'part', 'section']:
            if chapter_match.lastindex >= 2:
                title_part = chapter_match.group(2).strip()
        elif ptype == 'prefix':
            if chapter_match.lastindex >= 3:
                title_part = chapter_match.group(3).strip()
        elif ptype in ['simple_number', 'number_title_combined']:
            if chapter_match.lastindex >= 2:
                title_part = chapter_match.group(2).strip()
        elif ptype == 'number_chinese':
            if chapter_match.lastindex >= 2:
                title_part = chapter_match.group(2).strip()
        return title_part

    @staticmethod
    def analyze_chapter_structure(content: str, config_name: str = 'default') -> Dict:
        """分析章节结构
        
        Args:
            content: 文本内容
            config_name: 配置名称，可选值: 'default', 'bl', 'fantasy', 'detective'
        
        Returns:
            章节结构字典
        """
        # 获取配置
        config = ChapterConfig(config_name)
        chapter_patterns = config.CHAPTER_PATTERNS
        next_chapter_patterns = config.NEXT_CHAPTER_PATTERNS
        filter_rules = config.FILTER_RULES

        lines = content.split('\n')
        chapters = []
        chapter_count = 0
        line_count = 0
        last_chapter_num = None  # 跟踪上一个章节号
        seen_chapter_nums = set()  # 记录已识别章节号，用于检测重复章节

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            line_count += 1

            for pattern, ptype in chapter_patterns:
                chapter_match = re.match(pattern, line_stripped)
                if chapter_match:
                    # 获取标题部分用于过滤检查
                    title_part = ChapterAnalyzer._get_title_part(ptype, chapter_match)

                    # 应用过滤规则
                    should_filter = False
                    for filter_rule in filter_rules:
                        filter_func = filter_rule['func']
                        try:
                            if filter_func(title_part=title_part, ptype=ptype, 
                                          chapter_match=chapter_match, 
                                          seen_chapter_nums=seen_chapter_nums):
                                should_filter = True
                                break
                        except Exception as e:
                            # 过滤规则执行失败，跳过该规则
                            pass
                    
                    if should_filter:
                        break

                    chapter_num, chapter_title = ChapterAnalyzer.parse_chapter_title(line_stripped, ptype, chapter_match)
                    if chapter_num is None:
                        continue

                    # 检查章节号的递增性：不应出现重复章节号（通过过滤规则已处理）
                    if chapter_num in seen_chapter_nums:
                        break

                    seen_chapter_nums.add(chapter_num)
                    last_chapter_num = chapter_num

                    start_line = i
                    end_line = len(lines) - 1

                    for j in range(i + 1, len(lines)):
                        next_line = lines[j].strip()
                        for ncp in next_chapter_patterns:
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
