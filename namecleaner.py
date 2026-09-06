"""独立行水印识别与清理

只处理有空行包围的独立短行（2–8 汉字）且不在角色名单中的行。
高置信度，不触碰段落内容。

集成点：convert_for_easypub() 中 AdFilter 之后调用。
"""

import re
from typing import List, Set, Tuple


class NameCleaner:

    # 提取角色名：动作动词前的主语
    _ACTION_RE = re.compile(
        r'([一-龥]{1,6})'
        r'[的地]?'
        r'(?:说道?|问道?|答道?|道|叫道?|喊道?|笑道?|怒道?|低声道?'
        r'|沉声道?|冷道?|轻声道?|哼道?|叹道?|嗤道?)',
    )
    # 提取角色名：引号/冒号前的称呼
    _QUOTE_RE = re.compile(r'([一-龥]{1,6})[：:「『""]\s*[一-龥]')

    # 章节/卷标题豁免
    _CHAPTER_RE = re.compile(r'^第[零一二三四五六七八九十百千万\d]+[章卷节回]')

    # 独立行候选：纯汉字 2–8 字（允许中点·作为名字分隔）
    _CAND_RE = re.compile(r'^[一-龥·•]{2,8}$')

    # -----------------------------------------------------------------
    @classmethod
    def _build_roster(cls, lines: List[str]) -> Set[str]:
        """从全文提取合法角色名集合。"""
        roster: Set[str] = set()
        text = '\n'.join(lines)
        for pat in (cls._ACTION_RE, cls._QUOTE_RE):
            for m in pat.finditer(text):
                name = m.group(1).strip()
                if 1 < len(name) <= 6:
                    roster.add(name)
                    # 同时加入名字的首 2 字和尾 2 字，覆盖带称谓的变体
                    if len(name) > 2:
                        roster.add(name[:2])
                        roster.add(name[-2:])
        return roster

    @classmethod
    def _standalone(cls, lines: List[str], i: int) -> bool:
        """判断第 i 行是否为独立行（前后是空行或文件边界）。"""
        prev_empty = (i == 0) or (not lines[i - 1].strip())
        next_empty = (i == len(lines) - 1) or (not lines[i + 1].strip())
        return prev_empty and next_empty

    @classmethod
    def _in_roster(cls, name: str, roster: Set[str]) -> bool:
        """宽松匹配：名字本身、或名字是某角色名的子串/超串。"""
        if name in roster:
            return True
        for r in roster:
            if len(r) >= 2 and (name in r or r in name):
                return True
        return False

    # -----------------------------------------------------------------
    @classmethod
    def clean(
        cls,
        content: str,
        min_roster: int = 3,
    ) -> Tuple[str, int, List[str]]:
        """识别并删除独立行水印。

        Args:
            content:     原始文本
            min_roster:  角色名单最小数量；太少说明文本太短，跳过

        Returns:
            (cleaned_content, removed_count, removed_name_list)
        """
        lines = content.split('\n')
        roster = cls._build_roster(lines)

        if len(roster) < min_roster:
            return content, 0, []

        keep = [True] * len(lines)
        removed: List[str] = []

        for i, line in enumerate(lines):
            s = line.strip()
            if not s:
                continue
            if not cls._CAND_RE.match(s):
                continue
            if cls._CHAPTER_RE.match(s):
                continue
            if not cls._standalone(lines, i):
                continue
            if not cls._in_roster(s, roster):
                keep[i] = False
                removed.append(s)

        cleaned = [ln for i, ln in enumerate(lines) if keep[i]]

        # 消除删行后出现的连续多余空行（保留最多 2 个）
        result: List[str] = []
        blanks = 0
        for ln in cleaned:
            if not ln.strip():
                blanks += 1
                if blanks <= 2:
                    result.append(ln)
            else:
                blanks = 0
                result.append(ln)

        return '\n'.join(result), len(removed), removed
