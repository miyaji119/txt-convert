"""跨章节内容一致性检测

检测相邻章节的人名/地名实体是否完全不重叠，用于识别多部小说合并成一个文件的情况。
在 convert_for_easypub() 中 ChapterAnalyzer 之后、optimize_for_epub() 之前调用。
"""

import re
from typing import Dict, List, Optional, Set, Tuple


class ConsistencyChecker:

    # 人名：动作动词前缀（中文姓名 2-3 字，不抓更长的句子片段）
    _ACTION_RE = re.compile(
        r'([一-龥]{2,3})'
        r'[的地]?'
        r'(?:说道?|问道?|答道?|道|叫道?|喊道?|笑道?|怒道?|低声道?'
        r'|沉声道?|冷道?|轻声道?|哼道?|叹道?|嗤道?)',
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
    )

    @classmethod
    def _extract_entities(cls, text: str) -> Set[str]:
        entities: Set[str] = set()
        for pat in (cls._ACTION_RE, cls._QUOTE_RE):
            for m in pat.finditer(text):
                name = m.group(1).strip()
                if len(name) >= 2 and name[0] not in cls._BAD_STARTS:
                    entities.add(name)
        for m in cls._PLACE_RE.finditer(text):
            place = m.group(1).strip()
            if len(place) >= 2 and place[0] not in cls._BAD_STARTS:
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
            window:            用前 N 章的实体池代表「前段世界」
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
        if len(chapters) < window + confirm_n + 1:
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

        zero_streak = 0
        streak_start_idx = -1

        for i in range(window, len(chapters)):
            # 前段实体池
            left_pool: Set[str] = set()
            for j in range(max(0, i - window), i):
                left_pool |= entity_sets[j]

            current = entity_sets[i]

            if len(left_pool) < min_entities or len(current) < min_entities:
                zero_streak = 0
                continue

            overlap = left_pool & current
            if not overlap:
                if zero_streak == 0:
                    streak_start_idx = i
                zero_streak += 1
                if zero_streak >= confirm_n:
                    split_after = streak_start_idx - 1
                    left_sample = sorted(left_pool)[:6]
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
