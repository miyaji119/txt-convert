"""广告内容过滤模块

在 convert_for_easypub() 读文件后、ChapterAnalyzer 之前运行。
对每行打广告概率分（0–1），超过阈值或形成连续广告块的行被移除。
"""

import re
from typing import List, Set, Tuple


class AdFilter:

    _URL_RE = re.compile(
        r'https?://'
        r'|(?<!\w)www\.'
        r'|\.(com|cn|net|cc|org|io|xyz|top)([/?#\s]|$)',
        re.I,
    )

    _PLATFORM_RE = re.compile(
        r'(笔趣阁|起点|晋江|纵横|17k|腾讯|阅文|番茄|米读|七猫|掌阅|多看|po18|jjwxc)'
        r'.{0,6}(小说|阅读|文学|网|app)',
        re.I,
    )

    _HARD_KW = [
        '下载app', '下载APP', 'APP下载', 'app下载',
        '手机用户请', '最新章节请访问', '最新章节请到', '最新更新地址',
        'txt全集', '电子书下载', '本书来自', '首发于',
        '扫码', '二维码', 'qq群', 'QQ群', '公众号', '关注微信', '微信扫',
        '阅读网', '小说网', '全文阅读', '免费全文', '书城',
        '关注.*获取', '加入书架',
    ]

    _SOFT_KW = ['书友', '更新最快', '收藏推荐', '关注', '手机看书', '下载']

    @classmethod
    def _score(cls, line: str, near_boundary: bool = False) -> float:
        s = line.strip()
        if not s:
            return 0.0

        score = 0.0

        if cls._URL_RE.search(s):
            score = max(score, 0.88)
        if cls._PLATFORM_RE.search(s):
            score = max(score, 0.82)

        sl = s.lower()
        for kw in cls._HARD_KW:
            if kw.lower() in sl:
                score = max(score, 0.78)
                break
        for kw in cls._SOFT_KW:
            if kw in s:
                score += 0.18

        if len(s) < 20:
            score += 0.08
        if near_boundary:
            score = min(score * 1.4, 1.0)

        return min(score, 1.0)

    @classmethod
    def filter_content(
        cls,
        content: str,
        threshold: float = 0.68,
        head_tail_lines: int = 30,
    ) -> Tuple[str, int]:
        """过滤广告内容。

        Args:
            content: 原始文本
            threshold: 单行广告分阈值（0–1）
            head_tail_lines: 文件首尾各多少行视为「边界区域」加权

        Returns:
            (filtered_content, removed_line_count)
        """
        lines = content.split('\n')
        n = len(lines)
        scores = [
            cls._score(line, near_boundary=(i < head_tail_lines or i >= n - head_tail_lines))
            for i, line in enumerate(lines)
        ]

        removed: Set[int] = set()

        # 单行过滤
        for i, sc in enumerate(scores):
            if sc >= threshold:
                removed.add(i)

        # 连续广告块：≥3 行分值均 ≥ 0.45 → 整块删除
        run_start = None
        for i, sc in enumerate(scores):
            if sc >= 0.45:
                if run_start is None:
                    run_start = i
            else:
                if run_start is not None and (i - run_start) >= 3:
                    removed.update(range(run_start, i))
                run_start = None
        if run_start is not None and (n - run_start) >= 3:
            removed.update(range(run_start, n))

        # 保留章节标题行（防止误删）
        _CHAPTER_RE = re.compile(r'^第[零一二三四五六七八九十百千万\d]+[章卷节回]')
        for i, line in enumerate(lines):
            if _CHAPTER_RE.match(line.strip()):
                removed.discard(i)

        filtered = [line for i, line in enumerate(lines) if i not in removed]

        # 合并多余空行（最多保留 2 个连续空行）
        cleaned: List[str] = []
        blanks = 0
        for line in filtered:
            if not line.strip():
                blanks += 1
                if blanks <= 2:
                    cleaned.append(line)
            else:
                blanks = 0
                cleaned.append(line)

        return '\n'.join(cleaned), len(removed)
