"""跨章节内容一致性检测

检测相邻章节的人名/地名实体是否完全不重叠，用于识别多部小说合并成一个文件的情况。
在 convert_for_easypub() 中 ChapterAnalyzer 之后、optimize_for_epub() 之前调用。
"""

import re
from typing import Dict, List, Optional, Set, Tuple


class ConsistencyChecker:

    # 人名：动作动词前缀（中文姓名 2-3 字，不抓更长的句子片段）
    # 注：孤立的「道」必须后跟引号/冒号才算对话用法，避免把「知道」「明道」误匹配
    _ACTION_RE = re.compile(
        r'([一-龥]{2,3})'
        r'[的地]?'
        r'(?:说道?|问道?|答道?|叫道?|喊道?|笑道?|怒道?|低声道?'
        r'|沉声道?|冷道?|轻声道?|哼道?|叹道?|嗤道?'
        r'|道(?=[：:「『""」]))',
    )
    # 人名：引号/冒号前缀
    _QUOTE_RE = re.compile(r'([一-龥]{2,3})[：:「『""]\s*[一-龥]')

    # 地名：常见地点后缀（排除「道」避免误抓对话动词）
    _PLACE_RE = re.compile(
        r'([一-龥]{1,4}'
        r'(?:城|国|山|河|殿|宫|门|村|镇|县|府|阁|岛|峰|谷|林|原|界|域|洞|湖|海|宗|派|堂))',
    )

    # 以这些字开头的捕获结果不可能是人名/地名，直接过滤
    _BAD_STARTS = frozenset(
        '不没别非未也还又都而且但因和与或是为有在到从对向将让被把'
        '他她它这那什么谁某各每几多少可真很更最已就才只也还都再'
        '虽然虽然由于因此所以只是只有只要其实其中其他'
        '一些了'       # 数词"一"、量词"些"、助词"了"不会开头人名
        '们偶'         # "们"是复数后缀，"偶"常为副词"偶尔"，均不起头人名
    )

    # 含有这些字的捕获结果是语法短语而非实体（了=完成体，的=领属标记）
    _PHRASE_CHARS = frozenset('了的')

    @classmethod
    def _extract_entities(cls, text: str) -> Set[str]:
        entities: Set[str] = set()
        for pat in (cls._ACTION_RE, cls._QUOTE_RE):
            for m in pat.finditer(text):
                name = m.group(1).strip()
                if (len(name) >= 2
                        and name[0] not in cls._BAD_STARTS
                        and not any(c in name for c in cls._PHRASE_CHARS)):
                    entities.add(name)
        for m in cls._PLACE_RE.finditer(text):
            place = m.group(1).strip()
            if (len(place) >= 2
                    and place[0] not in cls._BAD_STARTS
                    and not any(c in place for c in cls._PHRASE_CHARS)):
                entities.add(place)
        return entities

    @classmethod
    def check(
        cls,
        content: str,
        chapter_structure: dict,
        window: int = 3,
        confirm_n: int = 3,
        min_entities: int = 3,
    ) -> Optional[dict]:
        """检查章节间内容一致性。

        Args:
            content:           原始文本
            chapter_structure: ChapterAnalyzer.analyze_chapter_structure() 的返回值
            window:            保留参数（不再使用固定窗口；改为累积池，更健壮）
            confirm_n:         连续 N 章与前段零重叠才确认为不一致
            min_entities:      两侧实体数均 < 该值时跳过比较（章节太短）

        Returns:
            None 表示无问题；否则返回描述不一致位置的 dict：
            {
              'split_after': chapter_index,   # 在第几章之后发生断裂（0-based）
              'left_sample': [...],            # 前段实体示例
              'right_sample': [...],           # 后段实体示例
              'left_title': str,
              'right_title': str,
            }
        """
        chapters = chapter_structure.get('chapters', [])
        if len(chapters) < confirm_n + 2:
            return None

        lines = content.split('\n')

        def chapter_text(ch: dict) -> str:
            start = ch['start_line'] - 1
            end = ch['end_line']
            return '\n'.join(lines[start:end])

        # 预提取每章实体集
        entity_sets: List[Set[str]] = [
            cls._extract_entities(chapter_text(ch)) for ch in chapters
        ]

        # 使用累积实体池（含所有已处理章节）而非固定窗口
        # 好处：番外章节换了配角也不会误判，因为该配角往往在正文中出现过
        cumulative_pool: Set[str] = set()
        zero_streak = 0
        streak_start_idx = -1

        for i, current in enumerate(entity_sets):
            if i == 0:
                cumulative_pool |= current
                continue

            if len(cumulative_pool) < min_entities or len(current) < min_entities:
                zero_streak = 0
                cumulative_pool |= current
                continue

            overlap = cumulative_pool & current
            if not overlap:
                if zero_streak == 0:
                    streak_start_idx = i
                zero_streak += 1
                if zero_streak >= confirm_n:
                    split_after = streak_start_idx - 1
                    left_sample = sorted(cumulative_pool)[:6]
                    right_sample = sorted(current)[:6]
                    return {
                        'split_after': split_after,
                        'left_title':  chapters[split_after]['title'],
                        'right_title': chapters[streak_start_idx]['title'],
                        'left_sample': left_sample,
                        'right_sample': right_sample,
                    }
            else:
                zero_streak = 0

            cumulative_pool |= current

        return None


class ContentMismatchError(Exception):
    """多书合并文件检测到后抛出，携带诊断信息。"""
    def __init__(self, info: dict):
        self.info = info
        left  = '、'.join(info['left_sample'])
        right = '、'.join(info['right_sample'])
        msg = (
            f"\n⛔  检测到内容不连续\n"
            f"   断裂位置：「{info['left_title']}」→「{info['right_title']}」\n"
            f"   前段出现：{left}\n"
            f"   后段出现：{right}\n"
            f"   疑似多部小说合并文件，已停止处理。\n"
            f"   建议在「{info['left_title']}」末尾处手动拆分文件后重新运行。\n"
            f"   如需强制继续，请在调用时传入 ignore_mismatch=True。"
        )
        super().__init__(msg)
