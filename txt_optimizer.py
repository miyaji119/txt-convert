#!/usr/bin/env python3
"""TXT转EPUB优化工具

使用方法:
    python3 txt_optimizer.py --convert <文件路径>     转换单个文件
    python3 txt_optimizer.py --batch <文件夹路径>    批量转换
    python3 txt_optimizer.py --epub <文件路径>        生成EPUB
    python3 txt_optimizer.py --tree <路径>           显示目录结构
    python3 txt_optimizer.py --catalog <文件路径>    显示章节目录
"""

import os
import sys
import argparse

from encoding import EncodingDetector
from display import DirectoryDisplay
from easypub import EasyPubOptimizer, convert_for_easypub, batch_convert_for_easypub
from epub import EPUBGenerator

try:
    from ebooklib import epub
    EPUB_SUPPORT = True
except ImportError:
    EPUB_SUPPORT = False


def print_guide():
    guide = """
📖 TXT转EPUB优化工具 - 使用指南
===================================================

【功能】
  • 标准化章节标题格式
  • 支持多种章节格式（第X章、Chapter X、卷等）
  • 智能段落合并与分隔
  • 自动生成EPUB元数据
  • 支持批量处理
  • 封面搜索与下载

【命令行用法】
  1. 转换单个文件（生成*_epub_ready.txt）
     $ python3 txt_optimizer.py --convert ~/books/novel.txt

  2. 批量转换文件夹
     $ python3 txt_optimizer.py --batch ~/books/

  3. 生成EPUB文件
     $ python3 txt_optimizer.py --epub ~/books/novel_epub_ready.txt

  4. 显示目录结构
     $ python3 txt_optimizer.py --tree ~/books/

  5. 查看章节目录
     $ python3 txt_optimizer.py --catalog ~/books/novel.txt

【交互模式】
  $ python3 txt_optimizer.py

【EPUB封面选项】
  • 不使用封面
  • 指定本地封面图片路径
  • 自动从网上搜索封面（推荐）

【安装依赖】
  $ pip install ebooklib pillow requests

===================================================
"""
    print(guide)


