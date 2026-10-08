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

    # 对话引号识别：中文 "..." 和角括号 「...」 『...』
    _DLG_PATS = [
        (re.compile(r'“[^”]{0,400}”'), 'dlg-cn'),
        (re.compile(r'「[^」]{0,400}」'), 'dlg-sq'),
        (re.compile(r'『[^』]{0,400}』'), 'dlg-sq'),
    ]

    _TOC_PAGE_SIZE = 20

    _VOLUME_RE = re.compile(
        r'^(第[零一二三四五六七八九十百千万两\d]+卷|卷[零一二三四五六七八九十百千万两\d]|[上中下]卷)'
    )

    _CSS_TEMPLATE = (
        '@charset "UTF-8";'
        'body{{font-family:"Noto Serif CJK SC","Source Han Serif SC","思源宋体","STSong","SimSun","宋体",serif;'
        'font-size:1em;margin:{margin};color:#1c1c1c;word-break:break-all;overflow-wrap:break-word;'
        '-webkit-hyphens:none;hyphens:none}}'
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
    )

    @classmethod
    def _build_css(cls, margin: str = "0 4%", line_height: float = 1.8,
                   text_indent: str = "2em", custom_css: str = "") -> str:
        css = cls._CSS_TEMPLATE.format(
            margin=margin, line_height=line_height, text_indent=text_indent
        )
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
    def _apply_dialogue_spans(text: str) -> str:
        """将对话引号内容包裹在 span 中，供 CSS 自定义样式。"""
        for pat, cls in EPUBGenerator._DLG_PATS:
            text = pat.sub(lambda m, c=cls: f'<span class="{c}">{m.group(0)}</span>', text)
        return text

    @staticmethod
    def _parse_chapters(content: str) -> List[dict]:
        """解析章节结构（使用 ChapterAnalyzer 统一识别）"""
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

    @staticmethod
    def _chapter_to_html(content: str) -> str:
        content = EPUBGenerator._clean_chapter_content(content)
        content = EPUBGenerator._merge_dialogue_splits(content)
        paragraphs = []
        current = []

        def _flush():
            if not current:
                return
            text = ''.join(current)
            stripped = text.strip()
            if EPUBGenerator._SCENE_BREAK_PAT.match(stripped) and stripped:
                paragraphs.append(f'<p class="scene-break">{html.escape(stripped)}</p>')
            else:
                paragraphs.append(f'<p>{EPUBGenerator._apply_dialogue_spans(text)}</p>')
            current.clear()

        for line in content.split('\n'):
            line = line.strip()
            if line:
                current.append(html.escape(line, quote=True))
            else:
                _flush()
        _flush()
        return '\n'.join(paragraphs)

    @staticmethod
    def txt_to_epub(txt_path: str, output_path: str = None, book_title: str = "", author: str = "",
                    cover_image: str = None, auto_search_cover: bool = False, cover_url: str = None,
                    description: str = "", publisher: str = "",
                    margin: str = "0 4%", line_height: float = 1.8,
                    text_indent: str = "2em", custom_css: str = "") -> Optional[str]:
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
            if description:
                book.add_metadata('DC', 'description', description)
            if publisher:
                book.add_metadata('DC', 'publisher', publisher)

            # 封面处理
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
                ).encode('utf-8'),
            )
            book.add_item(css_item)
            for i, chapter in enumerate(chapters):
                chapter_title = chapter['title']
                has_author_note = False
                if '_html' in chapter:
                    html_content = chapter['_html']
                    body_type = 'frontmatter toc'
                else:
                    main_content, note_body = EPUBGenerator._split_author_note(chapter['content'])
                    html_content = EPUBGenerator._chapter_to_html(main_content)
                    body_type = 'bodymatter chapter'
                    if note_body is not None:
                        has_author_note = True
                        note_html = EPUBGenerator._chapter_to_html(note_body) if note_body.strip() else ''
                        html_content += (
                            '\n<h2 id="author-note">作者有话要说</h2>\n' + note_html
                        )
                epub_chapter = epub.EpubHtml(title=chapter_title, file_name=f'chapter_{i+1:03d}.xhtml', lang='zh')
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
                    f'<h1>{chapter_title}</h1>\n'
                    f'{html_content}\n'
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
                output_dir = os.path.dirname(os.path.abspath(txt_path)) or '.'
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
