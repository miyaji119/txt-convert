"""目录显示模块"""

import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from encoding import EncodingDetector
from chapter import ChapterAnalyzer


class DirectoryDisplay:
    """目录展示器"""

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    @staticmethod
    def get_file_type(path: Path) -> str:
        """获取文件类型描述"""
        suffix = path.suffix.lower()
        types = {
            '.txt': '文本文件',
            '_epub_ready.txt': 'EPUB优化文本文件',
            '.epub': '电子书文件',
            '.json': 'JSON配置文件',
        }
        return types.get(suffix, '未知文件')

    @staticmethod
    def display_file_tree(filepath: str, max_depth: int = 3) -> str:
        """显示文件树结构"""
        path = Path(filepath)
        tree_lines = []

        if path.is_file():
            tree_lines.append(f"📄 {path.name}")
            tree_lines.append(f"   ├── 位置: {path.parent}")
            tree_lines.append(f"   ├── 大小: {DirectoryDisplay.format_size(path.stat().st_size)}")
            tree_lines.append(f"   ├── 修改时间: {datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
            tree_lines.append(f"   └── 类型: {DirectoryDisplay.get_file_type(path)}")
        else:
            tree_lines.append(f"📁 {path.name}")
            extensions = {'.txt', '_epub_ready.txt', '.epub', '.json'}
            items = [item for item in path.iterdir()
                     if item.is_file() and item.suffix in extensions or item.is_dir()]
            items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))

            for i, item in enumerate(items[:20]):
                is_last = (i == len(items) - 1) or (i == 19 and len(items) > 20)
                prefix = "    └── " if is_last else "    ├── "
                if item.is_dir():
                    tree_lines.append(f"{prefix}📁 {item.name}/")
                else:
                    size = DirectoryDisplay.format_size(item.stat().st_size)
                    tree_lines.append(f"{prefix}📄 {item.name} ({size})")

            if len(items) > 20:
                tree_lines.append(f"    └── ... 还有 {len(items) - 20} 个文件")

        return '\n'.join(tree_lines)

    @staticmethod
    def display_chapter_catalog(filepath: str, max_chapters: int = 20) -> str:
        """显示章节目录"""
        try:
            content, encoding = EncodingDetector.read_file_with_auto_encoding(filepath)
        except Exception as e:
            return f"无法读取文件内容: {e}"

        structure = ChapterAnalyzer.analyze_chapter_structure(content)
        output_lines = [
            f"文件: {os.path.basename(filepath)}",
            "=" * 60,
            f"总章节数: {structure['total_chapters']}",
            f"总行数: {structure['total_lines']:,}",
            f"总字数: {structure['total_chars']:,}",
            "-" * 60,
            "章节目录:",
        ]

        if structure['chapters']:
            for i, chapter in enumerate(structure['chapters'][:max_chapters]):
                lines_per_chapter = chapter['line_count']
                chars_per_chapter = chapter['char_count']
                progress = chars_per_chapter / structure['total_chars'] * 50 if structure['total_chars'] > 0 else 0
                progress_bar = "█" * int(progress) + "░" * (50 - int(progress))

                output_lines.append(f"  {chapter['number']:3d}. {chapter['title']}")
                output_lines.append(f"       行号: {chapter['start_line']:4d}-{chapter['end_line']:<4d} "
                                   f"行数: {lines_per_chapter:4d} 字数: {chars_per_chapter:6,}")
                output_lines.append(f"       [{progress_bar}] {progress*2:.1f}%")
                output_lines.append("")

            if len(structure['chapters']) > max_chapters:
                output_lines.append(f"  ... 还有 {len(structure['chapters']) - max_chapters} 个章节未显示")
        else:
            output_lines.append("未检测到标准章节格式")

        return '\n'.join(output_lines)

    @staticmethod
    def display_batch_summary(results: List[Dict], output_dir: str) -> str:
        """显示批量处理摘要"""
        output_lines = [
            "📊 批量处理摘要",
            "=" * 60,
            f"处理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"输出目录: {output_dir}",
            f"处理文件数: {len(results)}",
            "",
        ]

        total_size = 0
        total_chapters = 0

        for i, result in enumerate(results, 1):
            if 'error' in result:
                status = "❌ 失败"
                details = result['error']
            else:
                status = "✅ 成功"
                details = f"大小: {DirectoryDisplay.format_size(result.get('size', 0))}"
                if 'chapters' in result:
                    details += f", 章节: {result['chapters']}个"
                    total_chapters += result['chapters']
                total_size += result.get('size', 0)

            filename = result.get('filename', '未知文件')
            output_lines.extend([f"{i:2d}. {filename}", f"    状态: {status}", f"    详情: {details}", ""])

        if total_chapters > 0:
            output_lines.append(f"总计章节数: {total_chapters:,} 个")
        output_lines.append(f"总计文件大小: {DirectoryDisplay.format_size(total_size)}")

        return '\n'.join(output_lines)
