"""主 GUI 应用类：TxtToEpubGUI"""

import os
import sys
import queue
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk

from gui.constants import APP_VERSION, APP_TITLE, EPUB_SUPPORT
from gui.theme import setup_style, COLORS, get_ui_font
from gui.log_panel import TextRedirector
from gui.task_runner import TaskRunner
from config import config
from gui.settings_dialog import show_settings
from gui.tabs.convert_tab import ConvertTab
from gui.tabs.batch_tab import BatchTab
from gui.tabs.epub_tab import EpubTab
from gui.tabs.catalog_tab import CatalogTab

# 侧边栏配色（深蓝系）
_NAV_BG        = '#1e3a8a'
_NAV_ACTIVE    = '#1d4ed8'
_NAV_HOVER     = '#1e40af'
_NAV_INDICATOR = '#60a5fa'
_NAV_TEXT      = '#93c5fd'
_NAV_TEXT_ACT  = '#ffffff'
_NAV_SEP       = '#2d4fa0'
_NAV_WIDTH     = 180


class TxtToEpubGUI:
    """主 GUI 应用类"""

    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1060x800")
        self.root.minsize(840, 660)

        config.load()
        saved = config.get('window_geometry', '')
        if saved:
            try:
                self.root.geometry(saved)
            except tk.TclError:
                pass

        self.log_queue: queue.Queue = queue.Queue()
        self.task_runner = TaskRunner(self.root, on_task_finished=self._task_finished)
        self.current_output_file = None
        self.colors = COLORS
        setup_style()

        self._nav_items = []
        self._pages = []
        self._current_page = 0

        self._build_menu()
        self._build_status_bar()
        self._build_main_layout()

        sys.stdout = TextRedirector(self.log_queue)
        self._poll_log_queue()

        last = config.get('last_nav_index', 0)
        self._nav_select(last if 0 <= last < len(self._pages) else 0)

        print(f"=== {APP_TITLE} ===")
        print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if not EPUB_SUPPORT:
            print("⚠️ 未检测到 ebooklib，EPUB 生成功能不可用")
            print("   安装命令: pip install ebooklib pillow requests")
        else:
            print("✓ 已加载 ebooklib，EPUB 生成功能可用")

    # ------------------------------------------------------------------
    # 菜单（tk.Menu — CTk 无菜单控件）
    # ------------------------------------------------------------------
    def _build_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="打开 TXT 文件...", command=self._menu_open_txt)
        file_menu.add_command(label="打开文件夹...",   command=self._menu_open_dir)
        file_menu.add_separator()
        file_menu.add_command(label="设置...", command=self._show_settings)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_close)
        menubar.add_cascade(label="文件", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="使用说明", command=self._show_help)
        help_menu.add_command(label="关于",     command=self._show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)
        self.root.config(menu=menubar)

    def _menu_open_txt(self):
        path = filedialog.askopenfilename(
            title="选择 TXT 文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*")]
        )
        if path:
            self.tab_convert.set_file_path(path)
            self._nav_select(0)

    def _menu_open_dir(self):
        path = filedialog.askdirectory(title="选择文件夹")
        if path:
            self.tab_batch.set_dir_path(path)
            self._nav_select(1)

    def _show_settings(self):
        show_settings(self.root)

    def _show_help(self):
        messagebox.showinfo("使用说明", (
            "【使用说明】\n\n"
            "1. 单文件转换：选择 TXT 文件，自动提取书名作者，点击「开始转换」\n"
            "2. 批量转换：选择文件夹，批量处理所有 TXT 文件\n"
            "3. EPUB 生成：选择文件，配置封面后生成 EPUB\n"
            "4. 章节目录：查看章节列表和统计信息\n\n"
            "处理过程中可点击「取消」终止任务。"
        ))

    def _show_about(self):
        messagebox.showinfo("关于", (
            f"{APP_TITLE}\n\n"
            "TXT 小说优化与 EPUB 转换工具\n\n"
            f"版本: {APP_VERSION}\n"
            "Python: " + sys.version.split()[0] + "\n"
            "EPUB 支持: " + ("✓ 已启用" if EPUB_SUPPORT else "✗ 未启用")
        ))

    # ------------------------------------------------------------------
    # 主布局
    # ------------------------------------------------------------------
    def _build_main_layout(self):
        banner = ctk.CTkFrame(self.root, fg_color=self.colors['header_bg'],
                               height=52, corner_radius=0)
        banner.pack(fill='x')
        banner.pack_propagate(False)
        ctk.CTkLabel(banner, text="📚  TXT 转 EPUB 优化工具",
                     text_color=self.colors['header_fg'],
                     font=get_ui_font(15, 'bold'), anchor='w').pack(side='left', padx=18)
        ctk.CTkLabel(banner, text=f"v{APP_VERSION}",
                     text_color=self.colors['header_sub'],
                     font=get_ui_font(9)).pack(side='right', padx=18)

        body = ctk.CTkFrame(self.root, fg_color=self.colors['bg'], corner_radius=0)
        body.pack(fill='both', expand=True)
        self._build_sidebar(body)
        self._build_content_area(body)

    # ------------------------------------------------------------------
    # 左侧导航栏
    # ------------------------------------------------------------------
    def _build_sidebar(self, parent):
        sidebar = ctk.CTkFrame(parent, fg_color=_NAV_BG, corner_radius=0,
                                width=_NAV_WIDTH)
        sidebar.pack(side='left', fill='y')
        sidebar.pack_propagate(False)

        # Logo
        logo = ctk.CTkFrame(sidebar, fg_color=_NAV_BG, corner_radius=0)
        logo.pack(fill='x', padx=14, pady=(16, 8))
        ctk.CTkLabel(logo, text="📖", fg_color=_NAV_BG, text_color='#ffffff',
                     font=get_ui_font(18)).pack(side='left')
        ctk.CTkLabel(logo, text=" 工具箱", fg_color=_NAV_BG, text_color='#ffffff',
                     font=get_ui_font(11, 'bold')).pack(side='left')

        ctk.CTkFrame(sidebar, fg_color=_NAV_SEP, height=1,
                     corner_radius=0).pack(fill='x', padx=12, pady=(0, 4))

        # 可折叠功能组
        self._nav_group_collapsed = False
        self._nav_group_btn = ctk.CTkButton(
            sidebar, text='  功能  ▾',
            fg_color='transparent', hover_color=_NAV_HOVER,
            text_color='#7aa2e8', anchor='w', corner_radius=0,
            font=get_ui_font(8), height=28,
            command=self._toggle_nav_group,
        )
        self._nav_group_btn.pack(fill='x', padx=6, pady=(0, 2))

        self._nav_group_items_frame = ctk.CTkFrame(sidebar, fg_color=_NAV_BG,
                                                    corner_radius=0)
        self._nav_group_items_frame.pack(fill='x')

        for idx, (icon, label) in enumerate([
            ('📄', '单文件转换'),
            ('📁', '批量转换'),
            ('📖', 'EPUB 生成'),
            ('📑', '章节目录'),
        ]):
            self._nav_items.append(
                self._make_nav_btn(self._nav_group_items_frame, icon, label, idx))

        # 弹性填充
        ctk.CTkFrame(sidebar, fg_color=_NAV_BG, corner_radius=0).pack(
            fill='both', expand=True)

        ctk.CTkFrame(sidebar, fg_color=_NAV_SEP, height=1,
                     corner_radius=0).pack(fill='x', padx=12, pady=(0, 4))
        self._make_util_btn(sidebar, '⚙', '设置', self._show_settings)
        self._log_nav_btn = self._make_util_btn(
            sidebar, '📋', '日志 ▼', self._toggle_log)
        ctk.CTkFrame(sidebar, fg_color=_NAV_BG, height=8).pack()

    def _toggle_nav_group(self):
        self._nav_group_collapsed = not self._nav_group_collapsed
        if self._nav_group_collapsed:
            self._nav_group_items_frame.pack_forget()
            self._nav_group_btn.configure(text='  功能  ▸')
        else:
            self._nav_group_items_frame.pack(fill='x')
            self._nav_group_btn.configure(text='  功能  ▾')

    def _make_nav_btn(self, parent, icon, label, idx):
        container = ctk.CTkFrame(parent, fg_color=_NAV_BG, corner_radius=0, height=44)
        container.pack(fill='x')
        container.pack_propagate(False)

        indicator = ctk.CTkFrame(container, width=3, fg_color=_NAV_BG, corner_radius=0)
        indicator.pack(side='left', fill='y')
        indicator.pack_propagate(False)

        btn = ctk.CTkButton(
            container,
            text=f"{icon}  {label}",
            fg_color='transparent',
            hover_color=_NAV_HOVER,
            text_color=_NAV_TEXT,
            anchor='w',
            corner_radius=6,
            font=get_ui_font(11),
            command=lambda i=idx: self._nav_select(i),
        )
        btn.pack(side='left', fill='both', expand=True, padx=(2, 4), pady=3)

        badge = ctk.CTkLabel(container, text='', text_color='#86efac',
                              fg_color='transparent', font=get_ui_font(8), width=24)
        badge.pack(side='right', padx=(0, 8))

        return {'container': container, 'indicator': indicator,
                'button': btn, 'badge': badge}

    def set_nav_badge(self, idx: int, text: str, color: str = '#86efac'):
        if 0 <= idx < len(self._nav_items):
            item = self._nav_items[idx]
            item['badge'].configure(text=text, text_color=color)
            if text:
                self.root.after(2000, lambda: item['badge'].configure(text=''))

    def _make_util_btn(self, parent, icon, label, command):
        btn = ctk.CTkButton(
            parent,
            text=f"{icon}  {label}",
            fg_color='transparent',
            hover_color=_NAV_HOVER,
            text_color=_NAV_TEXT,
            anchor='w',
            corner_radius=6,
            font=get_ui_font(10),
            height=36,
            command=command,
        )
        btn.pack(fill='x', padx=8, pady=2)
        return btn

    def _nav_select(self, idx: int):
        for i, item in enumerate(self._nav_items):
            active = (i == idx)
            item['indicator'].configure(
                fg_color=_NAV_INDICATOR if active else _NAV_BG)
            item['button'].configure(
                fg_color=_NAV_ACTIVE if active else 'transparent',
                text_color=_NAV_TEXT_ACT if active else _NAV_TEXT,
            )
        if 0 <= idx < len(self._pages):
            self._pages[idx].lift()
        self._current_page = idx

    # ------------------------------------------------------------------
    # 右侧内容区
    # ------------------------------------------------------------------
    def _build_content_area(self, parent):
        right = ctk.CTkFrame(parent, fg_color=self.colors['bg'], corner_radius=0)
        right.pack(side='left', fill='both', expand=True)

        self._page_container = ctk.CTkFrame(right, fg_color=self.colors['bg'],
                                             corner_radius=0)
        self._page_container.pack(fill='both', expand=True)

        self.tab_convert = ConvertTab(self._page_container, self)
        self.tab_batch   = BatchTab(self._page_container, self)
        self.tab_epub    = EpubTab(self._page_container, self)
        self.tab_catalog = CatalogTab(self._page_container, self)

        self._pages = [
            self.tab_convert._page,
            self.tab_batch._page,
            self.tab_epub._page,
            self.tab_catalog._page,
        ]
        for page in self._pages:
            page.place(x=0, y=0, relwidth=1, relheight=1)

        self._build_log_area(right)
        self._build_action_bar(right)

    def _build_log_area(self, parent):
        self.log_frame = ctk.CTkFrame(parent, fg_color='transparent', corner_radius=0)
        self.log_frame.pack(fill='x', padx=12, pady=(4, 2))

        log_header = ctk.CTkFrame(self.log_frame, fg_color='transparent')
        log_header.pack(fill='x')
        ctk.CTkLabel(log_header, text="日志输出", text_color='#9ba8b7',
                     font=get_ui_font(9)).pack(side='left')
        self.log_toggle_btn = ctk.CTkButton(
            log_header, text="▼ 隐藏", width=72, height=26,
            font=get_ui_font(9), command=self._toggle_log,
        )
        self.log_toggle_btn.pack(side='right')

        self.log_text = ctk.CTkTextbox(
            self.log_frame, height=130, wrap='word',
            font=('Menlo' if sys.platform == 'darwin' else 'Consolas', 10),
            fg_color='#0d1117', text_color='#e2e8f0',
            border_width=0, corner_radius=6,
        )
        self.log_text.pack(fill='both', expand=True, pady=(4, 0))
        self.log_text.configure(state='disabled')
        self.log_visible = True

        for tag, color in [
            ('INFO', '#e2e8f0'), ('SUCCESS', '#86efac'),
            ('WARNING', '#fcd34d'), ('ERROR', '#fca5a5'), ('DEBUG', '#67e8f9'),
        ]:
            self.log_text._textbox.tag_configure(tag, foreground=color)

    def _build_action_bar(self, parent):
        output_bar = ctk.CTkFrame(parent, fg_color='transparent')
        output_bar.pack(fill='x', padx=12, pady=(4, 0))
        ctk.CTkLabel(output_bar, text="输出文件:", text_color='#9ba8b7',
                     font=get_ui_font(9)).pack(side='left')
        self.output_path_lbl = ctk.CTkLabel(
            output_bar, text="（暂无）",
            text_color=self.colors['accent'],
            anchor='w', font=get_ui_font(9), cursor='hand2',
        )
        self.output_path_lbl.pack(side='left', padx=(8, 0), fill='x', expand=True)
        self.output_path_lbl.bind('<Button-1>', lambda e: self._open_output_file())

        bar = ctk.CTkFrame(parent, fg_color='transparent')
        bar.pack(fill='x', padx=12, pady=(4, 10))

        self.progress_bar = ctk.CTkProgressBar(bar, mode='determinate', height=12)
        self.progress_bar.set(0)
        self.progress_bar.pack(side='left', fill='x', expand=True, padx=(0, 10))

        self.progress_label = ctk.CTkLabel(bar, text="就绪", text_color='#9ba8b7',
                                            width=90, anchor='e', font=get_ui_font(9))
        self.progress_label.pack(side='left', padx=(0, 10))

        self.cancel_btn = ctk.CTkButton(bar, text="取消", state='disabled',
                                         command=self._cancel_task,
                                         width=70, font=get_ui_font(9))
        self.cancel_btn.pack(side='right', padx=(4, 0))

        self.open_file_btn = ctk.CTkButton(bar, text="打开文件",
                                            command=self._open_output_file,
                                            state='disabled',
                                            width=80, font=get_ui_font(9))
        self.open_file_btn.pack(side='right', padx=(4, 0))

        self.open_dir_btn = ctk.CTkButton(bar, text="打开输出目录",
                                           command=self._open_output_dir,
                                           state='disabled',
                                           width=110, font=get_ui_font(9))
        self.open_dir_btn.pack(side='right', padx=(4, 0))

        self.clear_log_btn = ctk.CTkButton(bar, text="清空日志",
                                            command=self._clear_log,
                                            width=80, font=get_ui_font(9))
        self.clear_log_btn.pack(side='right', padx=(4, 0))

    def _build_status_bar(self):
        status = ctk.CTkFrame(self.root, fg_color=self.colors['panel'],
                               corner_radius=0, height=28)
        status.pack(fill='x', side='bottom')
        status.pack_propagate(False)

        self._dot_lbl = ctk.CTkLabel(status, text="●",
                                      text_color=self.colors['success'],
                                      font=get_ui_font(11))
        self._dot_lbl.pack(side='left', padx=(10, 4), pady=4)

        self.status_lbl = ctk.CTkLabel(status, text="就绪",
                                        text_color=self.colors['text_muted'],
                                        font=get_ui_font(9))
        self.status_lbl.pack(side='left', pady=4)

        ctk.CTkLabel(status, text="TXT → EPUB",
                     text_color=self.colors['border'],
                     font=get_ui_font(9)).pack(side='right', padx=10, pady=4)

    # ------------------------------------------------------------------
    # 日志与进度
    # ------------------------------------------------------------------
    def _toggle_log(self):
        if self.log_visible:
            self.log_text.pack_forget()
            self.log_toggle_btn.configure(text="▲ 显示")
            self._log_nav_btn.configure(text='📋  日志 ▲')
            self.log_visible = False
        else:
            self.log_text.pack(fill='both', expand=True, pady=(4, 0))
            self.log_toggle_btn.configure(text="▼ 隐藏")
            self._log_nav_btn.configure(text='📋  日志 ▼')
            self.log_visible = True

    def _poll_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self._append_log(msg)
        except queue.Empty:
            pass
        self.root.after(80, self._poll_log_queue)

    def _append_log(self, text: str):
        tag = 'INFO'
        if '✅' in text or '✓' in text or '完成' in text:
            tag = 'SUCCESS'
        elif '⚠️' in text or '警告' in text:
            tag = 'WARNING'
        elif '❌' in text or '错误' in text or '失败' in text:
            tag = 'ERROR'
        elif '[DEBUG]' in text:
            tag = 'DEBUG'
        self.log_text.configure(state='normal')
        body = text + ('\n' if not text.endswith('\n') else '')
        self.log_text._textbox.insert('end', body, tag)
        self.log_text._textbox.see('end')
        self.log_text.configure(state='disabled')

    def _clear_log(self):
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.configure(state='disabled')

    def set_progress(self, value: float, label: str = None):
        self.progress_bar.set(value / 100.0)
        if label:
            self.progress_label.configure(text=label)

    def set_status(self, text: str):
        self.status_lbl.configure(text=text)
        if '失败' in text or '错误' in text or '取消' in text:
            dot_color = self.colors['error']
        elif '处理' in text or '加载' in text or '生成' in text or '转换' in text or '保存' in text:
            dot_color = self.colors['warning']
        else:
            dot_color = self.colors['success']
        self._dot_lbl.configure(text_color=dot_color)

    # ------------------------------------------------------------------
    # 任务执行
    # ------------------------------------------------------------------
    @property
    def worker_thread(self):
        return self.task_runner.worker_thread

    @property
    def cancel_flag(self):
        return self.task_runner.cancel_flag

    def run_task(self, target, args=(), kwargs=None, on_complete=None, on_error=None):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("提示", "已有任务正在运行，请等待完成或取消")
            return
        self.set_progress(0, "处理中...")
        self.set_status("处理中...")
        self.cancel_btn.configure(state='normal')
        kwargs = kwargs or {}
        if not self.task_runner.submit(target, *args,
                                       on_complete=on_complete,
                                       on_error=on_error, **kwargs):
            messagebox.showwarning("提示", "已有任务正在运行，请等待完成或取消")

    def _task_finished(self):
        self.cancel_btn.configure(state='disabled')
        if self.cancel_flag.is_set():
            self.set_status("已取消")
            self.set_progress(0, "已取消")
        else:
            self.set_status("就绪")
            self.set_progress(100, "完成")

    def _cancel_task(self):
        if self.worker_thread and self.worker_thread.is_alive():
            if messagebox.askyesno("确认", "确定要取消当前任务吗？"):
                self.task_runner.cancel()
                print("⚠️ 用户已请求取消任务")
        else:
            messagebox.showinfo("提示", "当前没有运行中的任务")

    def _open_output_dir(self):
        if not self.current_output_file:
            messagebox.showinfo("提示", "暂无输出文件，请先执行转换")
            return
        dir_path = os.path.dirname(self.current_output_file)
        if not os.path.isdir(dir_path):
            messagebox.showerror("错误", f"目录不存在: {dir_path}")
            return
        try:
            if sys.platform == 'darwin':
                if os.path.isfile(self.current_output_file):
                    os.system(f'open -R "{self.current_output_file}"')
                else:
                    os.system(f'open "{dir_path}"')
            elif sys.platform == 'win32':
                os.startfile(dir_path)
            else:
                os.system(f'xdg-open "{dir_path}"')
        except Exception as e:
            messagebox.showerror("错误", f"打开目录失败: {e}")

    def _open_output_file(self):
        if not self.current_output_file:
            messagebox.showinfo("提示", "暂无输出文件，请先执行转换")
            return
        if not os.path.isfile(self.current_output_file):
            messagebox.showerror("错误", f"文件不存在: {self.current_output_file}")
            return
        try:
            if sys.platform == 'darwin':
                os.system(f'open "{self.current_output_file}"')
            elif sys.platform == 'win32':
                os.startfile(self.current_output_file)
            else:
                os.system(f'xdg-open "{self.current_output_file}"')
        except Exception as e:
            messagebox.showerror("错误", f"打开文件失败: {e}")

    def set_output_file(self, path: str):
        self.current_output_file = path
        if path and os.path.isfile(path):
            size = os.path.getsize(path)
            if size >= 1024 * 1024:
                size_str = f"({size/1024/1024:.2f} MB)"
            elif size >= 1024:
                size_str = f"({size/1024:.1f} KB)"
            else:
                size_str = f"({size} B)"
            self.output_path_lbl.configure(text=f"{path}  {size_str}")
            self.open_file_btn.configure(state='normal')
            self.open_dir_btn.configure(state='normal')
        elif path:
            self.output_path_lbl.configure(text=path)
            self.open_file_btn.configure(state='disabled')
            self.open_dir_btn.configure(state='normal')
        else:
            self.output_path_lbl.configure(text="（暂无）")
            self.open_file_btn.configure(state='disabled')
            self.open_dir_btn.configure(state='disabled')

    # ------------------------------------------------------------------
    # 配置代理
    # ------------------------------------------------------------------
    def config_get_recent_files(self):
        return config.get_recent_files()

    def config_get_recent_dirs(self):
        return config.get_recent_dirs()

    # ------------------------------------------------------------------
    # 按钮内联进度反馈
    # ------------------------------------------------------------------
    def set_btn_working(self, btn, working: bool, idle_text: str,
                        working_text: str = None):
        if working:
            btn.configure(state='disabled',
                          text=working_text or f"⏳ {idle_text}…")
        else:
            btn.configure(state='normal', text=idle_text)

    def flash_btn_done(self, btn, idle_text: str, success: bool = True):
        flash_text = "✅ 完成" if success else "❌ 失败"
        btn.configure(text=flash_text)
        self.root.after(1200, lambda: btn.configure(state='normal', text=idle_text))

    # ------------------------------------------------------------------
    # 关闭
    # ------------------------------------------------------------------
    def _on_close(self):
        if self.worker_thread and self.worker_thread.is_alive():
            if not messagebox.askyesno("确认", "任务正在运行，确定退出吗？"):
                return
            self.task_runner.cancel()
        self._save_config()
        self.task_runner.shutdown()
        self.root.destroy()

    def _save_config(self):
        try:
            config.set('window_geometry', self.root.geometry())
            config.set('last_nav_index', self._current_page)
            if hasattr(self, 'tab_epub'):
                config.set('cover_choice', self.tab_epub.cover_var.get())
                config.set('last_title',   self.tab_epub.title_var.get())
                config.set('last_author',  self.tab_epub.author_var.get())
            config.save()
        except Exception as e:
            print(f"[CONFIG] 保存配置失败: {e}")
