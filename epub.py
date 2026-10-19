"""EPUB生成模块"""

import html
import os
import re
from datetime import datetime
from typing import Optional, List

try:
    from ebooklib import epub
    EPUB_SUPPORT = True
except ImportError:
    EPUB_SUPPORT = False

from encoding import EncodingDetector
from chapter import ChapterAnalyzer
from cover import CoverDownloader
from display import DirectoryDisplay


class EPUBGenerator:
    """EPUB文件生成器"""

    INTRO_MARKERS = [
        '文案：', '简介：', '内容标签：', '搜索关键字：', '一句话简介：', '立意：',
        '文案:', '简介:', '标签：', '主角：', '配角：', '其它：', '年下', 'HE', 'BE'
    ]

    _AUTHOR_NOTE_RE = re.compile(
        r'^[\s=*]*(作者有话要?说?|作者说|作话|作者留言)[\s:：。=*]{0,10}$'
    )

    _SCENE_BREAK_PAT = re.compile(r'^[\*＊·•\s]+$')

    # 默认样式预设：scope=inline 包裹 span，scope=block 给整段加 class
    DEFAULT_STYLE_PRESETS = [
        {
            "key": "dlg-cn",  "name": "双引号对话", "scope": "inline",
            "regex": "\u201c[^\u201d]{0,400}\u201d", "enabled": True,
            "color": "", "font_size": "", "font_style": "",
        },
        {
            "key": "dlg-sq",  "name": "角括号对话", "scope": "inline",
            "regex": r"「[^」]{0,400}」", "enabled": True,
            "color": "", "font_size": "", "font_style": "",
        },
        {
            "key": "dlg-dbl", "name": "双角括号",   "scope": "inline",
            "regex": r"『[^』]{0,400}』", "enabled": True,
            "color": "", "font_size": "", "font_style": "",
        },
        {
            "key": "dlg-sq2", "name": "单引号对话", "scope": "inline",
            "regex": "\u2018[^\u2019]{0,400}\u2019", "enabled": True,
            "color": "", "font_size": "", "font_style": "",
        },
    ]
    @staticmethod
    def compile_styles(presets: list):
        """预编译样式预设，返回 (inline_pats, block_pats)。

        inline_pats: [(compiled_re, css_key)]
        block_pats:  [(compiled_re, css_key)]
        """
        inline_pats, block_pats = [], []
        for p in presets:
            if not p.get('enabled', True):
                continue
            try:
                rx = re.compile(p['regex'])
            except re.error:
                continue
            target = inline_pats if p.get('scope', 'inline') == 'inline' else block_pats
            target.append((rx, p['key']))
        return inline_pats, block_pats

    # 缓存默认预设的编译结果
    _DEFAULT_INLINE_PATS = None
    _DEFAULT_BLOCK_PATS  = None

    @classmethod
    def _default_inline_pats(cls):
        if cls._DEFAULT_INLINE_PATS is None:
            cls._DEFAULT_INLINE_PATS, cls._DEFAULT_BLOCK_PATS = cls.compile_styles(
                cls.DEFAULT_STYLE_PRESETS)
        return cls._DEFAULT_INLINE_PATS

    @classmethod
    def _default_block_pats(cls):
        if cls._DEFAULT_BLOCK_PATS is None:
            cls._DEFAULT_INLINE_PATS, cls._DEFAULT_BLOCK_PATS = cls.compile_styles(
                cls.DEFAULT_STYLE_PRESETS)
        return cls._DEFAULT_BLOCK_PATS

    # 保留旧 _DLG_PATS 兼容性（现在由 DEFAULT_STYLE_PRESETS 生成）
    _DLG_PATS = [
        (re.compile(r'“[^”]{0,400}”'),             'dlg-cn'),
        (re.compile(r'「[^」]{0,400}」'),           'dlg-sq'),
        (re.compile(r'『[^』]{0,400}』'),           'dlg-sq'),
        (re.compile('‘[^’]{0,400}’'), 'dlg-sq2'),
    ]

    # 默认对话样式（空 = 不生成 CSS，由 custom_css 或用户自定义）
    DIALOG_STYLE_DEFAULTS: dict = {}

    _TOC_PAGE_SIZE = 20

    _VOLUME_RE = re.compile(
        r'^(第[零一二三四五六七八九十百千万两\d]+卷|卷[零一二三四五六七八九十百千万两\d]|[上中下]卷)'
    )

    _CSS_TEMPLATE = (
        '@charset "UTF-8";'
        'body{{font-family:"Noto Serif CJK SC","Source Han Serif SC","思源宋体","STSong","SimSun","宋体",serif;'
        'font-size:1em;margin:0;color:#1c1c1c;word-break:break-all;overflow-wrap:break-word;'
        '-webkit-hyphens:none;hyphens:none}}'
        # .content 用百分比边距，不随阅读器字号膨胀
        '.content{{margin:{margin}}}'
        'h1{{font-size:1.3em;font-weight:bold;text-align:center;line-height:1.5;'
        'margin:2em 0 1.8em;padding-bottom:.6em;border-bottom:1px solid #c0c0c0;letter-spacing:.08em}}'
        'h2{{font-size:.92em;font-weight:normal;text-align:center;margin-top:3em;'
        'padding:.5em 0 .3em;border-top:1px solid #e0e0e0;color:#999;letter-spacing:.1em}}'
        'p{{text-indent:{text_indent};line-height:{line_height};margin:.35em 0;text-align:justify}}'
        'p.noind{{text-indent:0}}'
        'p.scene-break{{text-indent:0;text-align:center;color:#bbb;padding:.8em 0;letter-spacing:.5em}}'
        '.toc{{list-style:none;padding:0;margin:1.5em 0}}'
        '.toc li{{padding:.55em .1em;border-bottom:1px solid #ebebeb}}'
        '.toc a{{text-decoration:none;color:#2c2c2c;font-size:.95em}}'
        '.toc a:hover{{text-decoration:underline}}'
        '.toc-vol>a{{font-weight:600;color:#1a1a1a}}'
        '.toc-sub{{margin-left:1.5em;list-style:none}}'
        '.dropcap{{float:left;font-size:3em;line-height:.8;margin:.05em .08em 0 0;font-weight:bold}}'
        'aside[epub|type="footnote"]{{font-size:.85em;color:#555;border-top:1px solid #e0e0e0;margin-top:2em;padding-top:.5em}}'
        'a[epub|type="noteref"]{{vertical-align:super;font-size:.75em;text-decoration:none;color:#888}}'
        '.header-img{{margin:0;margin-bottom:1em}}.header-img img{{width:100%;display:block}}'
        '.fullpage{{text-align:center;padding:0;margin:0}}'
        '.fullpage img{{max-width:100%;max-height:100vh;display:block;margin:auto}}'
    )

    @classmethod
    def _build_css(cls, margin: str = "0 4%", line_height: float = 1.8,
                   text_indent: str = "2em", custom_css: str = "",
                   dialog_styles: dict = None,
                   style_presets: list = None) -> str:
        css = cls._CSS_TEMPLATE.format(
            margin=margin, line_height=line_height, text_indent=text_indent
        )
        # 从 style_presets 生成 span/block CSS（优先于旧 dialog_styles）
        presets = style_presets if style_presets is not None else cls.DEFAULT_STYLE_PRESETS
        seen_keys: set = set()
        for p in presets:
            if not p.get('enabled', True):
                continue
            key = p['key']
            if key in seen_keys:
                continue
            seen_keys.add(key)
            rules = []
            if p.get('color'):
                rules.append(f'color:{p["color"]}')
            if p.get('font_size'):
                rules.append(f'font-size:{p["font_size"]}')
            if p.get('font_style'):
                rules.append(f'font-style:{p["font_style"]}')
            if rules:
                css += f'span.{key}{{{";".join(rules)}}}'
        # 向后兼容：若传了旧 dialog_styles，补充 style_presets 没覆盖到的 key
        _ds = dialog_styles if dialog_styles is not None else cls.DIALOG_STYLE_DEFAULTS
        for cls_name, props in _ds.items():
            if cls_name in seen_keys:
                continue
            rules = []
            if props.get('color'):
                rules.append(f'color:{props["color"]}')
            if props.get('font_size'):
                rules.append(f'font-size:{props["font_size"]}')
            if props.get('font_style'):
                rules.append(f'font-style:{props["font_style"]}')
            if rules:
                css += f'span.{cls_name}{{{";".join(rules)}}}'
        return css + (custom_css or '')

    @staticmethod
    def _split_author_note(content: str):
        """从章节内容末尾拆出「作者有话说」子节。

        Returns:
            (main_content, note_body) — note_body 为标题行之后的正文，
            不含标题行本身；未找到则 note_body 为 None。
        """
        lines = content.split('\n')
        note_start = None
        for i in range(len(lines) - 1, -1, -1):
            stripped = lines[i].strip()
            if not stripped or re.match(r'^=+$', stripped):
                continue
            if EPUBGenerator._AUTHOR_NOTE_RE.match(stripped):
                note_start = i
            break
        if note_start is None:
            return content, None

        main_lines = lines[:note_start]
        note_body_lines = lines[note_start + 1:]

        while main_lines and not main_lines[-1].strip():
            main_lines.pop()
        while note_body_lines and not note_body_lines[0].strip():
            note_body_lines.pop(0)
        while note_body_lines and (not note_body_lines[-1].strip() or
              re.match(r'^=+$', note_body_lines[-1].strip())):
            note_body_lines.pop()

        return '\n'.join(main_lines), '\n'.join(note_body_lines)

    @staticmethod
    def _extract_author(content: str) -> Optional[str]:
        patterns = [
            r'《[^》]+》作者[：:]\s*([^\n]+)', r'作者[：:]\s*([^\n]+)', r'作者\s+([^\n]+)',
            r'by\s+([^\n]+)', r'《作者》\s*([^\n]+)', r'\[作者\]\s*([^\n]+)',
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
        if content.startswith('\ufeff'):
            content = content[1:]
        lines = content.split('\n')[:20]

        # 模式1：书名行 + 下一行是作者行
        title_prefixes = ['书名：', '书名:', '题名：', '题名:', '书名', '题名']
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if line_stripped and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith('作者：') or next_line.startswith('作者:'):
                    title = line_stripped
                    for prefix in title_prefixes:
                        if title.startswith(prefix):
                            title = title[len(prefix):].strip()
                            break
                    title = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s\[\]]', '', title).strip()
                    if title and 1 < len(title) < 50:
                        return title

        # 模式2：正则匹配
        first_part = '\n'.join(lines)
        for pattern in [r'《([^》]+)》作者', r'书名[：:]\s*([^\n]+)']:
            match = re.search(pattern, first_part)
            if match:
                title = match.group(1).strip()
                title = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s\[\]]', '', title).strip()
                if title:
                    return title

        # 模式3：书名号
        match = re.search(r'《([^》]+)》', first_part)
        if match:
            title = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s\[\]]', '', match.group(1).strip())
            if title and 1 < len(title) < 50:
                return title

        return None

    # 句子终止符：紧接这些字符的段末可以安全拼接下一段
    _TERMINAL = frozenset('。！？"…』」')

    @staticmethod
    def _merge_duplicate_chapters(chapters: List[dict]) -> List[dict]:
        """合并相邻的同名章节（抓取断点造成的重复章节）。"""
        merged: List[dict] = []
        for ch in chapters:
            if merged and merged[-1]['title'] == ch['title']:
                prev = merged[-1]
                prev_tail = prev['content'].rstrip()
                curr_head = ch['content'].lstrip()
                if prev_tail and prev_tail[-1] not in EPUBGenerator._TERMINAL:
                    prev['content'] = prev_tail + curr_head
                else:
                    prev['content'] = prev['content'].rstrip('\n') + '\n' + curr_head
            else:
                merged.append(dict(ch))
        return merged

    @staticmethod
    def _apply_dialogue_spans(text: str, inline_pats=None) -> str:
        """将对话引号内容包裹在 span 中，供 CSS 自定义样式。"""
        pats = inline_pats if inline_pats is not None else EPUBGenerator._DLG_PATS
        for pat, cls in pats:
            text = pat.sub(lambda m, c=cls: f'<span class="{c}">{m.group(0)}</span>', text)
        return text

    @staticmethod
    def _parse_chapters(content: str) -> List[dict]:
        """解析章节结构（使用 ChapterAnalyzer 统一识别）"""
        content = ChapterAnalyzer.fix_broken_numbering(content)
        structure = ChapterAnalyzer.analyze_chapter_structure(content)
        lines = content.split('\n')
        chapters = []

        def _skip_comment(line: str) -> bool:
            return line.strip().startswith('<!--') or line.strip().startswith('-->')

        # 提取第一章之前的所有内容（标题、作者、文案简介等）
        if structure['chapters']:
            first_start = structure['chapters'][0]['start_line'] - 1
            intro_lines = [
                line for line in lines[:first_start]
                if not _skip_comment(line)
            ]
            # 去掉首尾空行
            while intro_lines and not intro_lines[0].strip():
                intro_lines.pop(0)
            while intro_lines and not intro_lines[-1].strip():
                intro_lines.pop()
            if intro_lines:
                has_synopsis = any(
                    any(m in line for m in EPUBGenerator.INTRO_MARKERS)
                    for line in intro_lines
                )
                title = '文案简介' if has_synopsis else '前言'
                chapters.append({'title': title, 'content': '\n'.join(intro_lines)})

        # 提取各章节内容
        for ch in structure['chapters']:
            start = ch['start_line'] - 1
            end = ch['end_line']
            chapter_lines = [line for line in lines[start+1:end] if not _skip_comment(line)]
            chapters.append({'title': ch['title'], 'content': '\n'.join(chapter_lines)})

        if not chapters:
            chapters = [{'title': '正文', 'content': content}]

        return EPUBGenerator._merge_duplicate_chapters(chapters)

    @staticmethod
    def _merge_dialogue_splits(content: str) -> str:
        """合并被拆行的对话：行尾为「：」且下一非空行以引号开头时拼回一行。"""
        _OPEN_QUOTES = frozenset('"「『“‘')
        lines = content.split('\n')
        out = []
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped and stripped[-1] in ('：', ':'):
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    next_s = lines[j].strip()
                    if next_s and next_s[0] in _OPEN_QUOTES:
                        out.append(lines[i].rstrip() + next_s)
                        i = j + 1
                        continue
            out.append(lines[i])
            i += 1
        return '\n'.join(out)

    @staticmethod
    def _clean_chapter_content(content: str) -> str:
        """清理章节内容，移除末尾的单独括号等"""
        lines = content.split('\n')
        end_idx = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            if not line:
                continue
            if line in ('（', '(', '）', ')'):
                end_idx = i
            else:
                break
        cleaned = lines[:end_idx]
        while cleaned and not cleaned[-1].strip():
            cleaned.pop()
        return '\n'.join(cleaned)

    _NOTE_RE = re.compile(r'\{\{注:(.*?)\}\}')

    @staticmethod
    def _chapter_to_html(content: str, drop_cap: bool = False, ch_idx: int = 0,
                         inline_pats=None, block_pats=None) -> str:
        content = EPUBGenerator._clean_chapter_content(content)
        content = EPUBGenerator._merge_dialogue_splits(content)
        paragraphs = []
        current = []
        noind = [False]
        notes: list = []   # 收集脚注 [(k, note_text)]

        def _note_sub(m):
            k = len(notes) + 1
            notes.append((k, m.group(1)))
            return (f'<a epub:type="noteref" href="#fn_{ch_idx}_{k}"'
                    f' id="fnref_{ch_idx}_{k}">[注{k}]</a>')

        def _flush():
            if not current:
                return
            text = ''.join(current)
            cls = ' class="noind"' if noind[0] else ''
            # block scope：若整段匹配某个 block_pats 规则，给 <p> 加额外 class
            if block_pats and not noind[0]:
                for rx, bkey in (block_pats or []):
                    if rx.search(text):
                        cls = f' class="{bkey}"'
                        break
            paragraphs.append(f'<p{cls}>{EPUBGenerator._apply_dialogue_spans(text, inline_pats)}</p>')
            current.clear()
            noind[0] = False

        for line in content.split('\n'):
            stripped = line.strip()
            if stripped:
                if EPUBGenerator._SCENE_BREAK_PAT.match(stripped):
                    _flush()
                    paragraphs.append(f'<p class="scene-break">{html.escape(stripped)}</p>')
                else:
                    if not current:  # 段落第一行：检测是否有手动缩进
                        noind[0] = line.startswith(('　', ' '))
                    line_escaped = html.escape(stripped, quote=True)
                    line_escaped = EPUBGenerator._NOTE_RE.sub(_note_sub, line_escaped)
                    current.append(line_escaped)
            else:
                _flush()
        _flush()
        if drop_cap and paragraphs:
            for idx, p in enumerate(paragraphs):
                if p.startswith('<p>') and len(p) > 4:
                    inner = p[3:-4]
                    if inner and inner[0] not in ('<', '&'):
                        paragraphs[idx] = (f'<p><span class="dropcap">{inner[0]}</span>'
                                           f'{inner[1:]}</p>')
                        break
        if notes:
            asides = []
            for k, note_text in notes:
                asides.append(
                    f'<aside epub:type="footnote" id="fn_{ch_idx}_{k}">'
                    f'<p><a href="#fnref_{ch_idx}_{k}">[注{k}]</a> {note_text}</p></aside>'
                )
            paragraphs.append('\n'.join(asides))
        return '\n'.join(paragraphs)

    @staticmethod
    def parse_epub(epub_path: str) -> dict:
        """将 EPUB 文件解析回结构化数据。

        返回:
          {
            "title": str, "author": str, "description": str,
            "language": str, "publisher": str, "isbn": str,
            "pubdate": str, "tags": [str],
            "chapters": [{"title": str, "content": str}]
          }
        content 为纯文本，段落之间以 \\n 分隔。
        """
        if not EPUB_SUPPORT:
            raise RuntimeError("ebooklib 不可用，请先安装 ebooklib")

        _TAG_RE = re.compile(r'<[^>]+>', re.S)

        def _strip(s: str) -> str:
            return html.unescape(_TAG_RE.sub('', s)).strip()

        def _parse_item(item) -> tuple:
            """返回 (chapter_title, body_text)，body_text=None 表示跳过（TOC/Nav 页）。"""
            raw = item.get_content().decode('utf-8', errors='ignore')
            # 跳过 nav / TOC 页
            if ('<nav' in raw.lower()
                    or 'epub:type="frontmatter toc"' in raw
                    or "epub:type='frontmatter toc'" in raw):
                return '', None
            # 跳过链接密集型目录页（外部 EPUB 兜底）
            link_count = raw.lower().count('<a ')
            if link_count > 12:
                body_m = re.search(r'<body[^>]*>(.*?)</body>', raw, re.S | re.I)
                body_raw = body_m.group(1) if body_m else raw
                non_link = _TAG_RE.sub('', re.sub(r'<a\b[^>]*>.*?</a>', '', body_raw, flags=re.S | re.I))
                if len(html.unescape(non_link).strip()) < 200:
                    return '', None

            title_m = re.search(r'<h[1-3][^>]*>(.*?)</h[1-3]>', raw, re.S | re.I)
            ch_title = _strip(title_m.group(1)) if title_m else ''

            body_m = re.search(r'<body[^>]*>(.*?)</body>', raw, re.S | re.I)
            body = body_m.group(1) if body_m else raw

            paras = []
            for p_m in re.finditer(r'<p[^>]*>(.*?)</p>', body, re.S | re.I):
                txt = _strip(p_m.group(1))
                if txt and txt != ch_title:
                    paras.append(txt)

            return ch_title, '\n'.join(paras)

        book = epub.read_epub(epub_path, options={'ignore_ncx': False})

        def _first_meta(dc_key):
            items = book.get_metadata('DC', dc_key)
            return items[0][0] if items else ''

        title    = _first_meta('title')
        author   = _first_meta('creator')
        desc     = _first_meta('description')
        language = _first_meta('language') or 'zh'
        publisher = _first_meta('publisher')
        pubdate  = _first_meta('date')
        tags     = [t[0] for t in book.get_metadata('DC', 'subject') if t[0]]
        isbn = ''
        for val, _ in book.get_metadata('DC', 'identifier'):
            if val and not val.startswith('urn:uuid:'):
                isbn = val
                break

        chapters = []
        for item_id, _linear in book.spine:
            item = book.get_item_with_id(item_id)
            if item is None:
                continue
            mt = getattr(item, 'media_type', '') or ''
            if 'html' not in mt.lower() and 'xhtml' not in mt.lower():
                continue
            ch_title, body = _parse_item(item)
            if body is None:
                continue
            if not body.strip() and not ch_title:
                continue
            chapters.append({'title': ch_title or '无题', 'content': body})

        return {
            'title': title, 'author': author, 'description': desc,
            'language': language, 'publisher': publisher,
            'isbn': isbn, 'pubdate': pubdate, 'tags': tags,
            'chapters': chapters,
        }

    @staticmethod
    def txt_to_epub(txt_path: Optional[str], output_path: str = None,
                    book_title: str = "", author: str = "",
                    cover_image: str = None, auto_search_cover: bool = False, cover_url: str = None,
                    description: str = "", publisher: str = "",
                    margin: str = "0 4%", line_height: float = 1.8,
                    text_indent: str = "2em", custom_css: str = "",
                    dialog_styles: dict = None,
                    isbn: str = "", pubdate: str = "", language: str = "zh",
                    tags=None, drop_cap: bool = False,
                    volume_map: dict = None,
                    style_presets: list = None,
                    header_images: list = None,
                    fonts: dict = None,
                    illustrations: list = None,
                    chapters: list = None) -> Optional[str]:
        """将TXT文件（或预解析章节列表）转换为EPUB。

        当 chapters 不为 None 时跳过文件读取，直接使用传入的章节列表；
        此时 txt_path 可为 None，但必须通过 output_path 指定输出路径。
        """
        if not EPUB_SUPPORT:
            print("❌ EPUB生成功能不可用，请先安装ebooklib库")
            return None

        try:
            content = ''
            if chapters is None:
                # 正常路径：读文件并解析章节
                content, _enc = EncodingDetector.read_file_with_auto_encoding(txt_path)
                chapters = EPUBGenerator._parse_chapters(content)
                if not chapters:
                    chapters = [{'title': book_title if book_title else "正文", 'content': content}]

            # 手动卷分配：在指定章节前插入卷标题章节（_VOLUME_RE 会自动识别生成两级 TOC）
            if volume_map:
                result_chs = []
                inserted_vols: set = set()
                for ch in chapters:
                    vol_name = volume_map.get(ch['title'])
                    if vol_name and vol_name not in inserted_vols:
                        result_chs.append({'title': vol_name, 'content': ''})
                        inserted_vols.add(vol_name)
                    result_chs.append(ch)
                chapters = result_chs

            if not book_title:
                if content:
                    book_title = EPUBGenerator._extract_title(content)
                if book_title:
                    print(f"   从内容中提取书名: {book_title}")
                elif txt_path:
                    book_title = os.path.splitext(os.path.basename(txt_path))[0].replace('_epub_ready', '')
                else:
                    book_title = "未命名"

            if not author:
                if content:
                    author = EPUBGenerator._extract_author(content)
                if author:
                    print(f"   从内容中提取作者: {author}")
                elif txt_path:
                    print("   ⚠️ 未能从文件中提取作者名")
                    author = input("   请输入作者名: ").strip() or "未知"
                else:
                    author = "未知"

            book = epub.EpubBook()
            book.set_identifier(f"urn:uuid:{datetime.now().strftime('%Y%m%d%H%M%S')}")
            book.set_title(book_title)
            book.set_language(language or 'zh')
            book.add_author(author if author else "未知")
            if description:
                book.add_metadata('DC', 'description', description)
            if publisher:
                book.add_metadata('DC', 'publisher', publisher)
            if isbn:
                book.add_metadata('DC', 'identifier', isbn)
            if pubdate:
                book.add_metadata('DC', 'date', pubdate)
            if tags:
                tag_list = (tags if isinstance(tags, list)
                            else [t.strip() for t in re.split(r'[,，、;；]', str(tags)) if t.strip()])
                for tag in tag_list:
                    book.add_metadata('DC', 'subject', tag)

            # 封面处理
            actual_cover_path = cover_image
            _asset_dir = (os.path.dirname(os.path.abspath(txt_path))
                          if txt_path else os.path.expanduser('~/.txt2epub/covers'))
            if cover_url and not actual_cover_path:
                os.makedirs(_asset_dir, exist_ok=True)
                actual_cover_path = CoverDownloader.download_cover_from_url(cover_url, _asset_dir)
            if auto_search_cover and not actual_cover_path:
                os.makedirs(_asset_dir, exist_ok=True)
                actual_cover_path = CoverDownloader.search_and_download_cover(book_title, author or "", _asset_dir)

            if actual_cover_path and os.path.exists(actual_cover_path):
                try:
                    with open(actual_cover_path, 'rb') as f:
                        book.set_cover('cover.jpg', f.read())
                    print(f"✅ 添加封面: {actual_cover_path}")
                except Exception as e:
                    print(f"⚠️ 添加封面失败: {e}")

            # 插图页插入（在 TOC 计算前，以正文章节序号为基准）
            if illustrations:
                # 构建正文章节列表（排除前言/目录）的索引映射
                _content_idx_to_ch_idx = []
                for _ci, _ch in enumerate(chapters):
                    if '_html' not in _ch:
                        _content_idx_to_ch_idx.append(_ci)
                # 倒序插入，避免 index 偏移
                _illust_sorted = sorted(illustrations,
                                        key=lambda x: x.get('after_chapter', 0), reverse=True)
                for _illi, _ill in enumerate(_illust_sorted):
                    _after = _ill.get('after_chapter', 0)
                    _caption = _ill.get('caption', '')
                    _ill_path = _ill.get('path', '')
                    if not os.path.isfile(str(_ill_path)):
                        continue
                    _ill_name = f'illust_{_illi}.jpg'
                    # 找到正确的插入位置
                    if _after < len(_content_idx_to_ch_idx):
                        _insert_at = _content_idx_to_ch_idx[_after] + 1
                    else:
                        _insert_at = len(chapters)
                    chapters.insert(_insert_at, {
                        'title': _caption,
                        '_html': (f'<div class="fullpage">'
                                  f'<img src="../images/{_ill_name}" alt="{html.escape(_caption)}"/>'
                                  f'</div>'),
                        '_skip_ncx': not bool(_caption),
                        '_illust_path': _ill_path,
                        '_illust_name': _ill_name,
                    })

            # 插入目录（支持多页分页及卷级两级结构）
            INTRO_TITLES = ('文案简介', '前言')
            insert_pos = 1 if (chapters and chapters[0]['title'] in INTRO_TITLES) else 0

            content_chs = [(j, ch) for j, ch in enumerate(chapters)
                           if ch['title'] not in INTRO_TITLES]
            has_volumes = any(EPUBGenerator._VOLUME_RE.match(ch['title'])
                              for _, ch in content_chs)

            if has_volumes:
                num_toc_pages = 1
                # Group content chapters by volume for nested HTML TOC
                vol_groups: list = []
                cur_vol: dict = None
                for j, ch in content_chs:
                    fi = j + 1 + num_toc_pages
                    if EPUBGenerator._VOLUME_RE.match(ch['title']):
                        if cur_vol:
                            vol_groups.append(cur_vol)
                        cur_vol = {'title': ch['title'], 'fi': fi, 'children': []}
                    else:
                        if cur_vol is not None:
                            cur_vol['children'].append({'title': ch['title'], 'fi': fi})
                        else:
                            vol_groups.append({'title': ch['title'], 'fi': fi, 'children': None})
                if cur_vol:
                    vol_groups.append(cur_vol)

                parts = ['<ol class="toc">']
                for vg in vol_groups:
                    if vg['children'] is None:
                        parts.append(
                            f'<li><a href="chapter_{vg["fi"]:03d}.xhtml">'
                            f'{html.escape(vg["title"])}</a></li>'
                        )
                    else:
                        parts.append(
                            f'<li class="toc-vol"><a href="chapter_{vg["fi"]:03d}.xhtml">'
                            f'{html.escape(vg["title"])}</a>'
                        )
                        if vg['children']:
                            parts.append('<ol class="toc-sub">')
                            for child in vg['children']:
                                parts.append(
                                    f'<li><a href="chapter_{child["fi"]:03d}.xhtml">'
                                    f'{html.escape(child["title"])}</a></li>'
                                )
                            parts.append('</ol>')
                        parts.append('</li>')
                parts.append('</ol>')
                toc_pages = [{'title': '目录', '_html': '\n'.join(parts), '_skip_ncx': True}]

            else:
                # Flat TOC — paginate when chapter count exceeds _TOC_PAGE_SIZE
                items = [{'title': ch['title'], 'j': j} for j, ch in content_chs]
                num_toc_pages = max(1, (len(items) + EPUBGenerator._TOC_PAGE_SIZE - 1)
                                    // EPUBGenerator._TOC_PAGE_SIZE)
                for item in items:
                    item['fi'] = item['j'] + 1 + num_toc_pages
                toc_pages = []
                for pg in range(num_toc_pages):
                    page_items = items[pg * EPUBGenerator._TOC_PAGE_SIZE:
                                       (pg + 1) * EPUBGenerator._TOC_PAGE_SIZE]
                    title = '目录' if pg == 0 else f'目录（续{pg}）'
                    li = [
                        f'<li><a href="chapter_{it["fi"]:03d}.xhtml">'
                        f'{html.escape(it["title"])}</a></li>'
                        for it in page_items
                    ]
                    toc_pages.append({
                        'title': title,
                        '_html': '<ol class="toc">\n' + '\n'.join(li) + '\n</ol>',
                        '_skip_ncx': True,
                    })

            for i, tp in enumerate(toc_pages):
                chapters.insert(insert_pos + i, tp)

            # 生成章节
            _dc_applied = [False]
            _inline_pats, _block_pats = EPUBGenerator.compile_styles(
                style_presets if style_presets is not None else EPUBGenerator.DEFAULT_STYLE_PRESETS
            )
            # 预处理头图
            _headers: list = []
            if header_images:
                try:
                    from header_image import make_header
                    _headers = header_images if isinstance(header_images, list) else [header_images]
                except ImportError:
                    print("   ⚠️ header_image 模块不可用，跳过头图")
            spine = ['nav']
            toc = []
            _cur_vol_sec = None
            _cur_vol_children: list = []
            css_item = epub.EpubItem(
                uid='main-style', file_name='styles/style.css',
                media_type='text/css',
                content=EPUBGenerator._build_css(
                    margin=margin, line_height=line_height,
                    text_indent=text_indent, custom_css=custom_css,
                    dialog_styles=dialog_styles,
                    style_presets=style_presets,
                ).encode('utf-8'),
            )
            book.add_item(css_item)

            # 字体子集化（fontTools）
            if fonts:
                try:
                    import tempfile
                    from font_subset import process_fonts
                    _font_ext_map = {"ttf": "font/ttf", "otf": "font/otf",
                                     "woff": "font/woff", "woff2": "font/woff2"}
                    with tempfile.TemporaryDirectory() as _ftmp:
                        _font_items = process_fonts(fonts, chapters, _ftmp)
                        _font_css = ''
                        for fi in _font_items:
                            _ext = fi['filename'].rsplit('.', 1)[-1].lower()
                            _mt = _font_ext_map.get(_ext, 'application/octet-stream')
                            book.add_item(epub.EpubItem(
                                uid=f"font-{fi['role']}",
                                file_name=f"fonts/{fi['filename']}",
                                media_type=_mt, content=fi['bytes'],
                            ))
                            _font_css += fi['css']
                    if _font_css:
                        # 把 @font-face 前置到 CSS
                        css_item.content = (_font_css + css_item.content.decode('utf-8')).encode('utf-8')
                except ImportError:
                    print("   ⚠️ font_subset 模块不可用，跳过字体嵌入")
            for i, chapter in enumerate(chapters):
                chapter_title = chapter['title']
                has_author_note = False
                if '_html' in chapter:
                    html_content = chapter['_html']
                    body_type = 'frontmatter toc'
                    # 插图页：把图片添加到 book
                    if chapter.get('_illust_path') and os.path.isfile(chapter['_illust_path']):
                        _ill_ext = os.path.splitext(chapter['_illust_path'])[1].lower()
                        _ill_mt = 'image/png' if _ill_ext == '.png' else 'image/jpeg'
                        with open(chapter['_illust_path'], 'rb') as _f:
                            book.add_item(epub.EpubItem(
                                uid=f"illust-{i}",
                                file_name=f"images/{chapter['_illust_name']}",
                                media_type=_ill_mt, content=_f.read(),
                            ))
                else:
                    main_content, note_body = EPUBGenerator._split_author_note(chapter['content'])
                    _use_dc = drop_cap and not _dc_applied[0] and chapter['title'] not in INTRO_TITLES
                    html_content = EPUBGenerator._chapter_to_html(
                        main_content, drop_cap=_use_dc, ch_idx=i,
                        inline_pats=_inline_pats, block_pats=_block_pats,
                    )
                    if _use_dc:
                        _dc_applied[0] = True
                    body_type = 'bodymatter chapter'
                    if note_body is not None:
                        has_author_note = True
                        note_html = EPUBGenerator._chapter_to_html(note_body) if note_body.strip() else ''
                        html_content += (
                            '\n<h2 id="author-note">作者有话要说</h2>\n' + note_html
                        )
                epub_chapter = epub.EpubHtml(title=chapter_title, file_name=f'chapter_{i+1:03d}.xhtml', lang='zh')
                # 头图（仅正文章节，按轮换索引选取）
                header_html = ''
                if _headers and '_html' not in chapter:
                    h_cfg = _headers[i % len(_headers)]
                    h_path = h_cfg.get('path', h_cfg) if isinstance(h_cfg, dict) else h_cfg
                    h_edge = h_cfg.get('edge', 'fade') if isinstance(h_cfg, dict) else 'fade'
                    h_name = f'header_{i % len(_headers)}.jpg'
                    if os.path.isfile(str(h_path)):
                        from header_image import make_header as _make_header
                        h_bytes = _make_header(str(h_path), h_edge)
                        if h_bytes:
                            h_item = epub.EpubItem(
                                uid=f'hdr-{i % len(_headers)}',
                                file_name=f'images/{h_name}',
                                media_type='image/jpeg', content=h_bytes,
                            )
                            book.add_item(h_item)
                            header_html = f'<div class="header-img"><img src="../images/{h_name}" alt=""/></div>\n'
                epub_chapter.content = (
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!DOCTYPE html>\n'
                    '<html xmlns="http://www.w3.org/1999/xhtml"'
                    ' xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh">\n'
                    '<head>\n'
                    '  <meta charset="UTF-8"/>\n'
                    f'  <title>{chapter_title}</title>\n'
                    '  <link rel="stylesheet" type="text/css" href="styles/style.css"/>\n'
                    '</head>\n'
                    f'<body epub:type="{body_type}">\n'
                    f'{header_html}'
                    '<div class="content">\n'
                    f'<h1>{chapter_title}</h1>\n'
                    f'{html_content}\n'
                    '</div>\n'
                    '</body>\n'
                    '</html>'
                ).encode('utf-8')
                book.add_item(epub_chapter)
                spine.append(epub_chapter)
                file_name = f'chapter_{i+1:03d}.xhtml'
                if chapter.get('_skip_ncx'):
                    pass
                elif has_volumes:
                    if EPUBGenerator._VOLUME_RE.match(chapter_title):
                        if _cur_vol_sec is not None:
                            toc.append((_cur_vol_sec, _cur_vol_children))
                        _cur_vol_sec = epub.Section(chapter_title, href=file_name)
                        _cur_vol_children = [epub.Link(file_name, chapter_title, f'ch{i+1}')]
                    else:
                        if has_author_note:
                            link = (epub.Section(chapter_title, href=file_name),
                                    [epub.Link(file_name, chapter_title, f'ch{i+1}'),
                                     epub.Link(f'{file_name}#author-note', '作者有话要说',
                                               f'ch{i+1}-note')])
                        else:
                            link = epub.Link(file_name, chapter_title, f'ch{i+1}')
                        if _cur_vol_sec is not None:
                            _cur_vol_children.append(link)
                        else:
                            toc.append(link)
                else:
                    if has_author_note:
                        toc.append((
                            epub.Section(chapter_title, href=file_name),
                            [
                                epub.Link(file_name, chapter_title, f'ch{i+1}'),
                                epub.Link(f'{file_name}#author-note', '作者有话要说', f'ch{i+1}-note'),
                            ]
                        ))
                    else:
                        toc.append(epub.Link(file_name, chapter_title, f'ch{i+1}'))

            if has_volumes and _cur_vol_sec is not None:
                toc.append((_cur_vol_sec, _cur_vol_children))
            book.add_item(epub.EpubNcx())
            book.add_item(epub.EpubNav())
            book.spine = spine
            book.toc = tuple(toc)

            if output_path is None:
                safe_book_title = re.sub(r'[<>:"/\\|?*]', '_', book_title)
                if txt_path:
                    output_dir = os.path.dirname(os.path.abspath(txt_path)) or '.'
                else:
                    output_dir = os.path.expanduser('~/.txt2epub/output')
                    os.makedirs(output_dir, exist_ok=True)
                output_path = os.path.join(output_dir, f"{safe_book_title}.epub")

            epub.write_epub(output_path, book, {})

            last_ch_title = chapters[-1]['title'] if chapters else '无'
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
