#!/usr/bin/env python3
"""CLI 入口：txt/epub → 精排 EPUB

用法:
    python3 cli.py <input.txt> [--title 书名] [--author 作者] [--cover cover.jpg]
                   [--no-ads] [--no-punct] [--epub-only] [--txt-only]

依赖: fastapi, uvicorn, ebooklib（仅 --txt-only 以外时需要）
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from easypub import convert_for_easypub
from consistency import ContentMismatchError


def main():
    p = argparse.ArgumentParser(description="网文 txt → 精排 EPUB")
    p.add_argument("input", help="输入文件路径（.txt 或 .epub）")
    p.add_argument("--title",     default="", help="书名（不填则自动提取）")
    p.add_argument("--author",    default="", help="作者（不填则自动提取）")
    p.add_argument("--cover",     default=None, help="封面图片路径")
    p.add_argument("--no-ads",    action="store_true", help="跳过广告过滤")
    p.add_argument("--no-punct",  action="store_true", help="跳过标点规范化")
    p.add_argument("--txt-only",  action="store_true", help="只输出 epub_ready.txt，不生成 EPUB")
    p.add_argument("--ignore-mismatch", action="store_true", help="忽略跨章节内容不一致错误")
    args = p.parse_args()

    if not os.path.isfile(args.input):
        print(f"❌ 文件不存在: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        txt_out, analysis = convert_for_easypub(
            args.input,
            book_title=args.title,
            author=args.author,
            filter_ads=not args.no_ads,
            normalize_punct=not args.no_punct,
            ignore_mismatch=args.ignore_mismatch,
        )
    except ContentMismatchError as e:
        print(f"\n⚠️  内容不一致: {e}", file=sys.stderr)
        print("  可以用 --ignore-mismatch 跳过此检查", file=sys.stderr)
        sys.exit(2)

    if not txt_out:
        print("❌ 转换失败，请检查上方日志", file=sys.stderr)
        sys.exit(1)

    if args.txt_only:
        print(f"\n✅ epub_ready.txt 已生成: {txt_out}")
        return

    try:
        from epub import EPUBGenerator
    except ImportError:
        print("❌ 缺少 ebooklib，请 pip install ebooklib", file=sys.stderr)
        sys.exit(1)

    epub_path = EPUBGenerator.txt_to_epub(
        txt_out, None,
        args.title, args.author,
        args.cover, False, None,
    )

    if epub_path:
        print(f"\n✅ EPUB 已生成: {epub_path}")
        print(f"   章节数: {analysis.get('total_chapters', '?')}")
        print(f"   字数:   {analysis.get('total_chars', 0):,}")
    else:
        print("❌ EPUB 生成失败", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
