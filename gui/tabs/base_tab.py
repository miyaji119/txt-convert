"""标签页基类，提供通用组件构建方法"""

import os
import tkinter as tk
from tkinter import ttk, filedialog
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gui.app import TxtToEpubGUI


class BaseTab:
    """标签页基类，提供文件选择器和元数据输入等通用组件"""

    def __init__(self, parent, app: 'TxtToEpubGUI'):
        self.parent = parent
        self.app = app
        self.frame = ttk.Frame(parent, padding=16)

    # ------------------------------------------------------------------
    # 文件 / 目录选择器（含最近记录下拉）
    # ------------------------------------------------------------------
    def _build_file_selector(self, container, label_text, button_text,
                              file_mode=True, filetypes=None, callback=None):
        """构建文件/文件夹选择器，附带最近使用下拉菜单。

        Args:
            container:   父容器
            label_text:  标签文字
            button_text: 浏览按钮文字
            file_mode:   True=选择文件, False=选择文件夹
            filetypes:   文件类型过滤器（仅 file_mode=True 时生效）
            callback:    选择/更改路径后的回调 (path: str) -> None

        Returns:
            path_var: StringVar，包含当前选中路径
        """
        outer = ttk.Frame(container)
        outer.pack(fill='x', pady=(0, 4))

        # ── 第一行：标签 + 输入框 + 浏览按钮 ──────────────────────────
        row = ttk.Frame(outer)
        row.pack(fill='x')

        ttk.Label(row, text=label_text, width=10, anchor='w').pack(side='left')

        path_var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=path_var)
        entry.pack(side='left', fill='x', expand=True, padx=(4, 4))

        def _on_path_changed(*_):
            p = path_var.get().strip()
            if p and callback:
                callback(p)

        def _browse():
            if file_mode:
                default_ft = [("文本文件", "*.txt"), ("所有文件", "*")]
                p = filedialog.askopenfilename(
                    title=label_text,
                    filetypes=filetypes or default_ft
                )
            else:
                p = filedialog.askdirectory(title=label_text)
            if p:
                path_var.set(p)
                _on_path_changed()

        ttk.Button(row, text=button_text, command=_browse).pack(side='right')

        # ── 第二行：最近使用下拉 ──────────────────────────────────────
        recents = (self.app.config_get_recent_files()
                   if file_mode
                   else self.app.config_get_recent_dirs())

        if recents:
            recent_row = ttk.Frame(outer)
            recent_row.pack(fill='x', pady=(2, 0))

            ttk.Label(recent_row, text="最近:", width=10, anchor='w',
                      style='Muted.TLabel').pack(side='left')

            combo_var = tk.StringVar()
            combo = ttk.Combobox(
                recent_row,
                textvariable=combo_var,
                values=[os.path.basename(p) + f"  ({_rel_time(p)})" for p in recents],
                state='readonly',
                height=min(len(recents), 6),
            )
            combo.pack(side='left', fill='x', expand=True, padx=(4, 4))
            # 存完整路径供查找
            combo._recent_paths = recents

            def _on_combo_select(event, _combo=combo, _path_var=path_var):
                idx = _combo.current()
                if 0 <= idx < len(_combo._recent_paths):
                    _path_var.set(_combo._recent_paths[idx])
                    _combo.set('')          # 重置显示，保持输入框为选中路径
                    _on_path_changed()

            combo.bind('<<ComboboxSelected>>', _on_combo_select)

            # 清除按钮
            ttk.Label(recent_row, text="", width=1).pack(side='right')  # spacer

        return path_var

    # ------------------------------------------------------------------
    # 书名 / 作者输入
    # ------------------------------------------------------------------
    def _build_meta_input(self, container):
        """构建书名/作者输入框

        Returns:
            (title_var, author_var): 两个 StringVar
        """
        meta_frame = ttk.Frame(container)
        meta_frame.pack(fill='x', pady=(0, 8))

        ttk.Label(meta_frame, text="书名:", width=10, anchor='w').pack(side='left')
        title_var = tk.StringVar()
        ttk.Entry(meta_frame, textvariable=title_var).pack(
            side='left', fill='x', expand=True, padx=(4, 12))

        ttk.Label(meta_frame, text="作者:", width=8, anchor='w').pack(side='left')
        author_var = tk.StringVar()
        ttk.Entry(meta_frame, textvariable=author_var).pack(
            side='left', fill='x', expand=True, padx=(4, 0))

        return title_var, author_var


# ------------------------------------------------------------------
# 模块级辅助
# ------------------------------------------------------------------
def _rel_time(path: str) -> str:
    """返回文件修改时间的相对描述（今天 / N天前 / 更早）"""
    try:
        import time
        mtime = os.path.getmtime(path)
        diff = time.time() - mtime
        if diff < 86400:
            return "今天"
        elif diff < 86400 * 2:
            return "昨天"
        elif diff < 86400 * 7:
            return f"{int(diff // 86400)}天前"
        elif diff < 86400 * 30:
            return f"{int(diff // 86400 // 7)}周前"
        else:
            return "更早"
    except OSError:
        return ""
