"""主 GUI 应用类：TxtToEpubGUI"""

import os
import sys
import queue
import tkinter as tk
from datetime import datetime
from tkinter import ttk, filedialog, messagebox, scrolledtext

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

# 侧边栏配色（深蓝系，与顶部横幅统一）
_NAV_BG        = '#1e3a8a'   # 底色
_NAV_ACTIVE    = '#1d4ed8'   # 选中项背景
_NAV_HOVER     = '#1e40af'   # 悬停背景
_NAV_INDICATOR = '#60a5fa'   # 左侧激活条
_NAV_TEXT      = '#93c5fd'   # 未选中文字
_NAV_TEXT_ACT  = '#ffffff'   # 选中文字
_NAV_SEP       = '#2d4fa0'   # 分割线
_NAV_WIDTH     = 172


class TxtToEpubGUI:
    """主 GUI 应用类"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1060x800")
        self.root.minsize(840, 660)

        config.load()
        saved_geometry = config.get('window_geometry', '')
        if saved_geometry:
            try:
                self.root.geometry(saved_geometry)
            except tk.TclError:
                pass

        self.log_queue: queue.Queue = queue.Queue()
        self.task_runner = TaskRunner(
            self.root, on_task_finished=self._task_finished)
        self.current_output_file = None

        self.colors = COLORS
        setup_style(self.root, self.colors)

        self._nav_items = []      # [{'frame', 'indicator', 'icon', 'text'}]
        self._pages = []          # [tk.Frame, ...]  一一对应 _nav_items
        self._current_page = 0

        self._build_menu()
        self._build_status_bar()   # side='bottom'，先 pack 才能正确占位
        self._build_main_layout()

        sys.stdout = TextRedirector(self.log_queue)
        self._poll_log_queue()

        # 默认选中第 0 页（恢复上次记录）
        last = config.get('last_nav_index', 0)
        self._nav_select(last if 0 <= last < len(self._pages) else 0)

        print(f"=== {APP_TITLE} ===")
        print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if not EPUB_SUPPORT:
            print("⚠️ 未检测到 ebooklib 库，EPUB 生成功能不可用")
            print("   安装命令: pip install ebooklib pillow requests")
        else:
            print("✓ 已加载 ebooklib，EPUB 生成功能可用")

    # ------------------------------------------------------------------
    # 菜单栏
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
            "2. 批量转换：选择文件夹，将批量处理所有 TXT 文件\n"
            "3. EPUB 生成：选择 *_epub_ready.txt 文件，配置封面后生成 EPUB\n"
            "4. 章节目录：选择 TXT 文件，查看章节列表和统计信息\n\n"
            "【快捷操作】\n"
            "- 处理过程中可点击「取消」终止任务\n"
            "- 完成后可点击「打开输出目录」查看结果\n"
        ))

    def _show_about(self):
        messagebox.showinfo("关于", (
            f"{APP_TITLE}\n\n"
            "一款 TXT 小说优化与 EPUB 转换工具\n"
            "支持多种章节格式识别、批量处理、封面下载\n\n"
            f"版本: {APP_VERSION}\n"
            "Python: " + sys.version.split()[0] + "\n"
            "EPUB 支持: " + ("✓ 已启用" if EPUB_SUPPORT else "✗ 未启用")
        ))

    # ------------------------------------------------------------------
    # 主布局
    # ------------------------------------------------------------------
    def _build_main_layout(self):
        # ── 顶部品牌横幅 ────────────────────────────────────────────────
        banner = tk.Frame(self.root, bg=self.colors['header_bg'], height=52)
        banner.pack(fill='x')
        banner.pack_propagate(False)

        tk.Label(
            banner, text="📚  TXT 转 EPUB 优化工具",
            bg=self.colors['header_bg'], fg=self.colors['header_fg'],
            font=get_ui_font(15, 'bold'), anchor='w'
        ).pack(side='left', padx=18)
        tk.Label(
            banner, text=f"v{APP_VERSION}",
            bg=self.colors['header_bg'], fg=self.colors['header_sub'],
            font=get_ui_font(9)
        ).pack(side='right', padx=18)

        # ── 主体区：左侧栏 + 右侧内容区 ─────────────────────────────────
        body = tk.Frame(self.root, bg=self.colors['bg'])
        body.pack(fill='both', expand=True)

        self._build_sidebar(body)
        self._build_content_area(body)

    # ------------------------------------------------------------------
    # 左侧导航栏
    # ------------------------------------------------------------------
    def _build_sidebar(self, parent):
        sidebar = tk.Frame(parent, bg=_NAV_BG, width=_NAV_WIDTH)
        sidebar.pack(side='left', fill='y')
        sidebar.pack_propagate(False)

        # ── Logo ─────────────────────────────────────────────────────────
        logo_frame = tk.Frame(sidebar, bg=_NAV_BG)
        logo_frame.pack(fill='x', padx=12, pady=(16, 8))
        tk.Label(logo_frame, text="📖", bg=_NAV_BG, fg='#ffffff',
                 font=get_ui_font(20)).pack(side='left')
        tk.Label(logo_frame, text=" 工具箱", bg=_NAV_BG, fg='#ffffff',
                 font=get_ui_font(11, 'bold')).pack(side='left')

        tk.Frame(sidebar, bg=_NAV_SEP, height=1).pack(fill='x', padx=12, pady=(0, 4))

        # ── 可折叠功能组 ──────────────────────────────────────────────────
        nav_defs = [
            ('📄', '单文件转换'),
            ('📁', '批量转换'),
            ('📖', 'EPUB 生成'),
            ('📑', '章节目录'),
        ]
        self._nav_group_collapsed = False
        self._nav_group_items_frame = tk.Frame(sidebar, bg=_NAV_BG)

        # 组头（可点击折叠）
        group_header = tk.Frame(sidebar, bg=_NAV_BG, cursor='hand2')
        group_header.pack(fill='x')

        self._nav_group_arrow = tk.Label(
            group_header, text='▾', bg=_NAV_BG, fg='#7aa2e8',
            font=get_ui_font(10))
        self._nav_group_arrow.pack(side='right', padx=(0, 10), pady=6)

        tk.Label(group_header, text='  功能', bg=_NAV_BG,
                 fg='#7aa2e8', font=get_ui_font(8)).pack(side='left', pady=6)

        for w in (group_header, self._nav_group_arrow):
            w.bind('<Button-1>', lambda e: self._toggle_nav_group())
            w.bind('<Enter>', lambda e, ws=(group_header, self._nav_group_arrow):
                   [x.config(bg=_NAV_HOVER) for x in ws])
            w.bind('<Leave>', lambda e, ws=(group_header, self._nav_group_arrow):
                   [x.config(bg=_NAV_BG) for x in ws])

        # 条目
        self._nav_group_items_frame.pack(fill='x')
        for idx, (icon, label) in enumerate(nav_defs):
            item = self._make_nav_btn(self._nav_group_items_frame, icon, label, idx)
            self._nav_items.append(item)

        # ── 弹性填充 ─────────────────────────────────────────────────────
        tk.Frame(sidebar, bg=_NAV_BG).pack(fill='both', expand=True)

        # ── 工具区 ────────────────────────────────────────────────────────
        tk.Frame(sidebar, bg=_NAV_SEP, height=1).pack(fill='x', padx=12, pady=(0, 4))
        self._make_util_btn(sidebar, '⚙', '设置', self._show_settings)
        self._log_nav_btn = self._make_util_btn(
            sidebar, '📋', '日志 ▼', self._toggle_log)

        tk.Frame(sidebar, bg=_NAV_BG, height=8).pack()

    def _toggle_nav_group(self):
        """折叠/展开功能导航组"""
        self._nav_group_collapsed = not self._nav_group_collapsed
        if self._nav_group_collapsed:
            self._nav_group_items_frame.pack_forget()
            self._nav_group_arrow.config(text='▸')
        else:
            self._nav_group_items_frame.pack(fill='x')
            self._nav_group_arrow.config(text='▾')

    def _make_nav_btn(self, parent, icon, label, idx):
        """创建一个导航条目，返回组件字典"""
        btn = tk.Frame(parent, bg=_NAV_BG, cursor='hand2')
        btn.pack(fill='x')

        # 左侧激活指示条（3px）
        indicator = tk.Frame(btn, width=3, bg=_NAV_BG)
        indicator.pack(side='left', fill='y')
        indicator.pack_propagate(False)

        icon_lbl = tk.Label(btn, text=icon, bg=_NAV_BG, fg=_NAV_TEXT,
                            font=get_ui_font(16))
        icon_lbl.pack(side='left', padx=(10, 6), pady=12)

        text_lbl = tk.Label(btn, text=label, bg=_NAV_BG, fg=_NAV_TEXT,
                            font=get_ui_font(10), anchor='w')
        text_lbl.pack(side='left', fill='x', expand=True, pady=12)

        # 右侧 badge（状态小标记，默认隐藏）
        badge_lbl = tk.Label(btn, text='', bg=_NAV_BG, fg='#86efac',
                             font=get_ui_font(8))
        badge_lbl.pack(side='right', padx=(0, 8))

        item = {'frame': btn, 'indicator': indicator,
                'icon': icon_lbl, 'text': text_lbl, 'badge': badge_lbl}

        for w in (btn, icon_lbl, text_lbl, badge_lbl):
            w.bind('<Button-1>', lambda e, i=idx: self._nav_select(i))
            w.bind('<Enter>',    lambda e, i=idx: self._on_nav_enter(i))
            w.bind('<Leave>',    lambda e, i=idx: self._on_nav_leave(i, e))

        return item

    def set_nav_badge(self, idx: int, text: str, color: str = '#86efac'):
        """在第 idx 个导航项右侧显示一个小 badge（空字符串=隐藏）"""
        if 0 <= idx < len(self._nav_items):
            item = self._nav_items[idx]
            item['badge'].config(text=text, fg=color)
            # 2 秒后自动清除
            if text:
                self.root.after(2000, lambda: item['badge'].config(text=''))

    def _make_util_btn(self, parent, icon, label, command):
        """底部工具按钮（设置、日志折叠）"""
        btn = tk.Frame(parent, bg=_NAV_BG, cursor='hand2')
        btn.pack(fill='x')

        icon_lbl = tk.Label(btn, text=icon, bg=_NAV_BG, fg=_NAV_TEXT,
                            font=get_ui_font(13))
        icon_lbl.pack(side='left', padx=(13, 6), pady=10)

        text_lbl = tk.Label(btn, text=label, bg=_NAV_BG, fg=_NAV_TEXT,
                            font=get_ui_font(9), anchor='w')
        text_lbl.pack(side='left', fill='x', expand=True)

        for w in (btn, icon_lbl, text_lbl):
            w.bind('<Button-1>', lambda e: command())
            w.bind('<Enter>',
                   lambda e, ws=(btn, icon_lbl, text_lbl):
                   [x.config(bg=_NAV_HOVER) for x in ws])
            w.bind('<Leave>',
                   lambda e, ws=(btn, icon_lbl, text_lbl):
                   [x.config(bg=_NAV_BG) for x in ws])

        return {'frame': btn, 'icon': icon_lbl, 'text': text_lbl}

    def _nav_select(self, idx: int):
        """切换到第 idx 个页面并高亮对应导航项"""
        for i, item in enumerate(self._nav_items):
            active = (i == idx)
            bg = _NAV_ACTIVE if active else _NAV_BG
            item['frame'].config(bg=bg)
            item['indicator'].config(bg=_NAV_INDICATOR if active else _NAV_BG)
            item['icon'].config(bg=bg, fg=_NAV_TEXT_ACT if active else _NAV_TEXT)
            item['text'].config(bg=bg, fg=_NAV_TEXT_ACT if active else _NAV_TEXT)

        if 0 <= idx < len(self._pages):
            self._pages[idx].lift()
        self._current_page = idx

    def _on_nav_enter(self, idx: int):
        if idx == self._current_page:
            return
        item = self._nav_items[idx]
        for w in (item['frame'], item['icon'], item['text']):
            w.config(bg=_NAV_HOVER)

    def _on_nav_leave(self, idx: int, event):
        if idx == self._current_page:
            return
        # 只有鼠标真正离开整个按钮区域才还原（避免子控件边界闪烁）
        item = self._nav_items[idx]
        f = item['frame']
        try:
            rx, ry = event.x_root, event.y_root
            fx, fy = f.winfo_rootx(), f.winfo_rooty()
            fw, fh = f.winfo_width(), f.winfo_height()
            if fx <= rx <= fx + fw and fy <= ry <= fy + fh:
                return
        except Exception:
            pass
        for w in (f, item['icon'], item['text']):
            w.config(bg=_NAV_BG)

    # ------------------------------------------------------------------
    # 右侧内容区
    # ------------------------------------------------------------------
    def _build_content_area(self, parent):
        right = tk.Frame(parent, bg=self.colors['bg'])
        right.pack(side='left', fill='both', expand=True)

        # ── 页面容器（各 Tab 叠放，通过 lift 切换）─────────────────────
        self._page_container = tk.Frame(right, bg=self.colors['bg'])
        self._page_container.pack(fill='both', expand=True)

        self.tab_convert = ConvertTab(self._page_container, self)
        self.tab_batch   = BatchTab(self._page_container, self)
        self.tab_epub    = EpubTab(self._page_container, self)
        self.tab_catalog = CatalogTab(self._page_container, self)

        self._pages = [
            self.tab_convert.frame,
            self.tab_batch.frame,
            self.tab_epub.frame,
            self.tab_catalog.frame,
        ]
        for page in self._pages:
            page.place(x=0, y=0, relwidth=1, relheight=1)

        # ── 日志区（可折叠）──────────────────────────────────────────────
        self._build_log_area(right)

        # ── 底部操作栏 ───────────────────────────────────────────────────
        self._build_action_bar(right)

    def _build_log_area(self, parent):
        self.log_frame = ttk.Frame(parent)
        self.log_frame.pack(fill='x', padx=12, pady=(4, 2))

        log_header = ttk.Frame(self.log_frame)
        log_header.pack(fill='x')
        ttk.Label(log_header, text="日志输出",
                  style='Muted.TLabel').pack(side='left')
        self.log_toggle_btn = ttk.Button(
            log_header, text="▼ 隐藏", width=8,
            command=self._toggle_log)
        self.log_toggle_btn.pack(side='right')

        self.log_text = scrolledtext.ScrolledText(
            self.log_frame, height=6, wrap='word',
            font=('Menlo' if sys.platform == 'darwin' else 'Consolas', 10),
            bg=self.colors['log_bg'], fg=self.colors['log_fg'],
            insertbackground=self.colors['log_fg'],
            selectbackground='#3b4261',
            relief='flat', padx=10, pady=8,
        )
        self.log_text.pack(fill='both', expand=True)
        self.log_text.configure(state='disabled')
        self.log_visible = True

        self.log_text.tag_config('INFO',    foreground='#e2e8f0')
        self.log_text.tag_config('SUCCESS', foreground='#86efac')
        self.log_text.tag_config('WARNING', foreground='#fcd34d')
        self.log_text.tag_config('ERROR',   foreground='#fca5a5')
        self.log_text.tag_config('DEBUG',   foreground='#67e8f9')

    def _build_action_bar(self, parent):
        # 输出文件路径行
        output_bar = ttk.Frame(parent)
        output_bar.pack(fill='x', padx=12, pady=(4, 0))
        ttk.Label(output_bar, text="输出文件:",
                  style='Muted.TLabel').pack(side='left')
        self.output_path_var = tk.StringVar(value="（暂无）")
        lbl = ttk.Label(output_bar, textvariable=self.output_path_var,
                        foreground=self.colors['accent'], cursor='hand2')
        lbl.pack(side='left', padx=(8, 0), fill='x', expand=True)
        lbl.bind('<Button-1>', lambda e: self._open_output_file())

        # 进度条 + 按钮行
        bar = ttk.Frame(parent)
        bar.pack(fill='x', padx=12, pady=(4, 10))

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            bar, orient='horizontal', mode='determinate',
            variable=self.progress_var, maximum=100,
        )
        self.progress_bar.pack(side='left', fill='x', expand=True, padx=(0, 10))

        self.progress_label = ttk.Label(bar, text="就绪",
                                        style='Muted.TLabel', width=12, anchor='e')
        self.progress_label.pack(side='left', padx=(0, 10))

        self.cancel_btn = ttk.Button(bar, text="取消", state='disabled',
                                     command=self._cancel_task)
        self.cancel_btn.pack(side='right', padx=(4, 0))

        self.open_file_btn = ttk.Button(bar, text="打开文件",
                                        command=self._open_output_file,
                                        state='disabled')
        self.open_file_btn.pack(side='right', padx=(4, 0))

        self.open_dir_btn = ttk.Button(bar, text="打开输出目录",
                                       command=self._open_output_dir,
                                       state='disabled')
        self.open_dir_btn.pack(side='right', padx=(4, 0))

        self.clear_log_btn = ttk.Button(bar, text="清空日志",
                                        command=self._clear_log)
        self.clear_log_btn.pack(side='right', padx=(4, 0))

    def _build_status_bar(self):
        status = tk.Frame(self.root, bg=self.colors['panel'],
                          highlightbackground=self.colors['border'],
                          highlightthickness=1)
        status.pack(fill='x', side='bottom')

        self._dot_canvas = tk.Canvas(status, width=10, height=10,
                                     bg=self.colors['panel'],
                                     highlightthickness=0)
        self._dot_canvas.pack(side='left', padx=(10, 4), pady=5)
        self._dot = self._dot_canvas.create_oval(1, 1, 9, 9,
                                                  fill=self.colors['success'],
                                                  outline='')

        self.status_var = tk.StringVar(value="就绪")
        tk.Label(status, textvariable=self.status_var,
                 bg=self.colors['panel'], fg=self.colors['text_muted'],
                 font=get_ui_font(9)).pack(side='left', pady=4)

        tk.Label(status, text="TXT → EPUB",
                 bg=self.colors['panel'], fg=self.colors['border'],
                 font=get_ui_font(9)).pack(side='right', padx=10, pady=4)

    # ------------------------------------------------------------------
    # 日志与进度
    # ------------------------------------------------------------------
    def _toggle_log(self):
        if self.log_visible:
            self.log_text.pack_forget()
            self.log_toggle_btn.config(text="▲ 显示")
            if hasattr(self, '_log_nav_btn'):
                self._log_nav_btn['text'].config(text='日志 ▲')
            self.log_visible = False
        else:
            self.log_text.pack(fill='both', expand=True)
            self.log_toggle_btn.config(text="▼ 隐藏")
            if hasattr(self, '_log_nav_btn'):
                self._log_nav_btn['text'].config(text='日志 ▼')
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
        self.log_text.configure(state='normal')
        tag = 'INFO'
        if '✅' in text or '✓' in text or '完成' in text:
            tag = 'SUCCESS'
        elif '⚠️' in text or '警告' in text:
            tag = 'WARNING'
        elif '❌' in text or '错误' in text or '失败' in text:
            tag = 'ERROR'
        elif '[DEBUG]' in text:
            tag = 'DEBUG'
        self.log_text.insert('end', text + ('\n' if not text.endswith('\n') else ''), tag)
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def _clear_log(self):
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.configure(state='disabled')

    def set_progress(self, value: float, label: str = None):
        self.progress_var.set(value)
        if label:
            self.progress_label.config(text=label)

    def set_status(self, text: str):
        self.status_var.set(text)
        if '失败' in text or '错误' in text or '取消' in text:
            dot_color = self.colors['error']
        elif '处理' in text or '加载' in text or '生成' in text or '转换' in text or '保存' in text:
            dot_color = self.colors['warning']
        else:
            dot_color = self.colors['success']
        self._dot_canvas.itemconfig(self._dot, fill=dot_color)

    # ------------------------------------------------------------------
    # 任务执行
    # ------------------------------------------------------------------
    @property
    def worker_thread(self):
        return self.task_runner.worker_thread

    @property
    def cancel_flag(self):
        return self.task_runner.cancel_flag

    def run_task(self, target, args=(), kwargs=None,
                 on_complete=None, on_error=None):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("提示", "已有任务正在运行，请等待完成或取消")
            return

        self.set_progress(0, "处理中...")
        self.set_status("处理中...")
        self.cancel_btn.config(state='normal')

        kwargs = kwargs or {}
        if not self.task_runner.submit(
            target, *args,
            on_complete=on_complete, on_error=on_error, **kwargs
        ):
            messagebox.showwarning("提示", "已有任务正在运行，请等待完成或取消")

    def _task_finished(self):
        self.cancel_btn.config(state='disabled')
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
            self.output_path_var.set(f"{path}  {size_str}")
            self.open_file_btn.config(state='normal')
            self.open_dir_btn.config(state='normal')
        elif path:
            self.output_path_var.set(path)
            self.open_file_btn.config(state='disabled')
            self.open_dir_btn.config(state='normal')
        else:
            self.output_path_var.set("（暂无）")
            self.open_file_btn.config(state='disabled')
            self.open_dir_btn.config(state='disabled')

    # ------------------------------------------------------------------
    # 配置代理（供 BaseTab 访问，避免直接 import config）
    # ------------------------------------------------------------------
    def config_get_recent_files(self):
        return config.get_recent_files()

    def config_get_recent_dirs(self):
        return config.get_recent_dirs()

    # ------------------------------------------------------------------
    # 按钮内联进度反馈
    # ------------------------------------------------------------------
    def set_btn_working(self, btn: 'ttk.Button', working: bool,
                        idle_text: str, working_text: str = None):
        """切换按钮的「工作中」外观。

        working=True  → 禁用按钮，文字改为 working_text（如「⏳ 转换中…」）
        working=False → 恢复 idle_text 并启用
        """
        if working:
            btn.config(state='disabled',
                       text=working_text or f"⏳ {idle_text}…")
        else:
            btn.config(state='normal', text=idle_text)

    def flash_btn_done(self, btn: 'ttk.Button', idle_text: str,
                       success: bool = True):
        """任务完成后让按钮短暂显示结果文字，1.2 秒后恢复。"""
        flash_text = "✅ 完成" if success else "❌ 失败"
        btn.config(text=flash_text)
        self.root.after(1200, lambda: btn.config(
            state='normal', text=idle_text))

    # ------------------------------------------------------------------
    # 关闭处理
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
