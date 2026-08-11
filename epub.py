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

    @staticmethod
    def _parse_chapters(content: str) -> List[dict]:
        """解析章节结构（使用 ChapterAnalyzer 统一识别）"""
        structure = ChapterAnalyzer.analyze_chapter_structure(content)
        lines = content.split('\n')
        chapters = []

        def _skip_comment(line: str) -> bool:
            return line.strip().startswith('<!--') or line.strip().startswith('-->')

        # 提取前言（第一个章节之前的内容）
        if structure['chapters']:
            first_start = structure['chapters'][0]['start_line'] - 1
            intro_lines = []
            in_intro = False
            for line in lines[:first_start]:
                if _skip_comment(line):
                    continue
                stripped = line.strip()
                if any(m in stripped for m in EPUBGenerator.INTRO_MARKERS):
                    in_intro = True
                if in_intro or intro_lines:
                    intro_lines.append(line)
            if intro_lines:
                chapters.append({'title': '前言', 'content': '\n'.join(intro_lines)})

        # 提取各章节内容
        for ch in structure['chapters']:
            start = ch['start_line'] - 1
            end = ch['end_line']
            chapter_lines = [line for line in lines[start:end] if not _skip_comment(line)]
            chapters.append({'title': ch['title'], 'content': '\n'.join(chapter_lines)})

        if not chapters:
            chapters = [{'title': '正文', 'content': content}]

        return chapters

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
        paragraphs = []
        current = []
        for line in content.split('\n'):
            line = line.strip()
            if line:
                current.append(html.escape(line, quote=True))
            else:
                if current:
                    paragraphs.append(f'<p>{" ".join(current)}</p>')
                    current = []
        if current:
            paragraphs.append(f'<p>{" ".join(current)}</p>')
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

            # 生成章节
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
