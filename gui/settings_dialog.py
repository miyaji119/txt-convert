"""设置对话框

管理用户配置：
- 默认输出目录
- 自定义章节正则规则（添加/删除/启用/禁用）

用法：
    from gui.settings_dialog import show_settings
    show_settings(parent)
"""

import os
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from config import config


def show_settings(parent):
    """弹出设置对话框（模态）"""
    dialog = SettingsDialog(parent)
    parent.wait_window(dialog)
    return dialog.result


class SettingsDialog(tk.Toplevel):
    """设置对话框"""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("设置")
        self.result = False  # 是否有修改
        self._pattern_vars = []  # 自定义规则的 BooleanVar/StringVar 引用

        self.transient(parent)
        self.grab_set()
        self.resizable(True, True)
        self.geometry("640x560")

        # 居中
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - 640) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - 560) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        # ===== 默认输出目录 =====
        output_frame = ttk.LabelFrame(self, text=" 默认输出目录 ", padding=10)
        output_frame.pack(fill='x', padx=12, pady=(12, 6))

        row = ttk.Frame(output_frame)
        row.pack(fill='x')
        self.output_dir_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.output_dir_var).pack(
            side='left', fill='x', expand=True, padx=(0, 4))
        ttk.Button(row, text="浏览...",
                   command=self._browse_output_dir).pack(side='right')
        ttk.Label(output_frame,
                  text="留空则输出到输入文件所在目录",
                  style='Muted.TLabel').pack(anchor='w', pady=(4, 0))

        # ===== 自定义章节正则规则 =====
        regex_frame = ttk.LabelFrame(
            self, text=" 自定义章节正则规则 ", padding=10)
        regex_frame.pack(fill='both', expand=True, padx=12, pady=6)

        ttk.Label(regex_frame,
                  text="每行一条正则表达式，用于识别 chapter_config.py 内置规则之外的章节格式",
                  style='Muted.TLabel').pack(anchor='w', pady=(0, 4))

        # 规则列表（Treeview）
        list_container = ttk.Frame(regex_frame)
        list_container.pack(fill='both', expand=True)

        columns = ("enabled", "pattern", "type")
        self.tree = ttk.Treeview(list_container, columns=columns,
                                  show='headings', height=6)
        self.tree.heading('enabled', text='启用')
        self.tree.heading('pattern', text='正则表达式')
        self.tree.heading('type', text='类型')
        self.tree.column('enabled', width=50, anchor='center')
        self.tree.column('pattern', width=400)
        self.tree.column('type', width=100, anchor='center')

        vscroll = ttk.Scrollbar(list_container, orient='vertical',
                                 command=self.tree.yview)
        self.tree.configure(yscrollcommand=vscroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vscroll.pack(side='right', fill='y')

        # 添加规则的输入行
        input_row = ttk.Frame(regex_frame)
        input_row.pack(fill='x', pady=(6, 0))

        ttk.Label(input_row, text="正则:").pack(side='left')
        self.new_pattern_var = tk.StringVar()
        ttk.Entry(input_row, textvariable=self.new_pattern_var).pack(
            side='left', fill='x', expand=True, padx=(4, 4))

        ttk.Label(input_row, text="类型:").pack(side='left')
        self.new_type_var = tk.StringVar(value='custom')
        type_combo = ttk.Combobox(input_row, textvariable=self.new_type_var,
                                   values=['custom', 'chinese', 'number',
                                           'fanwai', 'volume', 'part'],
                                   width=10, state='readonly')
        type_combo.pack(side='left', padx=(4, 4))

        ttk.Button(input_row, text="➕ 添加",
                   command=self._add_pattern).pack(side='left')

        # 删除按钮
        btn_row = ttk.Frame(regex_frame)
        btn_row.pack(fill='x', pady=(4, 0))
        ttk.Button(btn_row, text="🗑 删除选中",
                   command=self._delete_pattern).pack(side='left')
        ttk.Button(btn_row, text="☑ 切换启用",
                   command=self._toggle_pattern).pack(side='left', padx=(4, 0))
        ttk.Label(btn_row, text="提示：双击行可切换启用状态",
                  style='Muted.TLabel').pack(side='left', padx=(8, 0))

        self.tree.bind('<Double-1>', lambda e: self._toggle_pattern())

        # ===== 底部按钮 =====
        footer = ttk.Frame(self, padding=(12, 6))
        footer.pack(fill='x')
        ttk.Button(footer, text="取消",
                   command=self._on_cancel).pack(side='right')
        ttk.Button(footer, text="💾 保存", style='Accent.TButton',
                   command=self._on_save).pack(side='right', padx=(4, 0))

    def _load_settings(self):
        """从 config 加载当前设置"""
        self.output_dir_var.set(config.get('default_output_dir', ''))
        self._refresh_pattern_list()

    def _refresh_pattern_list(self):
        """刷新正则规则列表"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._pattern_vars = []
        for p in config.get_chapter_patterns():
            enabled_text = '✓' if p.get('enabled', True) else '✗'
            item = self.tree.insert('', 'end', values=(
                enabled_text, p['pattern'], p.get('type', 'custom')
            ))
            self._pattern_vars.append({
                'item': item,
                'pattern': p['pattern'],
                'type': p.get('type', 'custom'),
                'enabled': p.get('enabled', True),
            })

    def _browse_output_dir(self):
        path = filedialog.askdirectory(title="选择默认输出目录")
        if path:
            self.output_dir_var.set(path)

    def _add_pattern(self):
        """添加新的正则规则"""
        pattern = self.new_pattern_var.get().strip()
        if not pattern:
            messagebox.showwarning("提示", "请输入正则表达式")
            return

        # 验证正则合法性
        try:
            re.compile(pattern)
        except re.error as e:
            messagebox.showerror("正则错误", f"正则表达式无效:\n{e}")
            return

        ptype = self.new_type_var.get().strip() or 'custom'

        # 检查是否已存在
        existing = config.get_chapter_patterns()
        if any(p.get('pattern') == pattern for p in existing):
            messagebox.showwarning("提示", "该正则规则已存在")
            return

        config.add_chapter_pattern(pattern, ptype, enabled=True)
        self.new_pattern_var.set('')
        self._refresh_pattern_list()
        self.result = True
        print(f"✓ 已添加正则规则: {pattern}")

    def _delete_pattern(self):
        """删除选中的正则规则"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择一条规则")
            return
        item = selected[0]
        values = self.tree.item(item, 'values')
        pattern = values[1]
        if messagebox.askyesno("确认", f"确定删除这条规则吗？\n\n{pattern}"):
            config.remove_chapter_pattern(pattern)
            self._refresh_pattern_list()
            self.result = True
            print(f"✓ 已删除正则规则: {pattern}")

    def _toggle_pattern(self):
        """切换选中规则的启用状态"""
        selected = self.tree.selection()
        if not selected:
            return
        item = selected[0]
        # 找到对应的 pattern
        for pv in self._pattern_vars:
            if pv['item'] == item:
                pv['enabled'] = not pv['enabled']
                # 更新 config
                patterns = config.get_chapter_patterns()
                for p in patterns:
                    if p['pattern'] == pv['pattern']:
                        p['enabled'] = pv['enabled']
                        break
                config.set('custom_chapter_patterns', patterns)
                # 更新显示
                self.tree.item(item, values=(
                    '✓' if pv['enabled'] else '✗',
                    pv['pattern'], pv['type']
                ))
                self.result = True
                break

    def _on_save(self):
        """保存设置"""
        config.set('default_output_dir', self.output_dir_var.get().strip())
        if config.save():
            self.result = True
            messagebox.showinfo("成功", "设置已保存")
            self.destroy()
        else:
            messagebox.showerror("错误", "保存失败，请检查文件权限")

    def _on_cancel(self):
        self.result = False
        self.destroy()
