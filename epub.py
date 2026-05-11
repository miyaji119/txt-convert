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
        (r'^[=]+第(\d+)章\s*(.*?)[=]*$', 'equals'),
        (r'^第([零一二三四五六七八九十百千万\d]+)章\s*(.*)$', 'chinese'),
        (r'^(攻)?第([零一二三四五六七八九十百千万\d]+)章\s*(.*)$', 'prefix'),
        (r'^\d+、第([零一二三四五六七八九十百千万\d]+)章\s*(.*)$', 'number_chinese'),
        (r'^\d+、番外(.*)$', 'number_fanwai'),
        (r'^番外([零一二三四五六七八九十百千万\d]+)(.*)$', 'fanwai'),
        (r'^(\d+)、(.*)$', 'simple_number'),
        (r'^楔子\s*(.*)$', 'xiezi'),
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
        patterns = [
            r'《([^》]+)》作者', r'《([^》]+)》', r'书名[：:]\s*([^\n]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                title = match.group(1).strip() if match.group(1) else (match.group(2).strip() if match.group(2) else None)
                if title:
                    title = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', '', title).strip()
                    if title:
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
                        if re.match(pattern, stripped):
                            is_chapter = True
                            in_intro = False
                            break
                    if not is_chapter:
                        intro_lines.append(line)
                        continue

            chapter_num = None
            chapter_title = ""
            for pattern, ptype in EPUBGenerator.CHAPTER_PATTERNS:
                match = re.match(pattern, stripped)
                if match:
                    if ptype == 'equals':
                        chapter_num = int(match.group(1))
                        title_part = match.group(2).strip()
                        chapter_title = f"第{chapter_num}章 {title_part}" if title_part else f"第{chapter_num}章"
                    elif ptype == 'chinese':
                        chapter_num = EPUBGenerator._normalize_chapter_num(match.group(1))
                        title_part = match.group(2).strip()
                        chapter_title = f"第{chapter_num}章 {title_part}" if title_part else f"第{chapter_num}章"
                    elif ptype == 'prefix':
                        chapter_num = EPUBGenerator._normalize_chapter_num(match.group(2))
                        title_part = match.group(3).strip()
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
                        chapter_title = f"第{chapter_num}章 {title_part}" if title_part else f"第{chapter_num}章"
                    elif ptype == 'number_fanwai':
                        chapter_num = 999
                        chapter_title = f"番外 {match.group(1).strip()}" if match.group(1).strip() else "番外"
                    elif ptype == 'fanwai':
                        chapter_num = 999
                        fanwai_num = EPUBGenerator._normalize_chapter_num(match.group(1))
                        fanwai_rest = match.group(2).strip()
                        chapter_title = f"番外{fanwai_num}{fanwai_rest}" if fanwai_rest else f"番外{fanwai_num}"
                    break

            if chapter_num is not None:
                if not EPUBGenerator._is_valid_chapter_number(chapter_num, current_title is None):
                    continue
                if current_title and current_lines:
                    chapters.append({'title': current_title, 'content': '\n'.join(current_lines)})
                if current_title is None and intro_lines:
                    chapters.insert(0, {'title': '前言', 'content': '\n'.join(intro_lines)})
                    intro_lines = []
                current_title = chapter_title
                current_lines = []
            elif current_title:
                current_lines.append(line)

        if current_title and current_lines:
            chapters.append({'title': current_title, 'content': '\n'.join(current_lines)})
        return chapters

    @staticmethod
    def _chapter_to_html(content: str) -> str:
        paragraphs = []
        for line in content.split('\n'):
            line = line.strip()
            if line:
                for old, new in [('&', '&amp;'), ('<', '&lt;'), ('>', '&gt;'), ('"', '&quot;'), ("'", '&#39;')]:
                    line = line.replace(old, new)
                paragraphs.append(f'<p>{line}</p>')
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
