"""TXT 转 EPUB 工具 - GUI 包"""

import os
import sys

_PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

# 必须在创建根窗口前导入（内部调用 ctk.set_appearance_mode 等）
import gui.theme  # noqa: F401

import customtkinter as ctk
from gui.app import TxtToEpubGUI
from gui.constants import APP_VERSION, APP_TITLE, EPUB_SUPPORT

__all__ = ['main', 'TxtToEpubGUI', 'APP_VERSION', 'APP_TITLE', 'EPUB_SUPPORT']


def main():
    """启动 GUI 应用"""
    root = ctk.CTk()
    app = TxtToEpubGUI(root)

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
