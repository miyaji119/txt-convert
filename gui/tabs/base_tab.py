"""标签页基类，提供通用组件构建方法"""

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

    def _build_file_selector(self, container, label_text, button_text,
                              file_mode=True, filetypes=None, callback=None):
        """构建文件/文件夹选择器

        Args:
            container: 父容器
            label_text: 标签文字
            button_text: 按钮文字
            file_mode: True=选择文件, False=选择文件夹
            filetypes: 文件类型过滤器（仅 file_mode=True 时生效）
            callback: 选择后的回调函数

        Returns:
            path_var: StringVar，包含选中的路径
        """
        row = ttk.Frame(container)
        row.pack(fill='x', pady=(0, 8))

        ttk.Label(row, text=label_text, width=10, anchor='w').pack(side='left')
        path_var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=path_var)
        entry.pack(side='left', fill='x', expand=True, padx=(4, 4))

        def _browse():
            if file_mode:
                # macOS Tk 不支持 *.* 和带通配符的扩展名，使用兼容格式
                default_filetypes = [("文本文件", "*.txt"), ("所有文件", "*")]
                path = filedialog.askopenfilename(
                    title=label_text,
                    filetypes=filetypes or default_filetypes
                )
            else:
                path = filedialog.askdirectory(title=label_text)
            if path:
                path_var.set(path)
                if callback:
                    callback(path)

        ttk.Button(row, text=button_text, command=_browse).pack(side='right')
        return path_var

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
