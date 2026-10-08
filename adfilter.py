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
        r'|\.(com|cn|net|cc|org|io|xyz|top)([/?#\s]|$)'
        # 混淆域名：xxxx.com / xxxx·com / xxxx点com
        r'|[A-Za-z0-9Ａ-Ｚａ-ｚ０-９]{3,}[.·．点](com|net|cc|org|me|xyz)(?!\w)',
        re.I,
    )

    _PLATFORM_RE = re.compile(
        r'(笔趣阁|起点|晋江|纵横|17k|腾讯|阅文|番茄|米读|七猫|掌阅|多看|po18|jjwxc'
        r'|笔力阅读|阅笔小说|润文网|书趣网|新笔趣阁|顶点小说|飞卢小说|爱好中文)'
        r'.{0,6}(小说|阅读|文学|网|app)',
        re.I,
    )

    # 高置信度正则模式（不可被用户 hard_kw 参数覆盖）
    _HARD_RE = [
        re.compile(r'想看更多.{0,20}(小说|访问|请)',          re.I),
        re.compile(r'最新章节.{0,15}(更新|请到|请访)',         re.I),
        re.compile(r'更多好看的(文章|小说)',                   re.I),
        re.compile(r'求(月票|推荐票|鲜花|评价票)',             re.I),
        re.compile(r'(本书|全书|全文).{0,6}(首发|发布).{0,10}(网|站|阁|楼)',  re.I),
        re.compile(r'(欢迎|请).{0,4}(访问|关注).{0,10}(网|站|com|net)', re.I),
    ]

    _HARD_KW = [
        '下载app', '下载APP', 'APP下载', 'app下载',
        '手机用户请', '最新章节请访问', '最新章节请到', '最新更新地址',
        'txt全集', '电子书下载', '本书来自', '本作品来自', '首发于',
        '扫码', '二维码', 'qq群', 'QQ群', '公众号', '关注微信', '微信扫',
        '阅读网', '小说网', '全文阅读', '免费全文', '书城',
        '关注.*获取', '加入书架',
        '内容版权归', '不做任何负责', '免费日更',
        # 作者拉票（从 kasaki AD_PRESETS 补充）
        '求月票', '求推荐票', '求打赏', '求鲜花', '求评价票',
        # 站点推广
        '欢迎访问', '在线阅读全文', '全本TXT下载', '更多好书', '手机阅读',
        # 联系方式
        '微信群', '微信号', '书友群', '电报群',
    ]

    _SOFT_KW = ['书友', '更新最快', '收藏推荐', '关注', '手机看书', '下载', '求订阅']

    @classmethod
    def _score(cls, line: str, near_boundary: bool = False,
               hard_kw=None, soft_kw=None) -> float:
        s = line.strip()
        if not s:
            return 0.0

        _hard = hard_kw if hard_kw is not None else cls._HARD_KW
        _soft = soft_kw if soft_kw is not None else cls._SOFT_KW

        score = 0.0

        if cls._URL_RE.search(s):
            score = max(score, 0.88)
        if cls._PLATFORM_RE.search(s):
            score = max(score, 0.82)

        # 高置信度正则（始终检查，不受 hard_kw 覆盖影响）
        for rx in cls._HARD_RE:
            if rx.search(s):
                score = max(score, 0.85)
                break

        sl = s.lower()
        for kw in _hard:
            if kw.lower() in sl:
                score = max(score, 0.78)
                break
        for kw in _soft:
            if kw in s:
                score += 0.18

        if len(s) < 20:
            score += 0.08
        if near_boundary:
            score = min(score * 1.4, 1.0)

        return min(score, 1.0)

    @classmethod
    def scan_content(
        cls,
        content: str,
        threshold: float = 0.68,
        head_tail_lines: int = 30,
        hard_kw=None,
        soft_kw=None,
    ) -> List[dict]:
        """扫描广告内容（不删除），返回可疑行信息列表。

        Returns:
            [{'line_num': int, 'score': float, 'text': str}]
        """
        lines = content.split('\n')
        n = len(lines)
        result = []
        for i, line in enumerate(lines):
            sc = cls._score(
                line,
                near_boundary=(i < head_tail_lines or i >= n - head_tail_lines),
                hard_kw=hard_kw, soft_kw=soft_kw,
            )
            if sc >= threshold:
                result.append({'line_num': i + 1, 'score': round(sc, 3), 'text': line.strip()})
        return result

    @classmethod
    def filter_content(
        cls,
        content: str,
        threshold: float = 0.68,
        head_tail_lines: int = 30,
        hard_kw=None,
        soft_kw=None,
    ) -> Tuple[str, int]:
        """过滤广告内容。

        Args:
            content: 原始文本
            threshold: 单行广告分阈值（0–1）
            head_tail_lines: 文件首尾各多少行视为「边界区域」加权
            hard_kw: 强匹配关键词列表（覆盖默认）
            soft_kw: 软匹配关键词列表（覆盖默认）

        Returns:
            (filtered_content, removed_line_count)
        """
        lines = content.split('\n')
        n = len(lines)
        scores = [
            cls._score(line,
                       near_boundary=(i < head_tail_lines or i >= n - head_tail_lines),
                       hard_kw=hard_kw, soft_kw=soft_kw)
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

        # 保留章节标题行（防止误删）；若标题部分含广告则原地清除
        _CHAPTER_TITLE_RE = re.compile(
            r'^(第[零一二三四五六七八九十百千万两\d]+[章卷节回]'
            r'|番外[零一二三四五六七八九十百千万两\d]*'
            r'|楔子|序章|序言|终章|完结章|尾声|后记'
            r')\s*(.*?)$'
        )
        # 去除 CJK 字符间的空格（用于反混淆广告）
        _CJK_SP_RE = re.compile(
            r'(?<=[一-鿿])\s+(?=[一-鿿])'
            r'|(?<=[A-Za-z0-9])\s+(?=[一-鿿])'
            r'|(?<=[一-鿿])\s+(?=[A-Za-z0-9])'
        )
        for i, line in enumerate(lines):
            m = _CHAPTER_TITLE_RE.match(line.strip())
            if not m:
                continue
            removed.discard(i)
            title_part = m.group(2).strip()
            if title_part:
                deobs = _CJK_SP_RE.sub('', title_part)
                if cls._score(deobs, hard_kw=hard_kw, soft_kw=soft_kw) >= threshold or len(deobs) > 30:
                    lines[i] = m.group(1)  # 只保留章节号，去掉广告标题

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
