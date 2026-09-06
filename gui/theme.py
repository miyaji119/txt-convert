"""主题配置（CustomTkinter 深色主题）

依赖：pip install customtkinter
"""

import platform
import customtkinter as ctk

# 全局外观设置（必须在创建根窗口前调用）
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def get_ui_font(size: int = 10, weight: str = 'normal') -> tuple:
    """返回适合当前平台的 UI 字体元组（兼容 tkinter 和 CustomTkinter）"""
    _sys = platform.system()
    if _sys == 'Darwin':
        family = 'PingFang SC'
    elif _sys == 'Windows':
        family = '微软雅黑'
    else:
        family = 'Noto Sans CJK SC'
    return (family, size, weight) if weight != 'normal' else (family, size)


# 颜色方案（用于侧边栏、日志区、状态栏等非 CTk 默认颜色的元素）
COLORS = {
    'bg': '#1c1c2e',
    'panel': '#2b2b3b',
    'accent': '#3b82f6',
    'accent_hover': '#2563eb',
    'accent_light': '#1e3a5f',
    'success': '#10b981',
    'warning': '#f59e0b',
    'error': '#ef4444',
    'text': '#e2e8f0',
    'text_muted': '#9ba8b7',
    'border': '#3d4a5c',
    # 顶部横幅
    'header_bg': '#1e3a8a',
    'header_fg': '#ffffff',
    'header_sub': '#93c5fd',
    # 日志区（深色）
    'log_bg': '#0d1117',
    'log_fg': '#e2e8f0',
}


def setup_style(root=None, colors=None):
    """设置 ttk.Treeview 深色样式（Treeview 无 CTk 替代，保留 ttk）"""
    if colors is None:
        colors = COLORS

    import tkinter.ttk as ttk
    style = ttk.Style()
    try:
        style.theme_use('default')
    except Exception:
        pass

    _sys = platform.system()
    if _sys == 'Darwin':
        _font_family = 'PingFang SC'
    elif _sys == 'Windows':
        _font_family = '微软雅黑'
    else:
        _font_family = 'Noto Sans CJK SC'

    style.configure('Treeview',
                    background='#2b2b3b',
                    foreground='#dce4ee',
                    fieldbackground='#2b2b3b',
                    borderwidth=0,
                    font=(_font_family, 10),
                    rowheight=28)
    style.configure('Treeview.Heading',
                    background='#1e2030',
                    foreground='#9ba8b7',
                    font=(_font_family, 10, 'bold'),
                    relief='flat',
                    padding=(8, 6))
    style.map('Treeview',
              background=[('selected', '#1d4ed8')],
              foreground=[('selected', '#ffffff')])
    style.map('Treeview.Heading',
              background=[('active', '#2d3748')])
