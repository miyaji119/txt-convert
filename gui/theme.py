"""主题与样式配置（基于 sv-ttk Sun Valley 主题）

使用 sv-ttk 提供现代化外观（Windows 11 风格），
保留 COLORS 字典用于非 ttk 组件（日志区、状态栏等）。

依赖：pip install sv-ttk
"""

import platform
import tkinter as tk
from tkinter import ttk

try:
    from sv_ttk import set_theme as _sv_set_theme
    HAS_SV_TTK = True
except ImportError:
    HAS_SV_TTK = False


def get_ui_font(size: int = 10, weight: str = 'normal') -> tuple:
    """返回适合当前平台的 UI 字体"""
    _sys = platform.system()
    if _sys == 'Darwin':
        family = 'PingFang SC'
    elif _sys == 'Windows':
        family = '微软雅黑'
    else:
        family = 'Noto Sans CJK SC'
    return (family, size, weight) if weight != 'normal' else (family, size)


# 颜色方案（用于非 ttk 组件，如标题横幅、日志区、状态栏指示灯）
COLORS = {
    'bg': '#f0f2f5',
    'panel': '#ffffff',
    'accent': '#2563eb',
    'accent_light': '#dbeafe',
    'accent_hover': '#1d4ed8',
    'success': '#059669',
    'warning': '#d97706',
    'error': '#dc2626',
    'text': '#111827',
    'text_muted': '#6b7280',
    'border': '#e5e7eb',
    # 标题横幅
    'header_bg': '#1e3a8a',
    'header_fg': '#ffffff',
    'header_sub': '#93c5fd',
    # 日志区配色（深色背景）
    'log_bg': '#1a1b2e',
    'log_fg': '#e2e8f0',
}


def setup_style(root: tk.Tk, colors: dict = None):
    """设置主题和样式

    优先使用 sv-ttk Sun Valley 主题，不可用时回退到 clam + 手写样式。
    """
    if colors is None:
        colors = COLORS

    sv_applied = False
    if HAS_SV_TTK:
        try:
            _sv_set_theme("light")
            _apply_custom_styles(root, colors)
            sv_applied = True
        except tk.TclError as e:
            print(f"[THEME] sv-ttk 加载失败（可能 Tk 版本过低），回退到手写样式: {e}")

    if not sv_applied:
        _apply_fallback_style(root, colors)


def _apply_custom_styles(root: tk.Tk, colors: dict):
    """在 sv-ttk 主题基础上补充自定义样式"""
    style = ttk.Style()

    # Success.TButton：绿色按钮
    style.configure('Success.TButton', font=get_ui_font(10),
                    padding=6, background=colors['success'],
                    foreground='white')
    style.map('Success.TButton',
              background=[('active', '#047857'),
                          ('disabled', '#9ca3af')])

    # Title.TLabel：标题文字
    style.configure('Title.TLabel',
                    foreground=colors['text'],
                    font=get_ui_font(14, 'bold'))

    # Muted.TLabel：次要文字
    style.configure('Muted.TLabel',
                    foreground=colors['text_muted'],
                    font=get_ui_font(9))

    # Status.TLabel：状态栏文字
    style.configure('Status.TLabel',
                    foreground=colors['text_muted'],
                    font=get_ui_font(9))

    # Card.TFrame：卡片容器（带边框）
    style.configure('Card.TFrame',
                    background=colors['panel'],
                    relief='solid', borderwidth=1)

    root.configure(bg=colors['bg'])


def _apply_fallback_style(root: tk.Tk, colors: dict):
    """sv-ttk 不可用时的回退样式"""
    style = ttk.Style()
    try:
        style.theme_use('clam')
    except tk.TclError:
        pass

    root.configure(bg=colors['bg'])

    # Frame
    style.configure('TFrame', background=colors['bg'])
    style.configure('Card.TFrame', background=colors['panel'],
                    relief='solid', borderwidth=1)

    # Label
    style.configure('TLabel', background=colors['bg'],
                    foreground=colors['text'], font=get_ui_font(10))
    style.configure('Card.TLabel', background=colors['panel'],
                    foreground=colors['text'], font=get_ui_font(10))
    style.configure('Title.TLabel', background=colors['bg'],
                    foreground=colors['text'], font=get_ui_font(14, 'bold'))
    style.configure('Muted.TLabel', background=colors['bg'],
                    foreground=colors['text_muted'], font=get_ui_font(9))
    style.configure('Status.TLabel', background=colors['panel'],
                    foreground=colors['text_muted'], font=get_ui_font(9))

    # Button
    style.configure('TButton', font=get_ui_font(10), padding=6)
    style.configure('Accent.TButton', font=get_ui_font(10, 'bold'),
                    padding=8, background=colors['accent'],
                    foreground='white')
    style.map('Accent.TButton',
              background=[('active', colors['accent_hover']),
                          ('disabled', '#9ca3af')])
    style.configure('Success.TButton', font=get_ui_font(10),
                    padding=6, background=colors['success'],
                    foreground='white')
    style.map('Success.TButton',
              background=[('active', '#047857')])

    # Entry / Combobox
    style.configure('TEntry', fieldbackground='white', padding=4)
    style.configure('TCombobox', fieldbackground='white', padding=4)

    # Notebook
    style.configure('TNotebook', background=colors['bg'])
    style.configure('TNotebook.Tab',
                    background=colors['bg'],
                    foreground=colors['text_muted'],
                    padding=(16, 8), font=get_ui_font(10))
    style.map('TNotebook.Tab',
              background=[('selected', colors['panel'])],
              foreground=[('selected', colors['accent'])])

    # Progressbar
    style.configure('Horizontal.TProgressbar',
                    background=colors['accent'],
                    troughcolor=colors['border'])

    # Treeview
    style.configure('Treeview',
                    background='#ffffff',
                    foreground=colors['text'],
                    fieldbackground='#ffffff',
                    borderwidth=0,
                    font=get_ui_font(10),
                    rowheight=28)
    style.configure('Treeview.Heading',
                    background='#f9fafb',
                    foreground=colors['text_muted'],
                    font=get_ui_font(10, 'bold'),
                    relief='flat',
                    padding=(8, 6))
    style.map('Treeview',
              background=[('selected', colors['accent_light'])],
              foreground=[('selected', colors['text'])])
    style.map('Treeview.Heading',
              background=[('active', '#e5e7eb')])