def main():
    parser = argparse.ArgumentParser(description='TXT转EPUB优化工具')
    parser.add_argument('--convert', help='转换单个文件为EasyPub友好格式')
    parser.add_argument('--batch', help='批量转换文件夹内的所有txt文件')
    parser.add_argument('--epub', help='将优化后的TXT文件转换为EPUB')
    parser.add_argument('--tree', help='显示文件或目录结构')
    parser.add_argument('--catalog', help='显示TXT文件的章节目录')
    parser.add_argument('--guide', action='store_true', help='显示使用指南')
    parser.add_argument('--author', help='指定作者名')
    parser.add_argument('--title', help='指定书名')
    parser.add_argument('--cover', help='指定封面图片路径')
    parser.add_argument('--cover-url', help='指定封面图片URL')
    parser.add_argument('--auto-cover', action='store_true', help='自动搜索封面')

    args = parser.parse_args()

    if args.guide:
        print_guide()
        return

    if args.tree:
        if os.path.exists(args.tree):
            print(DirectoryDisplay.display_file_tree(args.tree))
            if os.path.isfile(args.tree) and args.tree.endswith('.txt'):
                catalog = input("\n是否显示章节目录? (y/n): ").strip().lower()
                if catalog == 'y':
                    print(DirectoryDisplay.display_chapter_catalog(args.tree))
        else:
            print("❌ 路径不存在！")
        return

    if args.catalog:
        if os.path.exists(args.catalog):
            print(DirectoryDisplay.display_chapter_catalog(args.catalog))
        else:
            print("❌ 文件不存在！")
        return

    if args.convert:
        if not os.path.exists(args.convert):
            print("❌ 文件不存在！")
            return

        filepath = args.convert
        print("\n📄 原文件信息:")
        print(DirectoryDisplay.display_file_tree(filepath))

        book_title = ""
        author = ""

        if not args.title or not args.author:
            try:
                from encoding import EncodingDetector
                content, _ = EncodingDetector.read_file_with_auto_encoding(filepath)
                
                if not args.title:
                    book_title = EPUBGenerator._extract_title(content)
                    if book_title:
                        print(f"   从内容中提取书名: {book_title}")
                
                if not args.author:
                    author = EPUBGenerator._extract_author(content)
                    if author:
                        print(f"   从内容中提取作者: {author}")
            except Exception as e:
                print(f"   ⚠️ 自动提取元数据失败: {e}")

        if not book_title:
            default_title = os.path.splitext(os.path.basename(filepath))[0]
            book_title = args.title or input(f"\n请输入书名 (默认: {default_title}): ").strip() or default_title
        
        if not author:
            author = args.author or input("请输入作者 (默认: 未知): ").strip() or "未知"

        output_file, analysis = convert_for_easypub(filepath, None, book_title, author, show_catalog=True)
        if output_file:
            print("\n" + "=" * 60)
            print("✅ 转换完成!")
            print(f"   输出文件: {output_file}")
            print("\n📄 输出文件信息:")
            print(DirectoryDisplay.display_file_tree(output_file))

            open_dir = input("\n是否打开文件所在目录? (y/n, 默认n): ").strip().lower()
            if open_dir == 'y':
                dir_path = os.path.dirname(output_file)
                if sys.platform == 'darwin':
                    os.system(f'open "{dir_path}"')
                elif sys.platform == 'win32':
                    os.startfile(dir_path)
                else:
                    os.system(f'xdg-open "{dir_path}"')
        return

    if args.batch:
        if not os.path.isdir(args.batch):
            print("❌ 文件夹不存在！")
            return

        print("\n📁 原目录结构:")
        print(DirectoryDisplay.display_file_tree(args.batch))

        confirm = input(f"\n确认批量转换 {args.batch} 下的所有txt文件? (y/n): ").strip().lower()
        if confirm != 'y':
            print("已取消")
            return

        results = batch_convert_for_easypub(args.batch, None, None, show_summary=True)
        if results:
            print(f"\n✅ 批量转换完成！共处理 {len(results)} 个文件")
        return

    if args.epub:
        if not EPUB_SUPPORT:
            print("❌ EPUB生成功能不可用，请先安装ebooklib库:")
            print("   pip install ebooklib")
            return

        if not os.path.exists(args.epub):
            print("❌ 文件不存在！")
            return

        print("\n📄 源文件信息:")
        print(DirectoryDisplay.display_file_tree(args.epub))

        book_title = args.title if args.title else ""
        author = args.author if args.author else ""

        cover_image = args.cover
        auto_search = args.auto_cover
        cover_url_input = args.cover_url

        if not cover_image and not auto_search and not cover_url_input:
            print("\n封面选项:")
            print("  1. 不使用封面")
            print("  2. 指定本地封面图片路径")
            print("  3. 指定封面图片URL")
            print("  4. 自动从网上搜索封面（推荐）")
            cover_option = input("请选择 (1-4, 默认4): ").strip()
            if cover_option == '2':
                cover_image = input("请输入封面图片路径: ").strip()
                if cover_image and not os.path.exists(cover_image):
                    print("⚠️ 封面图片不存在，将跳过")
                    cover_image = None
            elif cover_option == '3':
                cover_url_input = input("请输入封面图片URL: ").strip()
            elif cover_option == '1':
                pass
            else:
                auto_search = True

        epub_path = EPUBGenerator.txt_to_epub(args.epub, None, book_title, author, cover_image, auto_search, cover_url_input)
        if epub_path:
            print("\n📄 EPUB文件信息:")
            print(DirectoryDisplay.display_file_tree(epub_path))

            open_dir = input("\n是否打开文件所在目录? (y/n, 默认n): ").strip().lower()
            if open_dir == 'y':
                dir_path = os.path.dirname(epub_path)
                if sys.platform == 'darwin':
                    os.system(f'open "{dir_path}"')
                elif sys.platform == 'win32':
                    os.startfile(dir_path)
                else:
                    os.system(f'xdg-open "{dir_path}"')
        return

    print_guide()
    print("\n请使用 --help 查看命令行参数")
    print("或直接运行 python3 txt_optimizer.py 进入交互模式\n")


if __name__ == '__main__':
    main()