"""EPUB生成模块"""

import os
import re
from datetime import datetime
from typing import Optional, List, Dict

try:
    from ebooklib import epub
    EPUB_SUPPORT = True
except ImportError:
    EPUB_SUPPORT = False

from encoding import EncodingDetector
from cover import CoverDownloader
from display import DirectoryDisplay


class EPUBGenerator:
    """EPUB文件生成器"""

    CHAPTER_PATTERNS = [
        (r'^[=]+第\s*(\d+)\s*章\s*(.*?)[=]*$', 'equals'),
        (r'^第\s*([零一二三四五六七八九十百千万\d]+)\s*章\s*(.*)$', 'chinese'),  # 支持数字前后有空格
        (r'^(攻)?第\s*([零一二三四五六七八九十百千万\d]+)\s*章\s*(.*)$', 'prefix'),
        (r'^\d+、第([零一二三四五六七八九十百千万\d]+)章\s*(.*)$', 'number_chinese'),
        (r'^\d+、番外(.*)$', 'number_fanwai'),
        (r'^番外([零一二三四五六七八九十百千万\d]+)(.*)$', 'fanwai'),
        (r'^(\d+)、(.*)$', 'simple_number'),
        (r'^(\d+)\.?\s*(.+)$', 'number_title_combined'),  # 新增：数字+标题连在一起的格式
        (r'^楔子\s*(.*)$', 'xiezi'),
        (r'^[◇◆\*•·]\s*第(\d+)章\s*(.*)$', 'special_prefix'),
        (r'^第([零一二三四五六七八九十百千万]+)案[：:]\s*(.*)$', 'case_volume'),
        (r'^\[(\d+)\](.*)$', 'bracket_number'),
        (r'^(\d+)$', 'standalone_number'),
    ]

    INTRO_MARKERS = [
        '文案：', '简介：', '内容标签：', '搜索关键字：', '一句话简介：', '立意：',
        '文案:', '简介:', '标签：', '主角：', '配角：', '其它：', '年下', 'HE', 'BE'
    ]

    @staticmethod
    def _chinese_to_arabic(cn: str) -> int:
        cn_map = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
        if cn == '十':
            return 10
        if '十' in cn:
            parts = cn.split('十')
            return 10 + cn_map.get(parts[1], 0) if parts[0] == '' else cn_map.get(parts[0], 0) * 10 + cn_map.get(parts[1], 0)
        return cn_map.get(cn, 0)

    @staticmethod
    def _normalize_chapter_num(num_str: str) -> int:
        return int(num_str) if num_str.isdigit() else EPUBGenerator._chinese_to_arabic(num_str)

    @staticmethod
    def _is_valid_chapter_number(chap_num: int, is_first: bool) -> bool:
        if chap_num in (0, 999):
            return True
        return chap_num <= 3 if is_first else chap_num >= 1

    @staticmethod
    def _extract_author(content: str) -> Optional[str]:
        patterns = [
            r'《[^》]+》作者[：:]\s*([^\n]+)', r'作者[：:]\s*([^\n]+)', r'作者\s+([^\n]+)',
            r'by\s+([^\n]+)', r'【作者】\s*([^\n]+)', r'\[作者\]\s*([^\n]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                author = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', match.group(1).strip())
                if author:
                    return author
        return None

    @staticmethod
    def _extract_title(content: str) -> Optional[str]:
        # 移除BOM字符
        if content.startswith('\ufeff'):
            content = content[1:]
        lines = content.split('\n')[:20]
        print(f"[DEBUG] 书名提取 - 分析文件前20行")
        
        title_prefixes = ['书名：', '书名:', '题名：', '题名:', '书名', '题名']
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if line_stripped and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith('作者：') or next_line.startswith('作者:'):
                    print(f"[DEBUG] 书名提取 - 匹配模式：书名+作者行，行{i+1}: '{line_stripped}', 作者行: '{next_line}'")
                    title = line_stripped
                    original_title = title
                    for prefix in title_prefixes:
                        if title.startswith(prefix):
                            print(f"[DEBUG] 书名提取 - 移除前缀 '{prefix}'")
                            title = title[len(prefix):].strip()
                            break
                    title = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s\[\]]', '', title).strip()
                    if title and len(title) > 1 and len(title) < 50:
                        print(f"[DEBUG] 书名提取 - 成功：'{title}' (原始: '{original_title}')")
                        return title
        
        first_part = '\n'.join(lines)
        
        patterns = [
            r'《([^》]+)》作者', r'书名[：:]\s*([^\n]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, first_part)
            if match:
                print(f"[DEBUG] 书名提取 - 匹配正则模式：'{pattern}'")
                title = match.group(1).strip() if match.group(1) else (match.group(2).strip() if match.group(2) else None)
                if title:
                    title = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s\[\]]', '', title).strip()
                    if title:
                        print(f"[DEBUG] 书名提取 - 成功：'{title}'")
                        return title
        
        match = re.search(r'《([^》]+)》', first_part)
        if match:
            print(f"[DEBUG] 书名提取 - 匹配书名号格式")
            title = match.group(1).strip()
            title = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s\[\]]', '', title).strip()
            if title and len(title) > 1 and len(title) < 50:
                return title
        
        return None

    @staticmethod
    def _parse_chapters(content: str) -> List[Dict]:
        lines = content.split('\n')
        chapters = []
        intro_lines = []
        current_title = None
        current_lines = []
        in_intro = False
        last_chapter_num = None  # 跟踪上一个章节号，用于判断是否是章节内小标题
        seen_chapter_nums = set()  # 记录已识别章节号，用于检测重复章节
        uses_arabic_only = False  # 标记是否使用纯阿拉伯数字格式

        for line in lines[:30]:
            if any(marker in line.strip() for marker in EPUBGenerator.INTRO_MARKERS):
                in_intro = True
                break

        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('<!--') or stripped.startswith('-->'):
                continue

            if not current_title:
                if any(marker in stripped for marker in EPUBGenerator.INTRO_MARKERS):
                    in_intro = True
                    intro_lines.append(line)
                    continue

                if in_intro:
                    is_chapter = False
                    for pattern, ptype in EPUBGenerator.CHAPTER_PATTERNS:
                        if ptype == 'simple_number':
                            match = re.match(pattern, stripped)
                            if match and int(match.group(1)) == 1 and any(k in match.group(2) for k in ['章', '节', '楔子', '番外', '尾声', '后记']):
                                is_chapter = True
                                in_intro = False
                                break
                            continue
                        if ptype == 'standalone_number':
                            match = re.match(pattern, stripped)
                            if match and int(match.group(1)) == 1:
                                is_chapter = True
                                in_intro = False
                                break
                            continue
                        if ptype == 'number_title_combined':
                            # 在简介区域，数字+标题格式（如1.xxx）不认为是章节
                            # 需要明确包含章节关键词才认为是章节
                            match = re.match(pattern, stripped)
                            if match and int(match.group(1)) == 1 and any(k in match.group(2) for k in ['章', '节', '楔子', '番外', '尾声', '后记']):
                                is_chapter = True
                                in_intro = False
                                break
                            continue
                        if re.match(pattern, stripped):
                            is_chapter = True
                            in_intro = False
                            break
                    if not is_chapter:
                        intro_lines.append(line)
                        continue

            chapter_num = None
            chapter_title = ""
            matched_type = None
            for pattern, ptype in EPUBGenerator.CHAPTER_PATTERNS:
                match = re.match(pattern, stripped)
                if match:
                    print(f"[DEBUG] 章节识别 - 匹配成功: 行{idx+1}, 原始文本: {repr(stripped[:50])}, 模式类型: {ptype}")
                    matched_type = ptype
                    if ptype == 'equals':
                        chapter_num = int(match.group(1))
                        title_part = match.group(2).strip()
                        chapter_title = f"第{chapter_num}章 {title_part}" if title_part else f"第{chapter_num}章"
                    elif ptype == 'chinese':
                        chapter_num = EPUBGenerator._normalize_chapter_num(match.group(1))
                        title_part = match.group(2).strip()
                        # 检查是否可能是对话格式（如：正义的毒雾）
                        if title_part.startswith('：') or title_part.startswith(':'):
                            print(f"[DEBUG] 章节识别 - 跳过对话格式: 行{idx+1}, 文本: {repr(stripped)}")
                            chapter_num = None
                            continue
                        # 检查是否可能是问题格式（如为什么、既然、怎么）
                        if any(title_part.startswith(prefix) for prefix in ['为什么', '既然', '怎么', '如何', '什么', '谁', '何时', '何地']):
                            print(f"[DEBUG] 章节识别 - 跳过问题格式: 行{idx+1}, 文本: {repr(stripped)}")
                            chapter_num = None
                            continue
                        # 检查是否可能是内容的一部分（如"了，"开头）
                        if title_part.startswith('了，') or title_part.startswith('的，'):
                            print(f"[DEBUG] 章节识别 - 跳过内容片段: 行{idx+1}, 文本: {repr(stripped)}")
                            chapter_num = None
                            continue
                        # 检查是否可能是更新公告（包含更新时间信息）
                        if '更新' in title_part or '日~' in title_part or '（周' in title_part:
                            print(f"[DEBUG] 章节识别 - 跳过更新公告: 行{idx+1}, 文本: {repr(stripped)}")
                            chapter_num = None
                            continue
                        chapter_title = f"第{chapter_num}章 {title_part}" if title_part else f"第{chapter_num}章"
                    elif ptype == 'prefix':
                        chapter_num = EPUBGenerator._normalize_chapter_num(match.group(2))
                        title_part = match.group(3).strip()
                        # 检查是否可能是对话格式（如：正义的毒雾）
                        if title_part.startswith('：') or title_part.startswith(':'):
                            print(f"[DEBUG] 章节识别 - 跳过对话格式: 行{idx+1}, 文本: {repr(stripped)}")
                            chapter_num = None
                            continue
                        # 检查是否可能是问题格式（如为什么、既然、怎么）
                        if any(title_part.startswith(prefix) for prefix in ['为什么', '既然', '怎么', '如何', '什么', '谁', '何时', '何地']):
                            print(f"[DEBUG] 章节识别 - 跳过问题格式: 行{idx+1}, 文本: {repr(stripped)}")
                            chapter_num = None
                            continue
                        # 检查是否可能是内容的一部分（如"了，"开头）
                        if title_part.startswith('了，') or title_part.startswith('的，'):
                            print(f"[DEBUG] 章节识别 - 跳过内容片段: 行{idx+1}, 文本: {repr(stripped)}")
                            chapter_num = None
                            continue
                        chapter_title = f"第{chapter_num}章 {title_part}" if title_part else f"第{chapter_num}章"
                    elif ptype == 'xiezi':
                        chapter_num = 0
                        chapter_title = '楔子' + (match.group(1).strip() if match.group(1).strip() else '')
                    elif ptype == 'number_chinese':
                        chapter_num = EPUBGenerator._normalize_chapter_num(match.group(1))
                        title_part = match.group(2).strip()
                        chapter_title = f"第{chapter_num}章 {title_part}" if title_part else f"第{chapter_num}章"
                    elif ptype == 'simple_number':
                        chapter_num = int(match.group(1))
                        title_part = match.group(2).strip()
                        # 检查是否可能是问题格式（如为什么、既然、怎么）
                        if any(title_part.startswith(prefix) for prefix in ['为什么', '既然', '怎么', '如何', '什么', '谁', '何时', '何地']):
                            print(f"[DEBUG] 章节识别 - 跳过问题格式: 行{idx+1}, 文本: {repr(stripped)}")
                            chapter_num = None
                            continue
                        # 检查是否可能是倒计时格式（如6、5……）
                        # 可能的格式：6、5…… 或 6、5... 或 6、5…
                        cleaned_title = title_part.lstrip('、，,．.')  # 移除开头的标点
                        if cleaned_title.startswith('5') or cleaned_title.startswith('4') or cleaned_title.startswith('3') or cleaned_title.startswith('2') or cleaned_title.startswith('1'):
                            if chapter_num - int(cleaned_title[0]) == 1:
                                print(f"[DEBUG] 章节识别 - 跳过倒计时格式: 行{idx+1}, 文本: {repr(stripped)}")
                                chapter_num = None
                                continue
                        chapter_title = f"第{chapter_num}章 {title_part}" if title_part else f"第{chapter_num}章"
                    elif ptype == 'number_fanwai':
                        chapter_num = 999
                        chapter_title = f"番外 {match.group(1).strip()}" if match.group(1).strip() else "番外"
                    elif ptype == 'fanwai':
                        chapter_num = 999
                        fanwai_num = EPUBGenerator._normalize_chapter_num(match.group(1))
                        fanwai_rest = match.group(2).strip()
                        chapter_title = f"番外{fanwai_num}{fanwai_rest}" if fanwai_rest else f"番外{fanwai_num}"
                    elif ptype == 'special_prefix':
                        chapter_num = int(match.group(1))
                        title_part = match.group(2).strip()
                        chapter_title = f"第{chapter_num}章 {title_part}" if title_part else f"第{chapter_num}章"
                    elif ptype == 'case_volume':
                        chapter_num = None
                        case_num = match.group(1)
                        case_title = match.group(2).strip()
                        chapter_title = f"第{case_num}案：{case_title}" if case_title else f"第{case_num}案"
                    elif ptype == 'number_title_combined':
                        chapter_num = int(match.group(1))
                        title_part = match.group(2).strip()
                        # 检查是否可能是章节号+章+内容的格式（如1章 标题）
                        # 这种情况应该匹配 chinese 模式，而不是 number_title_combined
                        if title_part.startswith('章'):
                            print(f"[DEBUG] 章节识别 - 跳过章节格式: 行{idx+1}, 文本: {repr(stripped)}")
                            chapter_num = None
                            continue
                        # 检查是否可能是百分比格式（如25%、99%的玩家）
                        if title_part.startswith('%'):
                            print(f"[DEBUG] 章节识别 - 跳过百分比格式: 行{idx+1}, 文本: {repr(stripped)}")
                            chapter_num = None
                            continue
                        # 检查是否可能是对话格式（如：正义的毒雾）
                        if title_part.startswith('：') or title_part.startswith(':'):
                            print(f"[DEBUG] 章节识别 - 跳过对话格式: 行{idx+1}, 文本: {repr(stripped)}")
                            chapter_num = None
                            continue
                        # 检查是否可能是问题格式（如为什么、既然、怎么）
                        if any(title_part.startswith(prefix) for prefix in ['为什么', '既然', '怎么', '如何', '什么', '谁', '何时', '何地']):
                            print(f"[DEBUG] 章节识别 - 跳过问题格式: 行{idx+1}, 文本: {repr(stripped)}")
                            chapter_num = None
                            continue
                        # 检查是否可能是更新公告（包含更新时间信息）
                        if '更新' in title_part or '日~' in title_part or '（周' in title_part:
                            print(f"[DEBUG] 章节识别 - 跳过更新公告: 行{idx+1}, 文本: {repr(stripped)}")
                            chapter_num = None
                            continue
                        # 检查是否可能是内容的一部分（如"了，"开头）
                        if title_part.startswith('了，') or title_part.startswith('的，'):
                            print(f"[DEBUG] 章节识别 - 跳过内容片段: 行{idx+1}, 文本: {repr(stripped)}")
                            chapter_num = None
                            continue
                        # 检查是否可能是倒计时格式（如6、5……）
                        if title_part.startswith('、') or title_part.startswith('，') or title_part.startswith(','):
                            inner = title_part[1:].lstrip('、，,．.')
                            if inner.startswith('5') or inner.startswith('4') or inner.startswith('3') or inner.startswith('2') or inner.startswith('1'):
                                if chapter_num - int(inner[0]) == 1:
                                    print(f"[DEBUG] 章节识别 - 跳过倒计时格式: 行{idx+1}, 文本: {repr(stripped)}")
                                    chapter_num = None
                                    continue
                        # 检查是否可能是日期格式（如11月1号、12月）
                        if title_part.startswith('月') or title_part.startswith('月份'):
                            print(f"[DEBUG] 章节识别 - 跳过日期格式: 行{idx+1}, 文本: {repr(stripped)}")
                            chapter_num = None
                            continue
                        # 检查是否可能是时间格式（如22:45, 00:25）
                        if title_part.startswith(':') and re.match(r'^:\d{1,2}', title_part):
                            # 可能是时间格式，跳过
                            print(f"[DEBUG] 章节识别 - 跳过时间格式: 行{idx+1}, 文本: {repr(stripped)}")
                            chapter_num = None
                            continue
                        # 检查是否可能是日期/编号格式（如30号、741W）
                        if title_part.startswith('号') or title_part.startswith('W') or title_part.startswith('w'):
                            print(f"[DEBUG] 章节识别 - 跳过日期/编号格式: 行{idx+1}, 文本: {repr(stripped)}")
                            chapter_num = None
                            continue
                        # 检查是否可能是章节内的小标题（如1.豆澜、2.荷叶）
                        # 如果当前章节号大于这个数字很多（>50），可能是章节内小标题
                        if current_title and chapter_num < 10 and last_chapter_num and last_chapter_num - chapter_num > 50:
                            # 这很可能是章节内的小标题，不创建新章节
                            print(f"[DEBUG] 章节识别 - 跳过章节内小标题: 行{idx+1}, 文本: {repr(stripped)}, 当前章节: {current_title}, 上一章节号: {last_chapter_num}")
                            chapter_num = None
                            continue
                        # 检查是否可能是误匹配的大数字（如741、942）
                        if chapter_num > 200 and last_chapter_num and chapter_num - last_chapter_num > 100:
                            # 章节号突然跳变太大，可能是误匹配
                            print(f"[DEBUG] 章节识别 - 跳过异常大章节号: 行{idx+1}, 文本: {repr(stripped)}, 匹配章节号: {chapter_num}, 上一章节号: {last_chapter_num}")
                            chapter_num = None
                            continue
                        # 检查是否可能是误匹配的场景描述（如"82个人的考试"）
                        if title_part.startswith('个') or title_part.startswith('位') or title_part.startswith('名'):
                            print(f"[DEBUG] 章节识别 - 跳过数量描述: 行{idx+1}, 文本: {repr(stripped)}")
                            chapter_num = None
                            continue
                        # 检查是否可能是列表项（如"2. 如果做不到"）
                        if current_title and chapter_num < 5 and last_chapter_num and last_chapter_num > chapter_num + 10:
                            print(f"[DEBUG] 章节识别 - 跳过列表项: 行{idx+1}, 文本: {repr(stripped)}, 当前章节: {current_title}, 上一章节号: {last_chapter_num}")
                            chapter_num = None
                            continue
                        chapter_title = f"第{chapter_num}章 {title_part}" if title_part else f"第{chapter_num}章"
                    elif ptype == 'bracket_number':
                        chapter_num = int(match.group(1))
                        title_part = match.group(2).strip().replace('=', '').strip()
                        chapter_title = f"第{chapter_num}章 {title_part}" if title_part else f"第{chapter_num}章"
                    elif ptype == 'standalone_number':
                        chapter_num = int(match.group(1))
                        chapter_title = f"第{chapter_num}章"
                    break

            if chapter_num is not None or matched_type in ['case_volume', 'bracket_number', 'standalone_number']:
                if chapter_num is not None and not EPUBGenerator._is_valid_chapter_number(chapter_num, current_title is None):
                    print(f"[DEBUG] 章节识别 - 章节号验证失败: 行{idx+1}, 章节号: {chapter_num}, 是否是第一个章节: {current_title is None}")
                    continue
                # 检查章节号的递增性：如果已识别到后续章节，不应出现更小的章节号（除非是前言/楔子等特殊章节）
                if current_title is not None and chapter_num is not None and chapter_num in seen_chapter_nums:
                    print(f"[DEBUG] 章节识别 - 跳过重复章节: 行{idx+1}, 文本: {repr(stripped)}, 章节号: {chapter_num} 已存在")
                    continue
                # 检查格式一致性：如果之前章节都是阿拉伯数字格式，不应出现中文数字格式
                if current_title is not None and chapter_num is not None and uses_arabic_only:
                    # 判断当前章节是否使用中文数字格式（章节号不是纯数字）
                    chapter_str = match.group(1) if matched_type in ['equals', 'special_prefix', 'number_chinese', 'bracket_number'] else (match.group(2) if matched_type == 'prefix' else str(chapter_num))
                    if re.match(r'^[零一二三四五六七八九十百千万]+$', chapter_str):
                        print(f"[DEBUG] 章节识别 - 跳过格式不一致章节: 行{idx+1}, 文本: {repr(stripped)}, 之前使用阿拉伯数字格式")
                        continue
                if current_title and current_lines:
                    print(f"[DEBUG] 章节识别 - 添加章节: {current_title}, 内容行数: {len(current_lines)}")
                    chapters.append({'title': current_title, 'content': '\n'.join(current_lines)})
                if current_title is None and intro_lines:
                    print(f"[DEBUG] 章节识别 - 添加前言, 内容行数: {len(intro_lines)}")
                    chapters.insert(0, {'title': '前言', 'content': '\n'.join(intro_lines)})
                    intro_lines = []
                current_title = chapter_title
                last_chapter_num = chapter_num  # 更新上一个章节号
                if chapter_num is not None:
                    seen_chapter_nums.add(chapter_num)  # 记录已识别章节号
                    # 检查是否使用阿拉伯数字格式（章节号是纯数字）
                    uses_arabic_only = True  # 一旦识别到阿拉伯数字格式，后续只接受阿拉伯数字格式
                print(f"[DEBUG] 章节识别 - 设置当前章节: {chapter_title}, 章节号: {chapter_num}")
                current_lines = []
            elif current_title:
                current_lines.append(line)

        if current_title and current_lines:
            chapters.append({'title': current_title, 'content': '\n'.join(current_lines)})
        return chapters

    @staticmethod
    def _clean_chapter_content(content: str) -> str:
        """清理章节内容，移除末尾的单独括号等"""
        lines = content.split('\n')
        
        # 从末尾开始清理空行和单独的括号
        end_idx = len(lines)
        for i in range(len(lines)-1, -1, -1):
            line = lines[i].strip()
            if not line:
                continue
            # 检查是否是单独的括号
            if line in ['（', '(', '）', ')']:
                end_idx = i
            else:
                break
        
        # 移除从end_idx开始的内容
        cleaned_lines = lines[:end_idx]
        
        # 再次清理末尾的空行
        while cleaned_lines and not cleaned_lines[-1].strip():
            cleaned_lines.pop()
        
        return '\n'.join(cleaned_lines)
    
    @staticmethod
    def _chapter_to_html(content: str) -> str:
        # 先清理章节内容
        content = EPUBGenerator._clean_chapter_content(content)
        
        paragraphs = []
        current_paragraph = []
        for line in content.split('\n'):
            line = line.strip()
            if line:
                for old, new in [('&', '&amp;'), ('<', '&lt;'), ('>', '&gt;'), ('"', '&quot;'), ("'", '&#39;')]:
                    line = line.replace(old, new)
                current_paragraph.append(line)
            else:
                if current_paragraph:
                    paragraphs.append(f'<p>{" ".join(current_paragraph)}</p>')
                    current_paragraph = []
        if current_paragraph:
            paragraphs.append(f'<p>{" ".join(current_paragraph)}</p>')
        return '\n'.join(paragraphs)

    @staticmethod
    def txt_to_epub(txt_path: str, output_path: str = None, book_title: str = "", author: str = "",
                    cover_image: str = None, auto_search_cover: bool = False, cover_url: str = None) -> Optional[str]:
        """将TXT文件转换为EPUB"""
        if not EPUB_SUPPORT:
            print("❌ EPUB生成功能不可用，请先安装ebooklib库")
            return None

        try:
            content, encoding = EncodingDetector.read_file_with_auto_encoding(txt_path)
            chapters = EPUBGenerator._parse_chapters(content)

            if not chapters:
                chapters = [{'title': book_title if book_title else "正文", 'content': content}]

            if not book_title:
                book_title = EPUBGenerator._extract_title(content)
                if book_title:
                    print(f"   从内容中提取书名: {book_title}")
                else:
                    book_title = os.path.splitext(os.path.basename(txt_path))[0].replace('_epub_ready', '')

            if not author:
                author = EPUBGenerator._extract_author(content)
                if author:
                    print(f"   从内容中提取作者: {author}")
                else:
                    print("   ⚠️ 未能从文件中提取作者名")
                    author = input("   请输入作者名: ").strip() or "未知"

            book = epub.EpubBook()
            book.set_identifier(f"urn:uuid:{datetime.now().strftime('%Y%m%d%H%M%S')}")
            book.set_title(book_title)
            book.set_language('zh')
            book.add_author(author if author else "未知")

            actual_cover_path = cover_image
            if cover_url and not actual_cover_path:
                cover_dir = os.path.dirname(os.path.abspath(txt_path)) or '.'
                actual_cover_path = CoverDownloader.download_cover_from_url(cover_url, cover_dir)
            if auto_search_cover and not actual_cover_path:
                cover_dir = os.path.dirname(os.path.abspath(txt_path)) or '.'
                actual_cover_path = CoverDownloader.search_and_download_cover(book_title, author or "", cover_dir)

            if actual_cover_path and os.path.exists(actual_cover_path):
                try:
                    with open(actual_cover_path, 'rb') as f:
                        book.set_cover('cover.jpg', f.read())
                    print(f"✅ 添加封面: {actual_cover_path}")
                except Exception as e:
                    print(f"⚠️ 添加封面失败: {e}")

            spine = ['nav']
            toc = []
            for i, chapter in enumerate(chapters):
                html_content = EPUBGenerator._chapter_to_html(chapter['content'])
                chapter_title = chapter['title']
                epub_chapter = epub.EpubHtml(title=chapter_title, file_name=f'chapter_{i+1:03d}.xhtml', lang='zh')
                epub_chapter.content = f'''<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><meta charset="UTF-8" /><title>{chapter_title}</title>
<style type="text/css">
body {{ font-family: "SimSun", "STSong", "Noto Serif CJK SC", serif; font-size: 1em; line-height: 1.8; margin: 1em; text-align: justify; }}
h1 {{ text-align: center; font-size: 1.5em; margin-bottom: 1.5em; padding-bottom: 0.5em; border-bottom: 1px solid #ccc; }}
p {{ text-indent: 2em; margin: 0.5em 0; }}
</style>
</head>
<body><h1>{chapter_title}</h1>{html_content}</body></html>'''
                book.add_item(epub_chapter)
                spine.append(epub_chapter)
                toc.append(epub.Link(f'chapter_{i+1:03d}.xhtml', chapter_title, f'ch{i+1}'))

            book.add_item(epub.EpubNcx())
            book.add_item(epub.EpubNav())
            book.spine = spine
            book.toc = tuple(toc)

            if output_path is None:
                safe_book_title = re.sub(r'[<>:"/\\|?*]', '_', book_title)
                output_dir = os.path.dirname(os.path.abspath(txt_path)) or '.'
                output_path = os.path.join(output_dir, f"{safe_book_title}.epub")

            epub.write_epub(output_path, book, {})

            last_ch_title = chapters[-1]['title'] if chapters else '无'
            if last_ch_title.startswith('番外'):
                last_ch_title = last_ch_title.replace('：', ' ')
            elif not last_ch_title.startswith('第'):
                last_ch_title = f"第{last_ch_title}"

            print(f"✅ EPUB文件生成成功: {output_path}")
            print(f"   书名: {book_title}")
            print(f"   作者: {author}")
            print(f"   章节数: {len(chapters)} 章")
            print(f"   最后一章: {last_ch_title}")
            print(f"   文件大小: {DirectoryDisplay.format_size(os.path.getsize(output_path))}")

            if actual_cover_path and os.path.exists(actual_cover_path):
                try:
                    os.remove(actual_cover_path)
                    print(f"🗑️ 已清理临时封面: {actual_cover_path}")
                except Exception as e:
                    print(f"⚠️ 清理封面失败: {e}")

            return output_path

        except Exception as e:
            print(f"❌ EPUB生成失败: {str(e)}")
            return None
