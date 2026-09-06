"""单文件转换 Tab"""

import os
import tkinter as tk

import customtkinter as ctk

from gui.tabs.base_tab import BaseTab
from gui.theme import get_ui_font
from config import config
from encoding import EncodingDetector
from display import DirectoryDisplay
from easypub import convert_for_easypub
from epub import EPUBGenerator


class ConvertTab(BaseTab):
    """单文件转换：将单个 TXT 转为 EPUB-ready 格式"""

    def __init__(self, parent, app):
        super().__init__(parent, app)

        ctk.CTkLabel(self.frame,
                     text="将单个 TXT 文件转换为 EPUB-ready 格式（标准化章节标题、合并段落）",
                     text_color='#9ba8b7', font=get_ui_font(9)).pack(
            anchor='w', pady=(0, 12))

        self.path_var = self._build_file_selector(
            self.frame, "TXT 文件:", "浏览...",
            file_mode=True, callback=self._on_file_selected,
        )

        self.title_var, self.author_var = self._build_meta_input(self.frame)

        # 选项
        opt_frame = ctk.CTkFrame(self.frame, fg_color='transparent')
        opt_frame.pack(fill='x', pady=(0, 8))
        self.show_catalog_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(opt_frame, text="转换后显示章节目录",
                        variable=self.show_catalog_var,
                        font=get_ui_font(10)).pack(side='left')

        # 操作按钮
        btn_frame = ctk.CTkFrame(self.frame, fg_color='transparent')
        btn_frame.pack(fill='x', pady=(12, 0))
        self.convert_btn = ctk.CTkButton(
            btn_frame, text="▶ 开始转换",
            font=get_ui_font(10, 'bold'),
            command=self._start_convert,
        )
        self.convert_btn.pack(side='left')

        # 文件信息展示区
        info_inner = self._section(self.frame, "文件信息",
                                   fill='both', expand=True, pady=(12, 0))
        self.info_text = ctk.CTkTextbox(
            info_inner, height=160, wrap='word',
            font=('Consolas', 10),
            fg_color='#1a1a2e', text_color='#dce4ee',
            border_width=0,
        )
        self.info_text.pack(fill='both', expand=True)
        self.info_text.configure(state='disabled')

    def set_file_path(self, path: str):
        self.path_var.set(path)
        self._on_file_selected(path)

    def _on_file_selected(self, path: str):
        if not os.path.isfile(path):
            return
        config.add_recent_file(path)
        try:
            content, _ = EncodingDetector.read_file_with_auto_encoding(path)
            title = EPUBGenerator._extract_title(content) or ""
            author = EPUBGenerator._extract_author(content) or ""
            self.title_var.set(title or os.path.splitext(os.path.basename(path))[0])
            if author:
                self.author_var.set(author)

            info = DirectoryDisplay.display_file_tree(path)
            self.info_text.configure(state='normal')
            self.info_text.delete('1.0', 'end')
            self.info_text.insert('1.0', info)
            self.info_text.configure(state='disabled')
        except Exception as e:
            print(f"⚠️ 读取文件失败: {e}")

    def _start_convert(self):
        path = self.path_var.get().strip()
        if not path:
            from tkinter import messagebox
            messagebox.showwarning("提示", "请先选择 TXT 文件")
            return
        if not os.path.isfile(path):
            from tkinter import messagebox
            messagebox.showerror("错误", f"文件不存在: {path}")
            return

        title = self.title_var.get().strip()
        author = self.author_var.get().strip()

        _IDLE = "▶ 开始转换"
        self.app.set_btn_working(self.convert_btn, True, _IDLE, "⏳ 转换中…")
        self.app.set_status("正在转换...")

        def _task():
            return convert_for_easypub(path, None, title, author,
                                        show_catalog=self.show_catalog_var.get())

        def _on_complete(result):
            output_file, analysis = result
            if output_file:
                self.app.set_output_file(output_file)
                print(f"\n✅ 转换完成！\n   输出: {output_file}")
                if analysis:
                    print(f"   章节数: {analysis.get('total_chapters', 0)}")
                    print(f"   字数: {analysis.get('total_chars', 0):,}")
                self.app.flash_btn_done(self.convert_btn, _IDLE, success=True)
                self.app.set_nav_badge(0, '✓', '#86efac')
                from tkinter import messagebox
                messagebox.showinfo("成功", f"转换完成！\n输出文件:\n{output_file}")
            else:
                self.app.flash_btn_done(self.convert_btn, _IDLE, success=False)
                self.app.set_nav_badge(0, '✗', '#fca5a5')

        def _on_error(e):
            self.app.flash_btn_done(self.convert_btn, _IDLE, success=False)
            self.app.set_nav_badge(0, '✗', '#fca5a5')

        self.app.run_task(_task, on_complete=_on_complete, on_error=_on_error)
