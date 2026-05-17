#!/usr/bin/env python3
"""清理源文件中重复的章节标题（如"第XX章 第XX章 xxx"）"""

import re
import os
from encoding import EncodingDetector


def clean_duplicate_chapter_titles(input_file: str, output_file: str = None):
    """
    清理源文件中重复的章节标题
    
    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径，如果为None则覆盖原文件
    """
    # 读取文件
    content, encoding = EncodingDetector.read_file_with_auto_encoding(input_file)
    lines = content.split('\n')
    
    # 定义重复章节标题模式
    # 匹配"第X章 第X章 xxx"或"第X章第X章 xxx"格式
    patterns = [
        # 模式1: 第X章 第X章 xxx（带空格）
        (r'第([零一二三四五六七八九十百千万\d]+)章\s+第\1章\s*(.*)', r'第\1章 \2'),
        # 模式2: 第X章第X章 xxx（不带空格）
        (r'第([零一二三四五六七八九十百千万\d]+)章第\1章\s*(.*)', r'第\1章 \2'),
        # 模式3: 第X章 第X章（行尾）
        (r'第([零一二三四五六七八九十百千万\d]+)章\s+第\1章$', r'第\1章'),
        # 模式4: 第X章第X章（行尾）
        (r'第([零一二三四五六七八九十百千万\d]+)章第\1章$', r'第\1章'),
    ]
    
    cleaned_lines = []
    changes_count = 0
    
    for line in lines:
        original_line = line
        for pattern, replacement in patterns:
            line = re.sub(pattern, replacement, line)
        if line != original_line:
            changes_count += 1
            print(f'修复: {repr(original_line)} -> {repr(line)}')
        cleaned_lines.append(line)
    
    # 确定输出文件
    if output_file is None:
        output_file = input_file
    
    # 写入输出文件
    with open(output_file, 'w', encoding=encoding) as f:
        f.write('\n'.join(cleaned_lines))
    
    print(f'\n处理完成！共修复 {changes_count} 处重复章节标题')


def main():
    import argparse
    parser = argparse.ArgumentParser(description='清理源文件中重复的章节标题')
    parser.add_argument('input_file', help='输入文件路径')
    parser.add_argument('-o', '--output', help='输出文件路径（默认覆盖原文件）')
    args = parser.parse_args()
    
    clean_duplicate_chapter_titles(args.input_file, args.output)


if __name__ == '__main__':
    main()