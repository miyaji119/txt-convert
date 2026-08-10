#!/usr/bin/env python3
"""TXT转EPUB优化工具 - 图形化界面（GUI）

使用方法:
    python3 gui.py

功能:
    - 单文件转换（TXT → EPUB-ready 格式）
    - 批量转换文件夹
    - EPUB 生成（含封面选项）
    - 章节目录查看
    - 实时日志输出与进度显示
"""

import os
import re
import sys
import threading
import queue
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, scrolledtext
from datetime import datetime

# 确保能导入同目录下的模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from encoding import EncodingDetector
from display import DirectoryDisplay
from easypub import EasyPubOptimizer, convert_for_easypub, batch_convert_for_easypub
from epub import EPUBGenerator

try:
    from ebooklib import epub
    EPUB_SUPPORT = True
except ImportError:
    EPUB_SUPPORT = False

APP_VERSION = "v1.4"
APP_TITLE = f"TXT 转 EPUB 工具 {APP_VERSION}"


class TextRedirector:
    """将 print 输出重定向到 GUI 日志区"""

    def __init__(self, log_queue: queue.Queue):
        self.log_queue = log_queue

    def write(self, text):
        if text and text.strip():
            self.log_queue.put(text)

    def flush(self):
        pass


class TxtToEpubGUI:
    """主 GUI 应用类"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1080x800")
        self.root.minsize(960, 680)

        # 后台任务相关
        self.log_queue: queue.Queue = queue.Queue()
        self.worker_thread: threading.Thread = None
        self.cancel_flag = threading.Event()
        self.current_output_file = None

        # 应用主题
        self._setup_style()

        # 构建 UI
        self._build_menu()
        self._build_main_layout()
        self._build_status_bar()

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
    # 主题与样式
    # ------------------------------------------------------------------
    def _setup_style(self):
        """设置 ttk 主题和样式"""
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass

        # 颜色方案（现代蓝灰风格）
        self.colors = {
            'bg': '#f5f6f8',
            'panel': '#ffffff',
            'accent': '#2563eb',
            'accent_hover': '#1d4ed8',
            'success': '#16a34a',
            'warning': '#d97706',
            'error': '#dc2626',
            'text': '#1f2937',
            'text_muted': '#6b7280',
            'border': '#e5e7eb',
        }

        self.root.configure(bg=self.colors['bg'])

        # 配置 ttk 样式
        style.configure('TFrame', background=self.colors['bg'])
        style.configure('Card.TFrame', background=self.colors['panel'],
                        relief='solid', borderwidth=1)
        style.configure('TLabel', background=self.colors['bg'],
                        foreground=self.colors['text'], font=('微软雅黑', 10))
        style.configure('Card.TLabel', background=self.colors['panel'],
                        foreground=self.colors['text'], font=('微软雅黑', 10))
        style.configure('Title.TLabel', background=self.colors['bg'],
                        foreground=self.colors['text'], font=('微软雅黑', 14, 'bold'))
        style.configure('Muted.TLabel', background=self.colors['bg'],
                        foreground=self.colors['text_muted'], font=('微软雅黑', 9))
        style.configure('Status.TLabel', background=self.colors['panel'],
                        foreground=self.colors['text_muted'], font=('微软雅黑', 9))

        style.configure('TButton', font=('微软雅黑', 10), padding=6)
        style.configure('Primary.TButton', font=('微软雅黑', 10, 'bold'),
                        padding=8, background=self.colors['accent'],
                        foreground='white')
        style.map('Primary.TButton',
                  background=[('active', self.colors['accent_hover']),
                              ('disabled', '#9ca3af')])
        style.configure('Success.TButton', font=('微软雅黑', 10),
                        padding=6, background=self.colors['success'],
                        foreground='white')
        style.map('Success.TButton',
                  background=[('active', '#15803d')])

        style.configure('TEntry', fieldbackground='white', padding=4)
        style.configure('TCombobox', fieldbackground='white', padding=4)

        style.configure('TNotebook', background=self.colors['bg'])
        style.configure('TNotebook.Tab',
                        background=self.colors['bg'],
                        foreground=self.colors['text_muted'],
                        padding=(16, 8), font=('微软雅黑', 10))
        style.map('TNotebook.Tab',
                  background=[('selected', self.colors['panel'])],
                  foreground=[('selected', self.colors['accent'])])

        style.configure('Horizontal.TProgressbar',
                        background=self.colors['accent'],
                        troughcolor=self.colors['border'])

        # Treeview 样式（表格）
        style.configure('Treeview',
                        background='#ffffff',
                        foreground=self.colors['text'],
                        fieldbackground='#ffffff',
                        borderwidth=0,
                        font=('微软雅黑', 10),
                        rowheight=28)
        style.configure('Treeview.Heading',
                        background='#f9fafb',
                        foreground=self.colors['text_muted'],
                        font=('微软雅黑', 10, 'bold'),
                        relief='flat',
                        padding=(8, 6))
        style.map('Treeview',
                  background=[('selected', '#dbeafe')],
                  foreground=[('selected', self.colors['text'])])
        style.map('Treeview.Heading',
                  background=[('active', '#e5e7eb')])

    # ------------------------------------------------------------------
    # 菜单栏
    # ------------------------------------------------------------------
    def _build_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="打开 TXT 文件...", command=self._menu_open_txt)
        file_menu.add_command(label="打开文件夹...", command=self._menu_open_dir)
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
            font=('Consolas', 10), bg='#1e1e2e', fg='#cdd6f4',
            insertbackground='#cdd6f4', selectbackground='#45475a',
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
    # 任务执行
    # ------------------------------------------------------------------
    def run_task(self, target, args=(), kwargs=None,
                 on_complete=None, on_error=None):
        """在后台线程执行任务"""
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("提示", "已有任务正在运行，请等待完成或取消")
            return

        self.cancel_flag.clear()
        self.set_progress(0, "处理中...")
        self.set_status("处理中...")
        self.cancel_btn.config(state='normal')

        kwargs = kwargs or {}

        def _worker():
            try:
                result = target(*args, **kwargs)
                if on_complete:
                    try:
                        # 使用默认参数绑定当前值，避免闭包惰性求值问题
                        self.root.after(0, lambda r=result: on_complete(r))
                    except (RuntimeError, tk.TclError):
                        # 主窗口已关闭，忽略回调
                        pass
            except Exception as e:
                err_msg = f"❌ 任务执行失败: {e}"
                print(err_msg)
                if on_error:
                    try:
                        # 使用默认参数绑定异常对象，避免 except 块结束后 e 被删除
                        self.root.after(0, lambda err=e: on_error(err))
                    except (RuntimeError, tk.TclError):
                        pass
            finally:
                try:
                    self.root.after(0, self._task_finished)
                except (RuntimeError, tk.TclError):
                    # 主窗口已关闭，无需更新 UI
                    pass

        self.worker_thread = threading.Thread(target=_worker, daemon=True)
        self.worker_thread.start()

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
                self.cancel_flag.set()
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
            self.cancel_flag.set()
        self.root.destroy()


# ======================================================================
# 基础 Tab 类
# ======================================================================
class BaseTab:
    """标签页基类，提供通用组件构建方法"""

    def __init__(self, parent, app: TxtToEpubGUI):
        self.parent = parent
        self.app = app
        self.frame = ttk.Frame(parent, padding=16)

    def _build_file_selector(self, container, label_text, button_text,
                              file_mode=True, filetypes=None, callback=None):
        """构建文件/文件夹选择器"""
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
        """构建书名/作者输入框"""
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


# ======================================================================
# 单文件转换 Tab
# ======================================================================
class ConvertTab(BaseTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)

        # 说明文字
        ttk.Label(self.frame,
                  text="将单个 TXT 文件转换为 EPUB-ready 格式（标准化章节标题、合并段落）",
                  style='Muted.TLabel').pack(anchor='w', pady=(0, 12))

        # 文件选择器
        self.path_var = self._build_file_selector(
            self.frame, "TXT 文件:", "浏览...",
            file_mode=True,
            callback=self._on_file_selected
        )

        # 元数据输入
        self.title_var, self.author_var = self._build_meta_input(self.frame)

        # 选项
        opt_frame = ttk.Frame(self.frame)
        opt_frame.pack(fill='x', pady=(0, 8))
        self.show_catalog_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_frame, text="转换后显示章节目录",
                        variable=self.show_catalog_var).pack(side='left')

        # 操作按钮
        btn_frame = ttk.Frame(self.frame)
        btn_frame.pack(fill='x', pady=(12, 0))
        self.convert_btn = ttk.Button(
            btn_frame, text="▶ 开始转换", style='Primary.TButton',
            command=self._start_convert
        )
        self.convert_btn.pack(side='left')

        # 章节信息展示
        info_frame = ttk.LabelFrame(self.frame, text=" 文件信息 ", padding=8)
        info_frame.pack(fill='both', expand=True, pady=(12, 0))
        self.info_text = scrolledtext.ScrolledText(
            info_frame, height=8, wrap='word',
            font=('Consolas', 10), relief='flat',
            bg='#fafafa', fg='#374151'
        )
        self.info_text.pack(fill='both', expand=True)
        self.info_text.configure(state='disabled')

    def set_file_path(self, path: str):
        self.path_var.set(path)
        self._on_file_selected(path)

    def _on_file_selected(self, path: str):
        """文件被选中时自动提取书名作者"""
        if not os.path.isfile(path):
            return
        try:
            content, _ = EncodingDetector.read_file_with_auto_encoding(path)
            title = EPUBGenerator._extract_title(content) or ""
            author = EPUBGenerator._extract_author(content) or ""
            if title:
                self.title_var.set(title)
            else:
                self.title_var.set(os.path.splitext(os.path.basename(path))[0])
            if author:
                self.author_var.set(author)

            # 显示文件信息
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
            messagebox.showwarning("提示", "请先选择 TXT 文件")
            return
        if not os.path.isfile(path):
            messagebox.showerror("错误", f"文件不存在: {path}")
            return

        title = self.title_var.get().strip()
        author = self.author_var.get().strip()

        self.convert_btn.config(state='disabled')
        self.app.set_status("正在转换...")

        def _task():
            output_file, analysis = convert_for_easypub(
                path, None, title, author,
                show_catalog=self.show_catalog_var.get()
            )
            return output_file, analysis

        def _on_complete(result):
            output_file, analysis = result
            if output_file:
                self.app.set_output_file(output_file)
                print(f"\n✅ 转换完成！")
                print(f"   输出: {output_file}")
                if analysis:
                    print(f"   章节数: {analysis.get('total_chapters', 0)}")
                    print(f"   字数: {analysis.get('total_chars', 0):,}")
                messagebox.showinfo("成功", f"转换完成！\n输出文件:\n{output_file}")
            self.convert_btn.config(state='normal')

        def _on_error(e):
            self.convert_btn.config(state='normal')

        self.app.run_task(_task, on_complete=_on_complete, on_error=_on_error)


# ======================================================================
# 批量转换 Tab
# ======================================================================
class BatchTab(BaseTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)

        ttk.Label(self.frame,
                  text="批量转换文件夹内的所有 TXT 文件",
                  style='Muted.TLabel').pack(anchor='w', pady=(0, 12))

        self.dir_var = self._build_file_selector(
            self.frame, "文件夹:", "浏览...", file_mode=False
        )

        # 操作按钮
        btn_frame = ttk.Frame(self.frame)
        btn_frame.pack(fill='x', pady=(12, 0))
        self.batch_btn = ttk.Button(
            btn_frame, text="▶ 开始批量转换", style='Primary.TButton',
            command=self._start_batch
        )
        self.batch_btn.pack(side='left')

        # 结果展示
        result_frame = ttk.LabelFrame(self.frame, text=" 处理结果 ", padding=8)
        result_frame.pack(fill='both', expand=True, pady=(12, 0))

        # 使用 Treeview 展示结果
        columns = ("filename", "status", "chapters", "size")
        self.tree = ttk.Treeview(result_frame, columns=columns,
                                  show='headings', height=10)
        self.tree.heading('filename', text='文件名')
        self.tree.heading('status', text='状态')
        self.tree.heading('chapters', text='章节数')
        self.tree.heading('size', text='大小')
        self.tree.column('filename', width=300)
        self.tree.column('status', width=80, anchor='center')
        self.tree.column('chapters', width=80, anchor='center')
        self.tree.column('size', width=100, anchor='e')

        scrollbar = ttk.Scrollbar(result_frame, orient='vertical',
                                   command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # 绑定标签样式
        self.tree.tag_configure('success', foreground='#16a34a')
        self.tree.tag_configure('error', foreground='#dc2626')

    def set_dir_path(self, path: str):
        self.dir_var.set(path)

    def _start_batch(self):
        dir_path = self.dir_var.get().strip()
        if not dir_path:
            messagebox.showwarning("提示", "请先选择文件夹")
            return
        if not os.path.isdir(dir_path):
            messagebox.showerror("错误", f"文件夹不存在: {dir_path}")
            return

        # 清空之前的结果
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.batch_btn.config(state='disabled')
        self.app.set_status("批量处理中...")

        def _task():
            # 简化调用：使用底层 batch_convert_for_easypub
            results = batch_convert_for_easypub(
                dir_path, None, None, show_summary=True
            )
            return results

        def _on_complete(results):
            if results:
                for r in results:
                    filename = r.get('filename', '')
                    if 'error' in r:
                        self.tree.insert('', 'end', values=(filename, "失败", "-", "-"),
                                         tags=('error',))
                    else:
                        size = DirectoryDisplay.format_size(r.get('size', 0))
                        chapters = r.get('chapters', 0)
                        self.tree.insert('', 'end',
                                         values=(filename, "成功", chapters, size),
                                         tags=('success',))
                # 默认指向第一个输出文件
                if results and 'output_file' in results[0]:
                    self.app.set_output_file(os.path.dirname(results[0]['output_file']))
                print(f"\n✅ 批量转换完成！共处理 {len(results)} 个文件")
            self.batch_btn.config(state='normal')

        def _on_error(e):
            self.batch_btn.config(state='normal')

        self.app.run_task(_task, on_complete=_on_complete, on_error=_on_error)


# ======================================================================
# EPUB 生成 Tab
# ======================================================================
class EpubTab(BaseTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)

        if not EPUB_SUPPORT:
            ttk.Label(self.frame,
                      text="⚠️ 未检测到 ebooklib 库，请运行: pip install ebooklib pillow requests",
                      foreground='#dc2626').pack(anchor='w', pady=(0, 4))

        self.path_var = self._build_file_selector(
            self.frame, "TXT 文件:", "浏览...",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*")],
            callback=self._on_file_selected
        )

        self.title_var, self.author_var = self._build_meta_input(self.frame)

        # 工作流提示（单行精简）
        ttk.Label(
            self.frame,
            text="💡 自动检测文件类型：原始 TXT 自动转换+生成，EPUB-ready 文件直接生成",
            style='Muted.TLabel'
        ).pack(anchor='w', pady=(4, 4))

        # 章节统计信息
        stat_frame = ttk.Frame(self.frame)
        stat_frame.pack(fill='x', pady=(0, 4))
        self.stat_labels = {}
        for i, key in enumerate(['章节数', '总行数', '总字数']):
            ttk.Label(stat_frame, text=f"{key}:", width=8).grid(
                row=0, column=i*2, padx=(0, 4))
            lbl = ttk.Label(stat_frame, text="-", width=12,
                            foreground=self.app.colors['accent'])
            lbl.grid(row=0, column=i*2+1, padx=(0, 16))
            self.stat_labels[key] = lbl

        # 章节列表展示
        list_frame = ttk.LabelFrame(self.frame, text=" 章节目录 ", padding=4)
        list_frame.pack(fill='both', expand=True, pady=(4, 4))

        columns = ("num", "title", "lines", "start", "end", "chars")
        self.tree = ttk.Treeview(list_frame, columns=columns,
                                  show='headings', height=5)
        self.tree.heading('num', text='章节号')
        self.tree.heading('title', text='标题')
        self.tree.heading('lines', text='行数')
        self.tree.heading('start', text='起始行')
        self.tree.heading('end', text='结束行')
        self.tree.heading('chars', text='字数')
        self.tree.column('num', width=60, anchor='center')
        self.tree.column('title', width=300)
        self.tree.column('lines', width=70, anchor='center')
        self.tree.column('start', width=70, anchor='center')
        self.tree.column('end', width=70, anchor='center')
        self.tree.column('chars', width=80, anchor='e')

        vscroll = ttk.Scrollbar(list_frame, orient='vertical',
                                 command=self.tree.yview)
        self.tree.configure(yscrollcommand=vscroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vscroll.pack(side='right', fill='y')

        # 封面选项（水平排列，紧凑布局）
        cover_frame = ttk.LabelFrame(self.frame, text=" 封面选项 ", padding=4)
        cover_frame.pack(fill='x', pady=(0, 4))

        cover_row = ttk.Frame(cover_frame)
        cover_row.pack(fill='x')

        self.cover_var = tk.IntVar(value=4)
        options = [
            (1, "无封面"),
            (2, "本地图片"),
            (3, "图片URL"),
            (4, "自动搜索（推荐）"),
        ]
        for val, text in options:
            ttk.Radiobutton(cover_row, text=text, value=val,
                            variable=self.cover_var,
                            command=self._on_cover_change).pack(side='left', padx=(0, 12))

        self.cover_input_frame = ttk.Frame(cover_frame)
        self.cover_input_frame.pack(fill='x', pady=(2, 0))
        self.cover_input_var = tk.StringVar()
        self.cover_input_entry = ttk.Entry(self.cover_input_frame,
                                           textvariable=self.cover_input_var)
        self.cover_input_entry.pack(side='left', fill='x', expand=True, padx=(0, 4))

        self.cover_browse_btn = ttk.Button(
            self.cover_input_frame, text="浏览...",
            command=self._browse_cover
        )
        self.cover_browse_btn.pack(side='right')

        self._on_cover_change()

        # 操作按钮
        btn_frame = ttk.Frame(self.frame)
        btn_frame.pack(fill='x', pady=(8, 0))
        self.generate_btn = ttk.Button(
            btn_frame, text="🚀 一键转换并生成 EPUB", style='Primary.TButton',
            command=self._start_generate,
            state='normal' if EPUB_SUPPORT else 'disabled'
        )
        self.generate_btn.pack(side='left')
        self.reload_btn = ttk.Button(
            btn_frame, text="↻ 重新加载章节",
            command=self._reload_catalog
        )
        self.reload_btn.pack(side='left', padx=(8, 0))

    def _is_epub_ready(self, path: str) -> bool:
        """检查文件是否已经是 EPUB-ready 格式"""
        return '_epub_ready' in os.path.basename(path)

    def _on_file_selected(self, path: str):
        """文件被选中时自动加载章节目录"""
        if path and os.path.isfile(path):
            self._load_catalog(path)
            # 根据文件类型显示提示
            if self._is_epub_ready(path):
                print("💡 当前文件已是 EPUB-ready 格式，将直接生成 EPUB")
            else:
                print("💡 当前文件是原始 TXT，将自动执行：转换 → 生成 EPUB")

    def _reload_catalog(self):
        """手动重新加载章节目录"""
        path = self.path_var.get().strip()
        if not path:
            messagebox.showwarning("提示", "请先选择 TXT 文件")
            return
        if not os.path.isfile(path):
            messagebox.showerror("错误", f"文件不存在: {path}")
            return
        self._load_catalog(path)

    def _load_catalog(self, path: str):
        """加载章节目录到 Treeview"""
        # 清空之前的数据
        for item in self.tree.get_children():
            self.tree.delete(item)
        for k in self.stat_labels:
            self.stat_labels[k].config(text="-")

        self.reload_btn.config(state='disabled')
        self.app.set_status("加载章节中...")

        def _task():
            content, _ = EncodingDetector.read_file_with_auto_encoding(path)
            structure = ChapterAnalyzer.analyze_chapter_structure(content)
            return structure

        def _on_complete(structure):
            self.stat_labels['章节数'].config(
                text=str(structure.get('total_chapters', 0)))
            self.stat_labels['总行数'].config(
                text=f"{structure.get('total_lines', 0):,}")
            self.stat_labels['总字数'].config(
                text=f"{structure.get('total_chars', 0):,}")

            for ch in structure.get('chapters', []):
                self.tree.insert('', 'end', values=(
                    ch.get('number', 0),
                    ch.get('title', ''),
                    ch.get('line_count', 0),
                    ch.get('start_line', 0),
                    ch.get('end_line', 0),
                    ch.get('char_count', 0),
                ))
            print(f"✓ 已加载章节目录: {structure.get('total_chapters', 0)} 章")
            self.reload_btn.config(state='normal')

        def _on_error(e):
            self.reload_btn.config(state='normal')

        self.app.run_task(_task, on_complete=_on_complete, on_error=_on_error)

    def _on_cover_change(self):
        """根据封面选项切换输入框状态"""
        choice = self.cover_var.get()
        if choice == 2:
            self.cover_input_entry.config(state='normal')
            self.cover_browse_btn.config(state='normal')
        elif choice == 3:
            self.cover_input_entry.config(state='normal')
            self.cover_browse_btn.config(state='disabled')
        else:
            self.cover_input_entry.config(state='disabled')
            self.cover_browse_btn.config(state='disabled')
            self.cover_input_var.set('')

    def _browse_cover(self):
        # macOS Tk 多扩展名兼容格式：每类一个元组
        path = filedialog.askopenfilename(
            title="选择封面图片",
            filetypes=[
                ("JPEG 图片", "*.jpg"),
                ("JPEG 图片", "*.jpeg"),
                ("PNG 图片", "*.png"),
                ("GIF 图片", "*.gif"),
                ("WEBP 图片", "*.webp"),
                ("所有文件", "*"),
            ]
        )
        if path:
            self.cover_input_var.set(path)

    def _start_generate(self):
        """一键转换并生成 EPUB（自动检测文件类型，含详细日志）"""
        if not EPUB_SUPPORT:
            messagebox.showerror("错误", "EPUB 功能未启用，请先安装 ebooklib")
            return

        path = self.path_var.get().strip()
        if not path:
            messagebox.showwarning("提示", "请先选择 TXT 文件")
            return
        if not os.path.isfile(path):
            messagebox.showerror("错误", f"文件不存在: {path}")
            return

        title = self.title_var.get().strip()
        author = self.author_var.get().strip()

        # 解析封面选项
        cover_image = None
        auto_search = False
        cover_url = None
        choice = self.cover_var.get()
        if choice == 2:
            cover_image = self.cover_input_var.get().strip()
            if cover_image and not os.path.isfile(cover_image):
                messagebox.showerror("错误", f"封面图片不存在: {cover_image}")
                return
        elif choice == 3:
            cover_url = self.cover_input_var.get().strip()
            if not cover_url:
                messagebox.showwarning("提示", "请输入封面图片 URL")
                return
        elif choice == 4:
            auto_search = True

        # 自动判断是否需要先转换（不再需要用户勾选）
        need_convert = not self._is_epub_ready(path)

        self.generate_btn.config(state='disabled')
        self.reload_btn.config(state='disabled')

        # ===== 阶段 0：初始化日志 =====
        print("=" * 60)
        print(f"🚀 一键转换并生成 EPUB - 开始")
        print("=" * 60)
        print(f"📋 任务参数:")
        print(f"   输入文件: {path}")
        print(f"   文件大小: {self._format_size(os.path.getsize(path))}")
        print(f"   书名: {title or '(自动提取)'}")
        print(f"   作者: {author or '(自动提取)'}")
        print(f"   封面选项: {['无', '本地图片', 'URL', '自动搜索'][choice-1]}")
        if cover_image:
            print(f"   封面路径: {cover_image}")
        if cover_url:
            print(f"   封面 URL: {cover_url}")
        print(f"   工作流模式: {'转换 + 生成 EPUB' if need_convert else '直接生成 EPUB'}")
        print("-" * 60)

        if need_convert:
            self.app.set_status("步骤 1/2: 转换为 EPUB-ready 格式...")
        else:
            self.app.set_status("正在生成 EPUB...")

        def _task():
            current_path = path
            # ===== 阶段 1：自动转换（如果需要）=====
            if need_convert:
                print(f"\n📝 [步骤 1/2] 转换为 EPUB-ready 格式")
                print(f"   ⏳ 正在读取文件: {current_path}")
                try:
                    content, encoding = EncodingDetector.read_file_with_auto_encoding(current_path)
                    print(f"   ✅ 文件读取成功")
                    print(f"      编码: {encoding}")
                    print(f"      内容长度: {len(content):,} 字符")
                    print(f"      总行数: {content.count(chr(10)):,}")
                except Exception as e:
                    print(f"   ❌ 文件读取失败: {e}")
                    raise RuntimeError(f"文件读取失败: {e}")

                print(f"\n   ⏳ 正在分析章节结构...")
                try:
                    structure = ChapterAnalyzer.analyze_chapter_structure(content)
                    print(f"   ✅ 章节分析完成")
                    print(f"      识别章节数: {structure.get('total_chapters', 0)}")
                    print(f"      总行数: {structure.get('total_lines', 0):,}")
                    print(f"      总字数: {structure.get('total_chars', 0):,}")
                except Exception as e:
                    print(f"   ❌ 章节分析失败: {e}")
                    raise RuntimeError(f"章节分析失败: {e}")

                print(f"\n   ⏳ 正在执行格式转换（apply_easypub_format）...")
                try:
                    converted_path, _ = convert_for_easypub(
                        current_path, None, title, author, show_catalog=False
                    )
                    if not converted_path:
                        print(f"   ❌ 转换失败：未生成输出文件")
                        raise RuntimeError("转换失败：未生成输出文件")
                    print(f"   ✅ 转换完成")
                    print(f"      输出文件: {converted_path}")
                    print(f"      输出大小: {self._format_size(os.path.getsize(converted_path))}")
                    current_path = converted_path
                except RuntimeError:
                    raise
                except Exception as e:
                    print(f"   ❌ 转换过程异常: {e}")
                    raise RuntimeError(f"转换过程异常: {e}")

                # 验证转换后的文件
                print(f"\n   ⏳ 验证转换后的文件...")
                try:
                    new_content, new_encoding = EncodingDetector.read_file_with_auto_encoding(current_path)
                    new_structure = ChapterAnalyzer.analyze_chapter_structure(new_content)
                    print(f"   ✅ 验证通过")
                    print(f"      转换后章节数: {new_structure.get('total_chapters', 0)}")
                    print(f"      转换后行数: {new_structure.get('total_lines', 0):,}")
                    print(f"      转换后字数: {new_structure.get('total_chars', 0):,}")
                except Exception as e:
                    print(f"   ⚠️ 验证失败（不影响后续步骤）: {e}")

                self.app.set_status("步骤 2/2: 生成 EPUB...")

            # ===== 阶段 2：生成 EPUB =====
            print(f"\n📖 [步骤 {'2/2' if need_convert else '1/1'}] 生成 EPUB")
            print(f"   ⏳ 正在调用 EPUB 生成器...")
            print(f"      输入文件: {current_path}")
            print(f"      输入大小: {self._format_size(os.path.getsize(current_path))}")

            try:
                epub_path = EPUBGenerator.txt_to_epub(
                    current_path, None, title, author,
                    cover_image, auto_search, cover_url
                )
                if not epub_path:
                    print(f"   ❌ EPUB 生成失败：未生成输出文件")
                    raise RuntimeError("EPUB 生成失败：未生成输出文件")
                print(f"   ✅ EPUB 生成成功")
                print(f"      输出文件: {epub_path}")
                print(f"      输出大小: {self._format_size(os.path.getsize(epub_path))}")
            except RuntimeError:
                raise
            except Exception as e:
                print(f"   ❌ EPUB 生成过程异常: {e}")
                raise RuntimeError(f"EPUB 生成过程异常: {e}")

            return epub_path, current_path

        def _on_complete(result):
            epub_path, final_txt_path = result
            print("\n" + "=" * 60)
            print(f"✅ 全部任务完成！")
            print("=" * 60)
            print(f"📕 EPUB 文件: {epub_path}")
            print(f"      大小: {self._format_size(os.path.getsize(epub_path))}")
            if need_convert:
                print(f"📝 EPUB-ready 文件: {final_txt_path}")
                print(f"      大小: {self._format_size(os.path.getsize(final_txt_path))}")
            print("=" * 60)

            if epub_path:
                # 更新界面显示输出文件路径
                self.app.set_output_file(epub_path)
                messagebox.showinfo(
                    "成功",
                    f"EPUB 生成完成！\n\n"
                    f"📕 EPUB 文件:\n{epub_path}\n\n"
                    f"💡 可在底部点击「打开文件」按钮直接查看。"
                )
                # 如果转换过，更新文件路径显示
                if need_convert:
                    self.path_var.set(final_txt_path)
                    self._load_catalog(final_txt_path)
            self.generate_btn.config(
                state='normal' if EPUB_SUPPORT else 'disabled')
            self.reload_btn.config(state='normal')
            self.app.set_status("就绪")

        def _on_error(e):
            print("\n" + "=" * 60)
            print(f"❌ 任务失败: {e}")
            print("=" * 60)
            messagebox.showerror(
                "失败",
                f"任务失败：{e}\n\n请查看下方日志区了解详细错误信息。"
            )
            self.generate_btn.config(
                state='normal' if EPUB_SUPPORT else 'disabled')
            self.reload_btn.config(state='normal')
            self.app.set_status("失败")

        self.app.run_task(_task, on_complete=_on_complete, on_error=_on_error)

    @staticmethod
    def _format_size(size: int) -> str:
        """格式化文件大小"""
        if size >= 1024 * 1024:
            return f"{size/1024/1024:.2f} MB"
        elif size >= 1024:
            return f"{size/1024:.1f} KB"
        else:
            return f"{size} B"


# ======================================================================
# 章节目录编辑 Tab
# ======================================================================
class CatalogTab(BaseTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)

        self.path_var = self._build_file_selector(
            self.frame, "TXT 文件:", "浏览...",
            callback=self._on_file_selected
        )

        # 操作按钮 + 统计信息（合并为一行）
        btn_frame = ttk.Frame(self.frame)
        btn_frame.pack(fill='x', pady=(4, 4))
        self.load_btn = ttk.Button(
            btn_frame, text="▶ 加载", style='Primary.TButton',
            command=self._load_catalog
        )
        self.load_btn.pack(side='left')

        self.save_btn = ttk.Button(
            btn_frame, text="💾 保存修改",
            command=self._save_changes,
            state='disabled'
        )
        self.save_btn.pack(side='left', padx=(8, 0))

        self.reload_btn = ttk.Button(
            btn_frame, text="↻ 重新加载",
            command=self._load_catalog,
            state='disabled'
        )
        self.reload_btn.pack(side='left', padx=(8, 0))

        # 统计信息放在右侧
        self.stat_labels = {}
        stat_container = ttk.Frame(btn_frame)
        stat_container.pack(side='right')
        for i, key in enumerate(['章节数', '总行数', '总字数']):
            ttk.Label(stat_container, text=f"{key}:").grid(
                row=0, column=i*2, padx=(8, 2))
            lbl = ttk.Label(stat_container, text="-",
                            foreground=self.app.colors['accent'])
            lbl.grid(row=0, column=i*2+1, padx=(0, 4))
            self.stat_labels[key] = lbl

        self.changes_label = ttk.Label(btn_frame, text="",
                                       foreground='#f59e0b',
                                       font=('', 9, 'bold'))
        self.changes_label.pack(side='right', padx=(12, 0))

        # 编辑工具栏（单行紧凑布局）
        tool_frame = ttk.LabelFrame(self.frame, text=" 编辑工具 ", padding=4)
        tool_frame.pack(fill='x', pady=(0, 4))

        # 编辑行：章节号 + 标题 + 应用 + 上移/下移/删除
        edit_row = ttk.Frame(tool_frame)
        edit_row.pack(fill='x')

        ttk.Label(edit_row, text="章节号:").pack(side='left')
        self.edit_num_var = tk.StringVar()
        self.edit_num_entry = ttk.Entry(edit_row, textvariable=self.edit_num_var,
                                        width=6)
        self.edit_num_entry.pack(side='left', padx=(4, 8))

        ttk.Label(edit_row, text="标题:").pack(side='left')
        self.edit_title_var = tk.StringVar()
        self.edit_title_entry = ttk.Entry(edit_row, textvariable=self.edit_title_var)
        self.edit_title_entry.pack(side='left', fill='x', expand=True, padx=(4, 4))

        self.apply_title_btn = ttk.Button(edit_row, text="✓ 应用",
                                           command=self._apply_title_edit,
                                           state='disabled')
        self.apply_title_btn.pack(side='left', padx=(4, 8))

        ttk.Separator(edit_row, orient='vertical').pack(side='left', fill='y', padx=4)

        self.move_up_btn = ttk.Button(edit_row, text="⬆",
                                      command=self._move_chapter_up,
                                      state='disabled', width=3)
        self.move_up_btn.pack(side='left', padx=2)

        self.move_down_btn = ttk.Button(edit_row, text="⬇",
                                        command=self._move_chapter_down,
                                        state='disabled', width=3)
        self.move_down_btn.pack(side='left', padx=2)

        self.delete_btn = ttk.Button(edit_row, text="🗑 删除",
                                     command=self._delete_chapter,
                                     state='disabled', width=6)
        self.delete_btn.pack(side='left', padx=2)

        # 章节列表
        list_frame = ttk.LabelFrame(self.frame, text=" 章节列表 ", padding=4)
        list_frame.pack(fill='both', expand=True)

        columns = ("num", "title", "lines", "start", "end", "chars")
        self.tree = ttk.Treeview(list_frame, columns=columns,
                                  show='headings', height=10,
                                  selectmode='browse')
        self.tree.heading('num', text='章节号')
        self.tree.heading('title', text='标题')
        self.tree.heading('lines', text='行数')
        self.tree.heading('start', text='起始行')
        self.tree.heading('end', text='结束行')
        self.tree.heading('chars', text='字数')
        self.tree.column('num', width=60, anchor='center')
        self.tree.column('title', width=350)
        self.tree.column('lines', width=70, anchor='center')
        self.tree.column('start', width=70, anchor='center')
        self.tree.column('end', width=70, anchor='center')
        self.tree.column('chars', width=80, anchor='e')

        # 标签配置
        self.tree.tag_configure('modified', background='#fffbeb',
                                foreground='#d97706')

        vscroll = ttk.Scrollbar(list_frame, orient='vertical',
                                 command=self.tree.yview)
        self.tree.configure(yscrollcommand=vscroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vscroll.pack(side='right', fill='y')

        # 事件绑定
        self.tree.bind('<<TreeviewSelect>>', self._on_tree_select)
        self.tree.bind('<Double-1>', self._on_tree_double_click)
        self.edit_title_entry.bind('<Return>', lambda e: self._apply_title_edit())

        # 状态数据
        self.chapters_data = []  # 原始章节数据
        self.modified_ids = set()  # 已修改的 tree item id
        self.changes_count = 0  # 修改数量
        self.file_content = None  # 文件原始内容
        self.file_encoding = None  # 文件编码

    def set_file_path(self, path: str):
        self.path_var.set(path)
        self._on_file_selected(path)

    def _on_file_selected(self, path: str):
        """文件选中时自动加载"""
        if path and os.path.isfile(path):
            self._load_catalog()

    def _reset_editor(self):
        """重置编辑器状态"""
        self.chapters_data = []
        self.modified_ids.clear()
        self.changes_count = 0
        self.file_content = None
        self.file_encoding = None
        self.changes_label.config(text="")
        self.edit_num_var.set("")
        self.edit_title_var.set("")
        self.save_btn.config(state='disabled')
        self.reload_btn.config(state='disabled')
        self.apply_title_btn.config(state='disabled')
        self._update_move_buttons()

    def _update_move_buttons(self):
        """根据选中位置更新上下移按钮状态"""
        selected = self.tree.selection()
        if not selected:
            self.move_up_btn.config(state='disabled')
            self.move_down_btn.config(state='disabled')
            self.delete_btn.config(state='disabled')
            self.apply_title_btn.config(state='disabled')
            return

        children = self.tree.get_children()
        idx = children.index(selected[0])

        self.move_up_btn.config(state='normal' if idx > 0 else 'disabled')
        self.move_down_btn.config(state='normal' if idx < len(children) - 1 else 'disabled')
        self.delete_btn.config(state='normal')
        self.apply_title_btn.config(
            state='normal' if self.edit_title_var.get() else 'disabled')

    def _mark_change(self, item_id=None):
        """标记修改"""
        self.changes_count += 1
        if item_id:
            self.modified_ids.add(item_id)
            self.tree.item(item_id, tags=('modified',))
        self.changes_label.config(text=f"  📝 已有 {self.changes_count} 处修改")
        self.save_btn.config(state='normal')
        self.reload_btn.config(state='normal')

    def _load_catalog(self):
        path = self.path_var.get().strip()
        if not path:
            messagebox.showwarning("提示", "请先选择 TXT 文件")
            return
        if not os.path.isfile(path):
            messagebox.showerror("错误", f"文件不存在: {path}")
            return

        # 如果有未保存的修改，提示
        if self.changes_count > 0:
            if not messagebox.askyesno(
                "提示", f"存在 {self.changes_count} 处未保存的修改，重新加载将丢失修改，是否继续？"
            ):
                return

        self.load_btn.config(state='disabled')
        self._reset_editor()
        self.app.set_status("加载章节中...")

        # 清空之前的数据
        for item in self.tree.get_children():
            self.tree.delete(item)
        for k in self.stat_labels:
            self.stat_labels[k].config(text="-")

        def _task():
            content, encoding = EncodingDetector.read_file_with_auto_encoding(path)
            structure = ChapterAnalyzer.analyze_chapter_structure(content)
            return structure, content, encoding

        def _on_complete(result):
            structure, content, encoding = result
            self.file_content = content
            self.file_encoding = encoding

            self.stat_labels['章节数'].config(
                text=str(structure.get('total_chapters', 0)))
            self.stat_labels['总行数'].config(
                text=f"{structure.get('total_lines', 0):,}")
            self.stat_labels['总字数'].config(
                text=f"{structure.get('total_chars', 0):,}")

            self.chapters_data = []
            for ch in structure.get('chapters', []):
                item = self.tree.insert('', 'end', values=(
                    ch.get('number', 0),
                    ch.get('title', ''),
                    ch.get('line_count', 0),
                    ch.get('start_line', 0),
                    ch.get('end_line', 0),
                    ch.get('char_count', 0),
                ))
                self.chapters_data.append({
                    'number': ch.get('number', 0),
                    'title': ch.get('title', ''),
                    'start_line': ch.get('start_line', 0),
                    'end_line': ch.get('end_line', 0),
                    'line_count': ch.get('line_count', 0),
                    'char_count': ch.get('char_count', 0),
                    'content_start': ch.get('start_line', 0),
                    'content_end': ch.get('end_line', 0),
                })
            print(f"✓ 已加载章节目录: {structure.get('total_chapters', 0)} 章")
            self.load_btn.config(state='normal')

        def _on_error(e):
            self.load_btn.config(state='normal')

        self.app.run_task(_task, on_complete=_on_complete, on_error=_on_error)

    def _on_tree_select(self, event=None):
        """选中章节时更新编辑框"""
        selected = self.tree.selection()
        self._update_move_buttons()
        if not selected:
            self.edit_num_var.set("")
            self.edit_title_var.set("")
            return
        values = self.tree.item(selected[0], 'values')
        self.edit_num_var.set(str(values[0]))
        self.edit_title_var.set(str(values[1]))

    def _on_tree_double_click(self, event=None):
        """双击章节直接编辑标题"""
        self._edit_selected_title()

    def _edit_selected_title(self):
        """将焦点移到标题输入框"""
        selected = self.tree.selection()
        if not selected:
            return
        self.edit_title_entry.focus_set()
        self.edit_title_entry.select_range(0, 'end')

    def _apply_title_edit(self):
        """应用章节修改（章节号和标题）"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择一个章节")
            return

        item_id = selected[0]
        values = list(self.tree.item(item_id, 'values'))
        old_num = str(values[0])
        old_title = str(values[1])

        new_title = self.edit_title_var.get().strip()
        new_num_str = self.edit_num_var.get().strip()

        if not new_title:
            messagebox.showwarning("提示", "标题不能为空")
            return

        # 解析章节号
        try:
            new_num = int(new_num_str)
        except ValueError:
            messagebox.showwarning("提示", f"章节号必须是整数：{new_num_str}")
            return

        # 检查是否有变化
        num_changed = str(new_num) != old_num
        title_changed = old_title != new_title

        if not num_changed and not title_changed:
            messagebox.showinfo("提示", "没有变化")
            return

        # 构建确认信息
        changes = []
        if num_changed:
            changes.append(f"章节号：{old_num} → {new_num}")
        if title_changed:
            changes.append(f"标题：{old_title} → {new_title}")

        if not messagebox.askyesno(
            "确认修改",
            "确定要修改吗？\n\n" + "\n".join(changes)
        ):
            return

        # 更新 Treeview
        values[0] = new_num
        values[1] = new_title
        self.tree.item(item_id, values=values)

        # 同步更新 chapters_data
        children = self.tree.get_children()
        idx = children.index(item_id)
        if 0 <= idx < len(self.chapters_data):
            self.chapters_data[idx]['number'] = new_num
            self.chapters_data[idx]['title'] = new_title

        self._mark_change(item_id)
        print(f"✏️ 章节 {old_num} 已修改")
        if num_changed:
            print(f"   章节号：{old_num} → {new_num}")
        if title_changed:
            print(f"   标题：{old_title} → {new_title}")

    def _move_chapter_up(self):
        """上移选中章节"""
        selected = self.tree.selection()
        if not selected:
            return
        item_id = selected[0]
        children = self.tree.get_children()
        idx = children.index(item_id)
        if idx <= 0:
            return

        prev_id = children[idx - 1]

        # 交换 Treeview 位置
        self.tree.move(item_id, '', idx - 1)

        # 交换 chapters_data 顺序
        self.chapters_data[idx], self.chapters_data[idx - 1] = \
            self.chapters_data[idx - 1], self.chapters_data[idx]

        # 重新分配章节号
        self._renumber_chapters()

        # 保持选中
        self.tree.selection_set(item_id)
        self.tree.see(item_id)
        self._update_move_buttons()

        self._mark_change(item_id)
        self._mark_change(prev_id)
        num = self.edit_num_var.get()
        print(f"⬆ 章节 {num} 上移一位")

    def _move_chapter_down(self):
        """下移选中章节"""
        selected = self.tree.selection()
        if not selected:
            return
        item_id = selected[0]
        children = self.tree.get_children()
        idx = children.index(item_id)
        if idx >= len(children) - 1:
            return

        next_id = children[idx + 1]

        # 交换 Treeview 位置
        self.tree.move(item_id, '', idx + 1)

        # 交换 chapters_data 顺序
        self.chapters_data[idx], self.chapters_data[idx + 1] = \
            self.chapters_data[idx + 1], self.chapters_data[idx]

        # 重新分配章节号
        self._renumber_chapters()

        # 保持选中
        self.tree.selection_set(item_id)
        self.tree.see(item_id)
        self._update_move_buttons()

        self._mark_change(item_id)
        self._mark_change(next_id)
        num = self.edit_num_var.get()
        print(f"⬇ 章节 {num} 下移一位")

    def _renumber_chapters(self):
        """根据当前顺序重新分配连续的章节号"""
        children = self.tree.get_children()
        for idx, item_id in enumerate(children):
            values = list(self.tree.item(item_id, 'values'))
            old_title = str(values[1])
            old_num = int(values[0])
            new_num = idx + 1

            # 替换标题中的章节号
            new_title = re.sub(
                r'^第[零一二三四五六七八九十百千万\d]+(章|卷|案|节|部分)',
                f'第{new_num}\\1',
                old_title,
                count=1
            )
            # 如果标题本身没变化，补全章节号前缀
            if new_title == old_title and not re.match(
                    r'^第[零一二三四五六七八九十百千万\d]+[章卷案节部分]', old_title):
                new_title = f"第{new_num}章 {old_title}"

            values[0] = new_num
            values[1] = new_title
            self.tree.item(item_id, values=values)
            if 0 <= idx < len(self.chapters_data):
                self.chapters_data[idx]['number'] = new_num
                self.chapters_data[idx]['title'] = new_title

        # 同步编辑框显示
        selected = self.tree.selection()
        if selected:
            v = self.tree.item(selected[0], 'values')
            self.edit_num_var.set(str(v[0]))
            self.edit_title_var.set(str(v[1]))

    def _delete_chapter(self):
        """删除选中章节"""
        selected = self.tree.selection()
        if not selected:
            return
        item_id = selected[0]
        values = self.tree.item(item_id, 'values')
        chapter_num = values[0]
        chapter_title = values[1]

        if not messagebox.askyesno(
            "确认删除",
            f"确定要删除这个章节吗？\n\n第{chapter_num}章：{chapter_title}\n\n"
            f"⚠️ 注意：删除后，该章节的正文内容也会从输出文件中移除。"
        ):
            return

        children = self.tree.get_children()
        idx = children.index(item_id)

        # 删除 Treeview 项
        self.tree.delete(item_id)

        # 删除 chapters_data
        if 0 <= idx < len(self.chapters_data):
            del self.chapters_data[idx]

        # 重新编号
        self._renumber_chapters()

        # 更新统计
        old_total = int(self.stat_labels['章节数'].cget('text')) if \
            str(self.stat_labels['章节数'].cget('text')).isdigit() else 0
        self.stat_labels['章节数'].config(text=str(max(0, old_total - 1)))

        # 清空选择
        self.edit_num_var.set("")
        self.edit_title_var.set("")
        self._update_move_buttons()

        self.changes_count += 1
        self.changes_label.config(text=f"  📝 已有 {self.changes_count} 处修改")
        self.save_btn.config(state='normal')
        self.reload_btn.config(state='normal')

        print(f"🗑 已删除章节：{chapter_title}")
        print(f"   当前章节数：{max(0, old_total - 1)}")

    def _apply_pending_edits(self):
        """保存前自动应用编辑框中未提交的修改"""
        selected = self.tree.selection()
        if not selected:
            return
        item_id = selected[0]
        values = list(self.tree.item(item_id, 'values'))
        old_num = str(values[0])
        old_title = str(values[1])

        new_title = self.edit_title_var.get().strip()
        new_num_str = self.edit_num_var.get().strip()
        if not new_title:
            return
        try:
            new_num = int(new_num_str)
        except ValueError:
            return

        # 无变化则跳过
        if str(new_num) == old_num and old_title == new_title:
            return

        # 直接应用，不弹确认框
        values[0] = new_num
        values[1] = new_title
        self.tree.item(item_id, values=values)
        children = self.tree.get_children()
        idx = children.index(item_id)
        if 0 <= idx < len(self.chapters_data):
            self.chapters_data[idx]['number'] = new_num
            self.chapters_data[idx]['title'] = new_title
        self._mark_change(item_id)

    def _save_changes(self):
        """保存修改到文件"""
        if self.file_content is None:
            messagebox.showerror("错误", "请先加载文件")
            return
        if not self.chapters_data:
            messagebox.showwarning("提示", "没有章节数据")
            return

        # 自动应用编辑框中未提交的修改
        self._apply_pending_edits()

        path = self.path_var.get().strip()

        # 默认输出文件名：原文件名 + _edited 后缀
        input_path = Path(path)
        default_output = str(
            input_path.parent / f"{input_path.stem}_edited{input_path.suffix}")

        output_file = filedialog.asksaveasfilename(
            title="保存为",
            defaultextension=".txt",
            initialfile=os.path.basename(default_output),
            initialdir=os.path.dirname(default_output),
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*")]
        )
        if not output_file:
            return

        self.save_btn.config(state='disabled')
        self.app.set_status("保存文件中...")

        try:
            lines = self.file_content.split('\n')
            chapter_contents = []

            for ch in self.chapters_data:
                s = ch.get('content_start', ch.get('start_line', 0)) - 1
                e = ch.get('content_end', ch.get('end_line', 0)) - 1
                s = max(0, min(s, len(lines) - 1))
                e = max(s, min(e, len(lines) - 1))

                section_lines = lines[s:e + 1]
                if section_lines:
                    new_title_line = ch['title']
                    stripped = section_lines[0].lstrip()
                    if stripped and stripped[0] in '=*#':
                        prefix_match = re.match(r'^([=*#◇◆•·\s]+)',
                                                section_lines[0])
                        prefix = prefix_match.group(1) if prefix_match else ''
                        section_lines[0] = f"{prefix}{new_title_line}"
                    else:
                        section_lines[0] = new_title_line

                chapter_contents.append('\n'.join(section_lines))

            # 处理前置内容
            first_start = (self.chapters_data[0].get('content_start',
                             self.chapters_data[0].get('start_line', 0)) - 1)
            first_start = max(0, first_start)
            pre_lines = lines[:first_start]
            pre_content = '\n'.join(pre_lines)

            # 合并输出
            output_parts = []
            if pre_content.strip():
                output_parts.append(pre_content)
            output_parts.extend(chapter_contents)
            output_text = '\n\n'.join(output_parts) + '\n'

            # 写入文件
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(output_text)

            # 保存成功
            self.save_btn.config(state='normal')
            self.app.set_output_file(output_file)
            self.changes_count = 0
            self.modified_ids.clear()
            self.changes_label.config(text="  ✅ 修改已保存", foreground='#10b981')
            for item in self.tree.get_children():
                self.tree.item(item, tags=())
            print(f"\n💾 修改已保存：{output_file}")
            print(f"   章节数：{len(self.chapters_data)}")
            self.app.set_status("保存完成")
            messagebox.showinfo(
                "保存成功",
                f"修改已保存到：\n{output_file}\n\n"
                f"共 {len(self.chapters_data)} 章"
            )
        except Exception as e:
            self.save_btn.config(state='normal')
            self.app.set_status("保存失败")
            print(f"❌ 保存失败: {e}")
            messagebox.showerror("保存失败", f"错误信息：{e}")


# 需要在 CatalogTab 中导入 ChapterAnalyzer
from chapter import ChapterAnalyzer


# ======================================================================
# 主入口
# ======================================================================
def main():
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


if __name__ == '__main__':
    main()
