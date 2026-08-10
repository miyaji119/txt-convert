"""主 GUI 应用类：TxtToEpubGUI"""

import os
import sys
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk, filedialog, messagebox, scrolledtext

from gui.constants import APP_VERSION, APP_TITLE, EPUB_SUPPORT
from gui.theme import setup_style, COLORS
from gui.log_panel import TextRedirector
from gui.task_runner import TaskRunner
from config import config
from gui.settings_dialog import show_settings
from gui.tabs.convert_tab import ConvertTab
from gui.tabs.batch_tab import BatchTab
from gui.tabs.epub_tab import EpubTab
from gui.tabs.catalog_tab import CatalogTab


class TxtToEpubGUI:
    """主 GUI 应用类"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1080x800")
        self.root.minsize(960, 680)

        # 加载持久化配置（窗口大小/位置、最近路径、正则规则等）
        config.load()
        # 应用保存的窗口位置和大小
        saved_geometry = config.get('window_geometry', '')
        if saved_geometry:
            try:
                self.root.geometry(saved_geometry)
            except tk.TclError:
                pass

        # 后台任务相关（委托给 TaskRunner，functools.partial 机制杜绝闭包陷阱）
        self.log_queue: queue.Queue = queue.Queue()
        self.task_runner = TaskRunner(
            self.root, on_task_finished=self._task_finished)
        self.current_output_file = None

        # 应用主题
        self.colors = COLORS
        setup_style(self.root, self.colors)

        # 构建 UI
        self._build_menu()
        self._build_main_layout()
        self._build_status_bar()

        # 应用上次选中的标签页
        last_tab = config.get('last_tab_index', 0)
        try:
            if 0 <= last_tab < self.notebook.index('end'):
                self.notebook.select(last_tab)
        except tk.TclError:
            pass

        # 重定向 stdout 到日志区
        sys.stdout = TextRedirector(self.log_queue)

        # 启动日志轮询
        self._poll_log_queue()

        # 欢迎信息
        print(f"=== {APP_TITLE} ===")
        print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if not EPUB_SUPPORT:
            print("⚠️ 未检测到 ebooklib 库，EPUB 生成功能不可用")
            print("   安装命令: pip install ebooklib pillow requests")
        else:
            print("✓ 已加载 ebooklib，EPUB 生成功能可用")
        print("提示: 选择上方标签页开始操作\n")

    # ------------------------------------------------------------------
    # 菜单栏
    # ------------------------------------------------------------------
    def _build_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="打开 TXT 文件...", command=self._menu_open_txt)
        file_menu.add_command(label="打开文件夹...", command=self._menu_open_dir)
        file_menu.add_separator()
        file_menu.add_command(label="设置...", command=self._show_settings)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_close)
        menubar.add_cascade(label="文件", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="使用说明", command=self._show_help)
        help_menu.add_command(label="关于", command=self._show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)

        self.root.config(menu=menubar)

    def _menu_open_txt(self):
        path = filedialog.askopenfilename(
            title="选择 TXT 文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*")]
        )
        if path:
            self.tab_convert.set_file_path(path)
            self.notebook.select(0)

    def _menu_open_dir(self):
        path = filedialog.askdirectory(title="选择文件夹")
        if path:
            self.tab_batch.set_dir_path(path)
            self.notebook.select(1)

    def _show_settings(self):
        """打开设置对话框（默认输出目录 + 自定义正则规则）"""
        show_settings(self.root)

    def _show_help(self):
        help_text = (
            "【使用说明】\n\n"
            "1. 单文件转换：选择 TXT 文件，自动提取书名作者，点击「开始转换」\n"
            "2. 批量转换：选择文件夹，将批量处理所有 TXT 文件\n"
            "3. EPUB 生成：选择 *_epub_ready.txt 文件，配置封面后生成 EPUB\n"
            "4. 章节目录：选择 TXT 文件，查看章节列表和统计信息\n\n"
            "【快捷操作】\n"
            "- 拖拽文件到输入框可自动填入路径\n"
            "- 处理过程中可点击「取消」终止任务\n"
            "- 完成后可点击「打开输出目录」查看结果\n"
        )
        messagebox.showinfo("使用说明", help_text)

    def _show_about(self):
        about_text = (
            f"{APP_TITLE}\n\n"
            "一款 TXT 小说优化与 EPUB 转换工具\n"
            "支持多种章节格式识别、批量处理、封面下载\n\n"
            f"版本: {APP_VERSION}\n"
            "Python: " + sys.version.split()[0] + "\n"
            "EPUB 支持: " + ("✓ 已启用" if EPUB_SUPPORT else "✗ 未启用")
        )
        messagebox.showinfo("关于", about_text)

    # ------------------------------------------------------------------
    # 主布局
    # ------------------------------------------------------------------
    def _build_main_layout(self):
        """构建主布局：标题 + 标签页 + 日志区 + 操作栏"""
        # 顶部标题
        header = ttk.Frame(self.root)
        header.pack(fill='x', padx=16, pady=(12, 6))
        ttk.Label(header, text="📚 TXT 转 EPUB 优化工具",
                  style='Title.TLabel').pack(side='left')
        ttk.Label(header, text=f"版本 {APP_VERSION}",
                  style='Muted.TLabel').pack(side='right')

        # 标题下方分隔线
        ttk.Separator(self.root, orient='horizontal').pack(
            fill='x', padx=16, pady=(0, 4))

        # 标签页区域
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=16, pady=(4, 6))

        # 创建各标签页
        self.tab_convert = ConvertTab(self.notebook, self)
        self.tab_batch = BatchTab(self.notebook, self)
        self.tab_epub = EpubTab(self.notebook, self)
        self.tab_catalog = CatalogTab(self.notebook, self)

        self.notebook.add(self.tab_convert.frame, text="  📄 单文件转换  ")
        self.notebook.add(self.tab_batch.frame, text="  📁 批量转换  ")
        self.notebook.add(self.tab_epub.frame, text="  📖 EPUB 生成  ")
        self.notebook.add(self.tab_catalog.frame, text="  📑 章节目录  ")

        # 日志输出区（可折叠）
        self.log_frame = ttk.Frame(self.root)
        self.log_frame.pack(fill='both', expand=False, padx=16, pady=(6, 4))

        # 日志标题行（含折叠按钮）
        log_header = ttk.Frame(self.log_frame)
        log_header.pack(fill='x')
        ttk.Label(log_header, text="📋 日志输出",
                  style='Muted.TLabel').pack(side='left')
        self.log_toggle_btn = ttk.Button(
            log_header, text="▼ 隐藏日志", width=10,
            command=self._toggle_log)
        self.log_toggle_btn.pack(side='right')

        self.log_text = scrolledtext.ScrolledText(
            self.log_frame, height=6, wrap='word',
            font=('Consolas', 10),
            bg=self.colors['log_bg'], fg=self.colors['log_fg'],
            insertbackground=self.colors['log_fg'],
            selectbackground='#45475a',
            relief='flat', padx=8, pady=6
        )
        self.log_text.pack(fill='both', expand=True)
        self.log_text.configure(state='disabled')
        self.log_visible = True

        # 为日志文本配置标签颜色
        self.log_text.tag_config('INFO', foreground='#cdd6f4')
        self.log_text.tag_config('SUCCESS', foreground='#a6e3a1')
        self.log_text.tag_config('WARNING', foreground='#f9e2af')
        self.log_text.tag_config('ERROR', foreground='#f38ba8')
        self.log_text.tag_config('DEBUG', foreground='#94e2d5')

        # 底部操作栏
        self._build_action_bar()

    def _build_action_bar(self):
        """底部操作栏：输出文件路径 + 进度条 + 按钮"""
        # 输出文件路径显示行
        output_bar = ttk.Frame(self.root)
        output_bar.pack(fill='x', padx=16, pady=(4, 0))
        ttk.Label(output_bar, text="📂 输出文件:",
                  style='Muted.TLabel').pack(side='left')
        self.output_path_var = tk.StringVar(value="（暂无）")
        self.output_path_label = ttk.Label(
            output_bar, textvariable=self.output_path_var,
            foreground=self.colors['accent'], cursor='hand2'
        )
        self.output_path_label.pack(side='left', padx=(8, 0), fill='x', expand=True)
        # 点击路径标签也可以打开文件
        self.output_path_label.bind('<Button-1>', lambda e: self._open_output_file())

        # 进度条和按钮行
        bar = ttk.Frame(self.root)
        bar.pack(fill='x', padx=16, pady=(4, 8))

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            bar, orient='horizontal', length=400, mode='determinate',
            variable=self.progress_var, maximum=100
        )
        self.progress_bar.pack(side='left', fill='x', expand=True, padx=(0, 12))

        self.progress_label = ttk.Label(bar, text="就绪", style='Muted.TLabel',
                                        width=12, anchor='e')
        self.progress_label.pack(side='left', padx=(0, 12))

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
        """底部状态栏"""
        status = ttk.Frame(self.root, style='Card.TFrame')
        status.pack(fill='x', side='bottom')
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(status, textvariable=self.status_var,
                  style='Status.TLabel').pack(side='left', padx=10, pady=4)
        ttk.Label(status, text="© txt-convert", style='Status.TLabel').pack(
            side='right', padx=10, pady=4)

    # ------------------------------------------------------------------
    # 日志与进度
    # ------------------------------------------------------------------
    def _toggle_log(self):
        """折叠/展开日志区"""
        if self.log_visible:
            self.log_text.pack_forget()
            self.log_toggle_btn.config(text="▲ 显示日志")
            self.log_visible = False
        else:
            self.log_text.pack(fill='both', expand=True)
            self.log_toggle_btn.config(text="▼ 隐藏日志")
            self.log_visible = True

    def _poll_log_queue(self):
        """轮询日志队列并刷新显示"""
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self._append_log(msg)
        except queue.Empty:
            pass
        self.root.after(80, self._poll_log_queue)

    def _append_log(self, text: str):
        """追加日志到文本框"""
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

        self.log_text.insert('end', text + ('\n' if not text.endswith('\n') else ''),
                             tag)
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def _clear_log(self):
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.configure(state='disabled')

    def set_progress(self, value: float, label: str = None):
        """更新进度条"""
        self.progress_var.set(value)
        if label:
            self.progress_label.config(text=label)

    def set_status(self, text: str):
        """更新状态栏"""
        self.status_var.set(text)

    # ------------------------------------------------------------------
    # 任务执行（委托给 TaskRunner）
    # ------------------------------------------------------------------
    @property
    def worker_thread(self):
        """当前工作线程（兼容旧代码访问，实际由 TaskRunner 管理）"""
        return self.task_runner.worker_thread

    @property
    def cancel_flag(self):
        """取消标志（兼容旧代码访问，实际由 TaskRunner 管理）"""
        return self.task_runner.cancel_flag

    def run_task(self, target, args=(), kwargs=None,
                 on_complete=None, on_error=None):
        """在后台线程执行任务

        参数通过 TaskRunner.submit → functools.partial 在提交时冻结，
        从机制上杜绝闭包惰性求值陷阱（包括 except 块异常变量）。
        """
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
        """任务完成回调"""
        self.cancel_btn.config(state='disabled')
        if self.cancel_flag.is_set():
            self.set_status("已取消")
            self.set_progress(0, "已取消")
        else:
            self.set_status("就绪")
            self.set_progress(100, "完成")

    def _cancel_task(self):
        """取消当前任务"""
        if self.worker_thread and self.worker_thread.is_alive():
            if messagebox.askyesno("确认", "确定要取消当前任务吗？"):
                self.task_runner.cancel()
                print("⚠️ 用户已请求取消任务")
                # 注意：Python 线程无法强制终止，只能通过标志位协作取消
        else:
            messagebox.showinfo("提示", "当前没有运行中的任务")

    def _open_output_dir(self):
        """打开输出文件所在目录"""
        if not self.current_output_file:
            messagebox.showinfo("提示", "暂无输出文件，请先执行转换")
            return
        dir_path = os.path.dirname(self.current_output_file)
        if not os.path.isdir(dir_path):
            messagebox.showerror("错误", f"目录不存在: {dir_path}")
            return
        try:
            if sys.platform == 'darwin':
                # macOS: 在 Finder 中高亮显示该文件
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
        """使用系统默认程序打开输出文件"""
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
        """记录最新输出文件路径并更新界面显示"""
        self.current_output_file = path
        if path and os.path.isfile(path):
            # 显示完整路径，并提示文件大小
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
            # 路径是目录
            self.output_path_var.set(path)
            self.open_file_btn.config(state='disabled')
            self.open_dir_btn.config(state='normal')
        else:
            self.output_path_var.set("（暂无）")
            self.open_file_btn.config(state='disabled')
            self.open_dir_btn.config(state='disabled')

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
        """保存当前状态到配置文件（窗口位置/Tab/封面选项/书名作者）"""
        try:
            # 窗口位置和大小
            config.set('window_geometry', self.root.geometry())
            # 当前选中的标签页
            try:
                current_tab = self.notebook.select()
                if current_tab:
                    config.set('last_tab_index',
                               self.notebook.index(current_tab))
            except tk.TclError:
                pass
            # EpubTab 的封面选项和书名/作者
            if hasattr(self, 'tab_epub'):
                config.set('cover_choice', self.tab_epub.cover_var.get())
                config.set('last_title', self.tab_epub.title_var.get())
                config.set('last_author', self.tab_epub.author_var.get())
            config.save()
        except Exception as e:
            print(f"[CONFIG] 保存配置失败: {e}")
