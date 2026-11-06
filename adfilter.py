"""广告内容过滤模块

在 convert_for_easypub() 读文件后、ChapterAnalyzer 之前运行。
对每行打广告概率分（0–1），超过阈值或形成连续广告块的行被移除。
"""

import html as _html
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

    # 明确盗版站名：无需后缀即命中（false positive 风险极低）
    _PIRACY_RE = re.compile(
        r'(笔趣阁|新笔趣阁|笔力阅读|阅笔小说|润文网|书趣网|顶点小说|飞卢小说'
        r'|爱好中文|biliyd|yoabc)',
        re.I,
    )
    # 平台名 + 关键后缀（避免误匹配正文中的地名/公司名）
    _PLATFORM_RE = re.compile(
        r'(起点|晋江|纵横|17k|腾讯|阅文|番茄|米读|七猫|掌阅|多看|po18|jjwxc)'
        r'.{0,6}(小说|阅读|文学|网|app)',
        re.I,
    )

    # 行内夹带广告片段：正文末尾追加的"记住网址xxx.cc"等，需截取而非整行删除
    _INLINE_AD_FRAG_RE = re.compile(
        r'[\s,，]*'
        r'(?:记住(?:本站|本书|网址|网站|域名|地址)?|'
        r'最(?:新|快)(?:更新)?(?:地址|网址|网站)?(?:请?(?:到|访问))?|'
        r'请(?:记住|访问|收藏|到)|'
        r'本(?:书|章|文)(?:首发|来自|更新)(?:于|在)?)'
        r'[\s,，。：:]*'
        r'[A-Za-z0-9]+(?:[.][A-Za-z0-9]+){1,3}'
        r'[^\n,，。！？]{0,30}',
        re.I,
    )

    # 行首社交账号推广前缀：{…}微博Cc栗~{ 正文... 等
    # 账号名必须以 @/＠ 或 ASCII 字母/数字开头，避免误匹配正文中的"微博"
    _LEADING_AD_FRAG_RE = re.compile(
        r'^[^一-鿿]{0,15}'          # 行首装饰符（非汉字：{}~* 空格等）
        r'(?:微博|微信|公众号|抖音|[Bb]站|bilibili)\s*'
        r'(?:[@＠]\S{1,25}|[A-Za-z0-9]\S{0,24})'  # 账号名（必须以 @/英文/数字开头）
        r'[^一-鿿\s]{0,8}'          # 尾部装饰符
        r'\s+',
        re.I,
    )

    # 不可见字符、私用区码位等乱码噪声（几乎零误判，直接截除）
    _NOISE_RE = re.compile(
        r'[\u00a0\u00ad\u115f\u1160\u17b4\u17b5'  # NBSP / soft-hyphen / Hangul/Khmer filler
        r'\u180b-\u180e'    # Mongolian format chars
        r'\u200b-\u200f'    # zero-width sp / non-joiner / joiner / LRM / RLM
        r'\u202a-\u202e'    # 双向文本方向控制符
        r'\u2060-\u2064'    # word joiner 等
        r'\u206a-\u206f'    # 已废弃格式控制符
        r'\ufeff]+'         # BOM / ZWNBSP
        r'|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+'  # C0 控制符（保留 \t \n）
        r'|[\ue000-\uf8ff]+'   # BMP 私用区（PUA，平台水印常用）
        r'|[\ufff9-\uffff]+'   # 行间注释符 + Specials
    )
    # HTML 标签残留（爬虫未完全剥离标记）
    _HTML_TAG_RE = re.compile(
        r'</?(?:br|p|div|span|font|b|i|u|s|em|strong|a|ul|ol|li'
        r'|h[1-6]|table|tr|td|th|blockquote|pre|code)\b[^>]{0,80}/?>',
        re.I,
    )

    # 高置信度正则模式（不可被用户 hard_kw 参数覆盖）
    _HARD_RE = [
        re.compile(r'想看更多.{0,20}(小说|访问|请)',          re.I),
        re.compile(r'最新章节.{0,15}(更新|请到|请访)',         re.I),
        re.compile(r'更多好看的(文章|小说)',                   re.I),
        re.compile(r'最新最全的小说',                          re.I),
        re.compile(r'求(月票|推荐票|鲜花|评价票)',             re.I),
        re.compile(r'(本书|全书|全文).{0,6}(首发|发布).{0,10}(网|站|阁|楼)',  re.I),
        re.compile(r'(欢迎|请).{0,4}(访问|关注).{0,10}(网|站|com|net)', re.I),
    ]

    _HARD_KW = [
        '下载app', '下载APP', 'APP下载', 'app下载',
        '手机用户请', '最新章节请访问', '最新章节请到', '最新更新地址',
        'txt全集', '电子书下载', '本书来自', '本作品来自', '首发于', '本书首发',
        '扫码', '二维码', 'qq群', 'QQ群', '公众号', '关注微信', '微信扫',
        '阅读网', '小说网', '全文阅读', '免费全文', '书城',
        '关注.*获取', '加入书架',
        '内容版权归', '不做任何负责', '免费日更',
        # 作者拉票
        '求月票', '求推荐票', '求打赏', '求鲜花', '求评价票', '求收藏', '求订阅',
        # 站点推广
        '欢迎访问', '在线阅读全文', '全本TXT下载', '更多好书', '手机阅读',
        # 联系方式
        '微信群', '微信号', '书友群', '电报群',
    ]

    _SOFT_KW = ['书友', '更新最快', '收藏推荐', '关注', '手机看书', '下载', '求订阅']

    @staticmethod
    def _fw_normalize(s: str) -> str:
        """全角字母/数字/标点 → 半角 ASCII，用于反混淆 URL 检测。

        字符长度不变（1:1 映射），位置偏移在原始串中仍然有效。
        """
        result = []
        for ch in s:
            cp = ord(ch)
            if 0xFF01 <= cp <= 0xFF5E:   # 全角 ！-～ → 半角 !-~
                result.append(chr(cp - 0xFEE0))
            elif cp == 0x3000:            # 全角空格 → 普通空格
                result.append(' ')
            else:
                result.append(ch)
        return ''.join(result)

    @classmethod
    def _strip_inline_ads(cls, line: str) -> str:
        """从正文行中截除嵌入的广告片段。

        支持两种模式：
        - 行末追加型：正文…… 记住网址xxx.cc
        - 行首前缀型：{}微博Cc栗~{ 正文……

        只在截取后仍有足够正文内容（≥4 个汉字）时才截取。
        """
        # 行末广告（归一化后匹配，切点 1:1 映射回原始行）
        norm = cls._fw_normalize(line)
        m = cls._INLINE_AD_FRAG_RE.search(norm)
        if m:
            cjk_before = sum(1 for ch in line[:m.start()] if '一' <= ch <= '鿿')
            if cjk_before >= 4:
                return line[:m.start()].rstrip('，, \t')

        # 行首广告前缀（社交账号推广，如 {}微博Cc栗~{ 正文……）
        m_lead = cls._LEADING_AD_FRAG_RE.match(line)
        if m_lead:
            rest = line[m_lead.end():]
            cjk_after = sum(1 for ch in rest if '一' <= ch <= '鿿')
            if cjk_after >= 4:
                return rest

        return line

    @classmethod
    def _clean_noise(cls, line: str) -> str:
        """去除行内不可见字符、HTML 残留、私用区码位等乱码噪声。"""
        if '&' in line:
            line = _html.unescape(line)
        line = cls._HTML_TAG_RE.sub('', line)
        line = cls._NOISE_RE.sub('', line)
        return line

    @classmethod
    def _split_url_indices(cls, lines: list) -> set:
        """检测被换行拆开的推广网址，返回需要追加标记的行的 0-indexed 索引集合。

        只处理 s1 未独立命中的情况：若拼接 window 命中 URL，则 s1 是「域名前半/
        邀请语」，应补标记；s2 若独立命中则已在单行扫描中处理，若未命中则也补标记。
        当 s1 已独立命中时跳过（s2 是 URL 之后的内容，不应连累删除）。
        """
        suspicious: set = set()
        for i in range(len(lines) - 1):
            s1, s2 = lines[i].strip(), lines[i + 1].strip()
            if not s1 or not s2:
                continue
            if cls._URL_RE.search(s1):
                continue  # s1 已独立命中；s2 是其后内容，不牵连
            window = s1[-50:] + s2[:50]
            if cls._URL_RE.search(window):
                suspicious.add(i)          # s1 是被拆开 URL 的前半部分
                if not cls._URL_RE.search(s2):
                    suspicious.add(i + 1)  # s2 是后半部分且未独立命中
        return suspicious

    @classmethod
    def _score(cls, line: str, near_boundary: bool = False,
               hard_kw=None, soft_kw=None) -> float:
        s = line.strip()
        if not s:
            return 0.0

        _hard = hard_kw if hard_kw is not None else cls._HARD_KW
        _soft = soft_kw if soft_kw is not None else cls._SOFT_KW

        score = 0.0

        s_norm = cls._fw_normalize(s)
        if cls._URL_RE.search(s_norm):
            score = max(score, 0.88)
        if cls._PIRACY_RE.search(s_norm):
            score = max(score, 0.85)
        if cls._PLATFORM_RE.search(s_norm):
            score = max(score, 0.82)
        if cls._LEADING_AD_FRAG_RE.match(s):
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
            [{
                'line_num': int,
                'score': float,
                'text': str,          # 原始行（已 strip）
                'mode': str,          # 'remove'（整行删除）| 'strip'（只截除广告片段）
                'stripped': str|None, # mode='strip' 时截除后的保留内容
            }]
        """
        lines = content.split('\n')
        n = len(lines)
        result = []
        already: set = set()

        def _make_entry(i: int, line: str, sc: float) -> dict:
            stripped = cls._strip_inline_ads(line)
            if stripped != line and stripped.strip():
                return {'line_num': i + 1, 'score': round(sc, 3), 'text': line.strip(),
                        'mode': 'strip', 'stripped': stripped.strip()}
            return {'line_num': i + 1, 'score': round(sc, 3), 'text': line.strip(),
                    'mode': 'remove', 'stripped': None}

        for i, line in enumerate(lines):
            sc = cls._score(
                line,
                near_boundary=(i < head_tail_lines or i >= n - head_tail_lines),
                hard_kw=hard_kw, soft_kw=soft_kw,
            )
            if sc >= threshold:
                result.append(_make_entry(i, line, sc))
                already.add(i)
        # 检测被换行拆开的推广网址
        for i in cls._split_url_indices(lines):
            if i not in already:
                result.append(_make_entry(i, lines[i], 0.85))
                already.add(i)
        result.sort(key=lambda r: r['line_num'])
        return result

    @classmethod
    def scan_noise(cls, content: str) -> List[dict]:
        """扫描行内乱码噪声（不修改），返回可清理行列表。

        Returns:
            [{
                'line_num': int,       # 1-indexed
                'original': str,       # 原始行文本
                'cleaned': str,        # 清理后文本
                'types': List[str],    # watermark / pua / control / html_tag / html_entity
                'removed_count': int,  # 删除的字符数（长度差）
            }]
        """
        lines = content.split('\n')
        results = []
        for i, line in enumerate(lines):
            cleaned = cls._clean_noise(line)
            if cleaned == line:
                continue
            types: List[str] = []
            if cls._NOISE_RE.search(line):
                has_zw = any(
                    '\u200b' <= c <= '\u200f' or c in '\ufeff\u00ad\u00a0'
                    for c in line
                )
                has_pua = any('\ue000' <= c <= '\uf8ff' for c in line)
                has_ctrl = any(
                    ord(c) <= 0x08 or 0x0e <= ord(c) <= 0x1f or ord(c) == 0x7f
                    for c in line
                )
                if has_zw:  types.append('watermark')
                if has_pua: types.append('pua')
                if has_ctrl: types.append('control')
            if cls._HTML_TAG_RE.search(line):
                types.append('html_tag')
            if '&' in line and _html.unescape(line) != line:
                types.append('html_entity')
            if not types:
                types.append('noise')
            results.append({
                'line_num': i + 1,
                'original': line,
                'cleaned': cleaned,
                'types': types,
                'removed_count': len(line) - len(cleaned),
            })
        return results
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

        # 先去除不可见字符、HTML 标签残留等乱码噪声
        for i, line in enumerate(lines):
            cleaned = cls._clean_noise(line)
            if cleaned != line:
                lines[i] = cleaned

        # 截除行内夹带的广告片段（正文+广告混合行 → 只保留正文部分）
        for i, line in enumerate(lines):
            stripped = cls._strip_inline_ads(line)
            if stripped != line:
                lines[i] = stripped

        scores = [
            cls._score(line,
                       near_boundary=(i < head_tail_lines or i >= n - head_tail_lines),
                       hard_kw=hard_kw, soft_kw=soft_kw)
            for i, line in enumerate(lines)
        ]

        removed: Set[int] = set()

        # 将跨行拆分 URL 的两行分值提升到 0.85，使其进入单行过滤
        for i in cls._split_url_indices(lines):
            scores[i] = max(scores[i], 0.85)

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

        # 连续 3 行以上的纯符号装饰行（如 ~~~~~、*****、=====）→ 整块删除
        _PURE_SYMBOL_RE = re.compile(r'^[~＊*=\-_+#@^&]{5,}\s*$')
        sym_run_start = None
        for i, line in enumerate(lines):
            if _PURE_SYMBOL_RE.match(line.strip()):
                if sym_run_start is None:
                    sym_run_start = i
            else:
                if sym_run_start is not None and (i - sym_run_start) >= 3:
                    removed.update(range(sym_run_start, i))
                sym_run_start = None
        if sym_run_start is not None and (n - sym_run_start) >= 3:
            removed.update(range(sym_run_start, n))

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
