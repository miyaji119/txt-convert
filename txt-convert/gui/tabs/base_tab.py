"""标签页基类，提供通用组件构建方法"""

import os
import tkinter as tk
from tkinter import filedialog
from typing import TYPE_CHECKING

import customtkinter as ctk
from gui.theme import get_ui_font

if TYPE_CHECKING:
    from gui.app import TxtToEpubGUI


class BaseTab:
    """标签页基类。

    _page  — 放入页面容器（由 app.py 通过 place 叠放）
    frame  — 带内边距的内容区（各 Tab 子类向此 frame pack 控件）
    """

    def __init__(self, parent, app: 'TxtToEpubGUI'):
        self.parent = parent
        self.app = app
        # 外层页面帧（供 app.py 的 place 管理）
        self._page = ctk.CTkFrame(parent, fg_color='transparent', corner_radius=0)
        # 带内边距的工作区（子类向此 pack 控件，等价于原 padding=16 的 ttk.Frame）
        self.frame = ctk.CTkFrame(self._page, fg_color='transparent', corner_radius=0)
        self.frame.pack(fill='both', expand=True, padx=16, pady=16)

    # ------------------------------------------------------------------
    # 文件 / 目录选择器（含最近记录下拉）
    # ------------------------------------------------------------------
    def _build_file_selector(self, container, label_text, button_text,
                              file_mode=True, filetypes=None, callback=None):
        """构建文件/文件夹选择器，附带最近使用下拉菜单。

        Returns:
            path_var (tk.StringVar) — 当前选中路径
        """
        outer = ctk.CTkFrame(container, fg_color='transparent')
        outer.pack(fill='x', pady=(0, 4))

        # ── 第一行：标签 + 输入框 + 浏览按钮 ──────────────────────────
        row = ctk.CTkFrame(outer, fg_color='transparent')
        row.pack(fill='x')

        ctk.CTkLabel(row, text=label_text, width=80, anchor='w',
                     font=get_ui_font(10)).pack(side='left')

        path_var = tk.StringVar()
        entry = ctk.CTkEntry(row, textvariable=path_var, font=get_ui_font(10))
        entry.pack(side='left', fill='x', expand=True, padx=(6, 6))

        def _on_path_changed(*_):
            p = path_var.get().strip()
            if p and callback:
                callback(p)

        def _browse():
            if file_mode:
                default_ft = [("文本文件", "*.txt"), ("所有文件", "*")]
                p = filedialog.askopenfilename(
                    title=label_text, filetypes=filetypes or default_ft)
            else:
                p = filedialog.askdirectory(title=label_text)
            if p:
                path_var.set(p)
                _on_path_changed()

        ctk.CTkButton(row, text=button_text, command=_browse,
                      width=80, font=get_ui_font(10)).pack(side='right')

        # ── 第二行：最近使用下拉 ──────────────────────────────────────
        recents = (self.app.config_get_recent_files()
                   if file_mode else self.app.config_get_recent_dirs())

        if recents:
            recent_row = ctk.CTkFrame(outer, fg_color='transparent')
            recent_row.pack(fill='x', pady=(3, 0))

            ctk.CTkLabel(recent_row, text="最近:", width=80, anchor='w',
                         font=get_ui_font(9),
                         text_color='#9ba8b7').pack(side='left')

            # 构建 显示名 → 完整路径 的映射
            path_map = {
                os.path.basename(p) + f"  ({_rel_time(p)})": p
                for p in recents
            }

            def _on_combo_select(value,
                                  _path_var=path_var,
                                  _combo_ref=[None],
                                  _map=path_map):
                real_path = _map.get(value)
                if real_path:
                    _path_var.set(real_path)
                    if _combo_ref[0] is not None:
                        _combo_ref[0].set('')
                    _on_path_changed()

            combo = ctk.CTkComboBox(
                recent_row,
                values=list(path_map.keys()),
                font=get_ui_font(9),
                command=_on_combo_select,
                state='readonly',
            )
            combo.set('')
            combo.pack(side='left', fill='x', expand=True, padx=(6, 0))
            # 通过闭包传回 combo 引用，让回调可以 reset 显示
            _on_combo_select.__defaults__[2][0] = combo  # type: ignore[index]

        return path_var

    # ------------------------------------------------------------------
    # 书名 / 作者输入
    # ------------------------------------------------------------------
    def _build_meta_input(self, container):
        """构建书名/作者输入框

        Returns:
            (title_var, author_var): 两个 tk.StringVar
        """
        meta_frame = ctk.CTkFrame(container, fg_color='transparent')
        meta_frame.pack(fill='x', pady=(0, 8))

        ctk.CTkLabel(meta_frame, text="书名:", width=60,
                     anchor='w', font=get_ui_font(10)).pack(side='left')
        title_var = tk.StringVar()
        ctk.CTkEntry(meta_frame, textvariable=title_var,
                     font=get_ui_font(10)).pack(
            side='left', fill='x', expand=True, padx=(6, 12))

        ctk.CTkLabel(meta_frame, text="作者:", width=50,
                     anchor='w', font=get_ui_font(10)).pack(side='left')
        author_var = tk.StringVar()
        ctk.CTkEntry(meta_frame, textvariable=author_var,
                     font=get_ui_font(10)).pack(
            side='left', fill='x', expand=True, padx=(6, 0))

        return title_var, author_var

    # ------------------------------------------------------------------
    # 带标题的分区帧（ttk.LabelFrame 等价物）
    # ------------------------------------------------------------------
    def _section(self, container, title, **pack_kwargs):
        """创建带标题的圆角卡片帧，返回内容区。

        用法：
            inner = self._section(self.frame, "结果")
            some_widget.pack(master=inner, ...)
        """
        card = ctk.CTkFrame(container, corner_radius=8)
        card.pack(**{'fill': 'x', 'pady': (4, 0), **pack_kwargs})
        ctk.CTkLabel(card, text=f" {title} ",
                     text_color='#9ba8b7', font=get_ui_font(9)).pack(
            anchor='nw', padx=10, pady=(6, 2))
        inner = ctk.CTkFrame(card, fg_color='transparent')
        inner.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        return inner


# ------------------------------------------------------------------
# 模块级辅助
# ------------------------------------------------------------------
def _rel_time(path: str) -> str:
    """返回文件修改时间的相对描述"""
    try:
        import time
        diff = time.time() - os.path.getmtime(path)
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
