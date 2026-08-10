"""TXT 转 EPUB 工具 - GUI 包

使用方式：
    python3 -m gui           # 作为模块运行
    python3 gui.py           # 通过兼容入口运行
"""

import os
import sys

# 将上级目录（txt-convert/）加入 sys.path，确保能导入 encoding/epub 等模块
_PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

import tkinter as tk

from gui.app import TxtToEpubGUI
from gui.constants import APP_VERSION, APP_TITLE, EPUB_SUPPORT

__all__ = ['main', 'TxtToEpubGUI', 'APP_VERSION', 'APP_TITLE', 'EPUB_SUPPORT']


def main():
    """启动 GUI 应用"""
    root = tk.Tk()
    app = TxtToEpubGUI(root)

    # 窗口居中
    root.update_idletasks()
    w = root.winfo_width()
    h = root.winfo_height()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    root.protocol("WM_DELETE_WINDOW", app._on_close)
    root.mainloop()
