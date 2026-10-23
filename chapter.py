"""章节分析模块"""

import bisect
import re
from collections import Counter, defaultdict
from typing import Dict

from chapter_config import ChapterConfig


class ChapterAnalyzer:
    """章节分析器"""

    # 标准章节模式配置: ptype -> (章节号group, 标题group, 单位, 是否中文数字)
    _STANDARD = {
        'equals':            (1, 2, '章', True),
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
        'custom':            (1, 2, '章', False),
        'no_di_chapter':     (1, 2, '章', True),
        'chinese_part':      (1, 2, '部', True),
    }

    _AUTHOR_NOTE_PAT = re.compile(
        r'^[\s=*]*(作者有话要?说?|作者说|作话|作者留言)[\s:：。=*]{0,10}$'
    )
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
        """中文数字转阿拉伯数字，支持百千万两"""
        if cn.isdigit():
            return int(cn)
        cn_val = {'零': 0, '〇': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
                  '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
        unit_val = {'十': 10, '百': 100, '千': 1000, '万': 10000}
        result = 0
        temp = 0
        for char in cn:
            if char in cn_val:
                temp = cn_val[char]
            elif char in unit_val:
                unit = unit_val[char]
                if unit == 10000:
                    result = (result + temp) * unit
                    temp = 0
                else:
                    if temp == 0:
                        temp = 1  # 「十」起头时隐含「一」，如十五 = 15
                    result += temp * unit
                    temp = 0
        return result + temp

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
            title_part = (chapter_match.group(title_grp) or "").strip() if title_grp else ""
            # 标题以句号结尾，或以叹号/问号结尾且较长 → 疑似正文混入标题行
            if title_part and (
                title_part[-1] == '。'
                or (title_part[-1] in '！？' and len(title_part) >= 8)
            ):
                title_part = ""
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

        if ptype == 'fanwai_general':
            sub = chapter_match.group(1).strip()
            return 9990, f"番外 {sub}" if sub else "番外"

        if ptype == 'special_chapter':
            _SPECIAL_NUMS = {
                '序章': 1, '序言': 2,
                '完结章': 9991, '终章': 9992,
                '尾声': 9993, '后记': 9994, '后序': 9995,
            }
            name = chapter_match.group(1).strip()
            sub = chapter_match.group(2).strip() if chapter_match.lastindex >= 2 else ''
            num = _SPECIAL_NUMS.get(name, 9990)
            return num, f"{name} {sub}" if sub else name

        if ptype == 'chapter_part':
            num = ChapterAnalyzer.normalize_chapter_num(chapter_match.group(1))
            title = chapter_match.group(2).strip()
            suffix = chapter_match.group(3).strip()
            unit_str = f"第{num}章"
            title_full = f"{title}（{suffix}）" if title else f"（{suffix}）"
            return num, f"{unit_str} {title_full}"

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
        if ptype in ('fanwai', 'fanwai_general') and chapter_match.lastindex >= 1:
            return chapter_match.group(1).strip()
        if ptype == 'special_chapter' and chapter_match.lastindex >= 2:
            return chapter_match.group(2).strip()
        return ""

    # ------------------------------------------------------------------
    # 章节结构分析
    # ------------------------------------------------------------------
    @staticmethod
    def analyze_chapter_structure(content: str, config_name: str = 'default',
                                  extra_patterns: list = None) -> Dict:
        """分析章节结构"""
        config = ChapterConfig(config_name)
        chapter_patterns = config.CHAPTER_PATTERNS
        if extra_patterns:
            chapter_patterns = [(p, 'custom') for p in extra_patterns] + chapter_patterns
        filter_rules = config.FILTER_RULES

        lines = content.split('\n')

        # ── 第一遍：收集所有候选章节行（不去重），记录行号、解析结果 ──────────────
        candidates = []  # list of (line_idx, chapter_num, chapter_title)
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            for pattern, ptype in chapter_patterns:
                chapter_match = re.match(pattern, line_stripped)
                if not chapter_match:
                    continue
                title_part = ChapterAnalyzer._get_title_part(ptype, chapter_match)
                if any(f['func'](title_part=title_part, ptype=ptype,
                                 chapter_match=chapter_match,
                                 seen_chapter_nums=set())
                       for f in filter_rules):
                    break
                chapter_num, chapter_title = ChapterAnalyzer.parse_chapter_title(
                    line_stripped, ptype, chapter_match)
                if chapter_num is None:
                    break
                candidates.append((i, chapter_num, chapter_title or f"第{chapter_num}章"))
                break

        # ── 第二遍：过滤掉落在「作者有话要说」区域内的候选 ─────────────────────
        # 注释区域定义：注释起始行（exclusive）到下一个候选章节行（exclusive）之间。
        # 候选章节行本身不在区域内——它是注释区域的终点，不应被过滤。
        candidate_positions = sorted(c[0] for c in candidates)
        note_starts = [
            k for k, line in enumerate(lines)
            if ChapterAnalyzer._AUTHOR_NOTE_PAT.match(line.strip())
        ]
        note_regions = []
        for ns in note_starts:
            pos = bisect.bisect_right(candidate_positions, ns)
            end = candidate_positions[pos] if pos < len(candidate_positions) else len(lines)
            note_regions.append((ns, end))

        def _in_note_region(idx: int) -> bool:
            return any(start < idx < end for start, end in note_regions)

        real_candidates = [(i, cn, ct) for (i, cn, ct) in candidates
                           if not _in_note_region(i)]

        # ── 第三遍：去重并计算每章的 end_line ────────────────────────────────
        real_starts = [c[0] for c in real_candidates]  # 用于 bisect 的有效章节起始行
        chapters = []
        seen_chapter_nums = set()
        for (i, chapter_num, chapter_title) in real_candidates:
            if chapter_num in seen_chapter_nums:
                continue
            seen_chapter_nums.add(chapter_num)

            pos = bisect.bisect_right(real_starts, i)
            end_line = (real_starts[pos] - 1
                        if pos < len(real_starts)
                        else len(lines) - 1)

            char_count = sum(len(lines[k].strip())
                             for k in range(i, min(end_line + 1, len(lines))))
            chapters.append({
                'number': chapter_num,
                'title': chapter_title,
                'start_line': i + 1,
                'end_line': end_line + 1,
                'line_count': end_line - i,
                'char_count': char_count
            })

        return {
            'total_chapters': len(chapters),
            'total_lines': len(lines),
            'total_chars': len(content),
            'chapters': chapters
        }

    # ------------------------------------------------------------------
    # 章节编号修复
    # ------------------------------------------------------------------
    # 匹配"第X章/节/回/卷 标题"，X 可为中文或阿拉伯数字
    _BROKEN_NUM_RE = re.compile(
        r'^(第[零一二三四五六七八九十百千万两\d]+([章节回卷]))[：:，,\s]*(.*?)$'
    )

    @staticmethod
    def fix_broken_numbering(content: str) -> str:
        """检测并修正批量重复的章节编号。

        当同一章节编号前缀（如"第一章"）出现 ≥3 次、占全书章节 ≥30%，
        且这些重复行拥有多个不同标题时，视为编号错误，
        按出现顺序统一改写为第1章、第2章……
        """
        lines = content.split('\n')
        # (行下标, 完整前缀如"第一章", 单位字如"章", 后续标题文字)
        ch_lines: list = []
        for i, line in enumerate(lines):
            m = ChapterAnalyzer._BROKEN_NUM_RE.match(line.strip())
            if m:
                ch_lines.append((i, m.group(1), m.group(2), m.group(3).strip()))

        if len(ch_lines) < 3:
            return content

        prefix_counts: Counter = Counter(c[1] for c in ch_lines)
        most_common_prefix, most_common_count = prefix_counts.most_common(1)[0]

        # 条件1：同一前缀出现 ≥3 次，且占全部章节 ≥30%
        if most_common_count < 3 or most_common_count < len(ch_lines) * 0.3:
            return content

        # 条件2：重复编号下的标题各不相同（真实的分章，而非抓取断点重复）
        prefix_to_titles: defaultdict = defaultdict(set)
        for _i, prefix, _unit, title_body in ch_lines:
            prefix_to_titles[prefix].add(title_body)
        if len(prefix_to_titles[most_common_prefix]) <= 1:
            return content  # 同号同题 → 真实重复章节，交由 _merge_duplicate_chapters 处理

        print(f"   ⚠️ 检测到重复章节编号（{most_common_prefix} 出现 {most_common_count} 次），"
              f"自动修正为顺序编号")

        new_lines = list(lines)
        for seq, (i, _prefix, unit_char, title_body) in enumerate(ch_lines, 1):
            new_prefix = f"第{seq}{unit_char}"
            new_title = f"{new_prefix} {title_body}" if title_body else new_prefix
            orig = lines[i]
            leading = len(orig) - len(orig.lstrip())
            new_lines[i] = orig[:leading] + new_title

        return '\n'.join(new_lines)