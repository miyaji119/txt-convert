"""设置对话框"""

import os
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import customtkinter as ctk

from gui.theme import get_ui_font
from config import config


def show_settings(parent):
    """弹出设置对话框（模态）"""
    dialog = SettingsDialog(parent)
    parent.wait_window(dialog)
    return dialog.result


class SettingsDialog(ctk.CTkToplevel):
    """设置对话框"""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("设置")
        self.result = False
        self._pattern_vars = []

        self.transient(parent)
        self.grab_set()
        self.resizable(True, True)
        self.geometry("660x580")

        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - 660) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - 580) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        # ── 默认输出目录 ─────────────────────────────────────────────────
        s1 = ctk.CTkFrame(self, corner_radius=8)
        s1.pack(fill='x', padx=12, pady=(12, 6))
        ctk.CTkLabel(s1, text=" 默认输出目录 ",
                     text_color='#9ba8b7', font=get_ui_font(9)).pack(
            anchor='nw', padx=10, pady=(6, 2))
        inner1 = ctk.CTkFrame(s1, fg_color='transparent')
        inner1.pack(fill='x', padx=10, pady=(0, 10))

        row = ctk.CTkFrame(inner1, fg_color='transparent')
        row.pack(fill='x')
        self.output_dir_var = tk.StringVar()
        ctk.CTkEntry(row, textvariable=self.output_dir_var,
                     font=get_ui_font(10)).pack(
            side='left', fill='x', expand=True, padx=(0, 6))
        ctk.CTkButton(row, text="浏览...", width=80,
                      font=get_ui_font(10),
                      command=self._browse_output_dir).pack(side='right')
        ctk.CTkLabel(inner1, text="留空则输出到输入文件所在目录",
                     text_color='#9ba8b7', font=get_ui_font(9)).pack(
            anchor='w', pady=(4, 0))

        # ── 自定义章节正则规则 ───────────────────────────────────────────
        s2 = ctk.CTkFrame(self, corner_radius=8)
        s2.pack(fill='both', expand=True, padx=12, pady=6)
        ctk.CTkLabel(s2, text=" 自定义章节正则规则 ",
                     text_color='#9ba8b7', font=get_ui_font(9)).pack(
            anchor='nw', padx=10, pady=(6, 2))
        inner2 = ctk.CTkFrame(s2, fg_color='transparent')
        inner2.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        ctk.CTkLabel(inner2,
                     text="每行一条正则，用于识别 chapter_config.py 内置规则之外的章节格式",
                     text_color='#9ba8b7', font=get_ui_font(9)).pack(
            anchor='w', pady=(0, 4))

        # Treeview（保留 ttk — CTk 无 Treeview）
        list_frame = ctk.CTkFrame(inner2, fg_color='transparent')
        list_frame.pack(fill='both', expand=True)

        columns = ("enabled", "pattern", "type")
        self.tree = ttk.Treeview(list_frame, columns=columns,
                                  show='headings', height=6)
        self.tree.heading('enabled', text='启用')
        self.tree.heading('pattern', text='正则表达式')
        self.tree.heading('type',    text='类型')
        self.tree.column('enabled', width=50,  anchor='center')
        self.tree.column('pattern', width=420)
        self.tree.column('type',    width=100, anchor='center')

        vscroll = ctk.CTkScrollbar(list_frame, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vscroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vscroll.pack(side='right', fill='y')

        # 添加规则输入行
        input_row = ctk.CTkFrame(inner2, fg_color='transparent')
        input_row.pack(fill='x', pady=(6, 0))

        ctk.CTkLabel(input_row, text="正则:", font=get_ui_font(10)).pack(side='left')
        self.new_pattern_var = tk.StringVar()
        ctk.CTkEntry(input_row, textvariable=self.new_pattern_var,
                     font=get_ui_font(10)).pack(
            side='left', fill='x', expand=True, padx=(4, 6))

        ctk.CTkLabel(input_row, text="类型:", font=get_ui_font(10)).pack(side='left')
        self.new_type_var = tk.StringVar(value='custom')
        ctk.CTkComboBox(input_row, variable=self.new_type_var,
                        values=['custom', 'chinese', 'number',
                                'fanwai', 'volume', 'part'],
                        width=110, font=get_ui_font(10)).pack(side='left', padx=(4, 6))
        ctk.CTkButton(input_row, text="➕ 添加", width=80,
                      font=get_ui_font(10),
                      command=self._add_pattern).pack(side='left')

        # 操作按钮行
        btn_row = ctk.CTkFrame(inner2, fg_color='transparent')
        btn_row.pack(fill='x', pady=(4, 0))
        ctk.CTkButton(btn_row, text="🗑 删除选中", width=100,
                      font=get_ui_font(10),
                      command=self._delete_pattern).pack(side='left')
        ctk.CTkButton(btn_row, text="☑ 切换启用", width=100,
                      font=get_ui_font(10),
                      command=self._toggle_pattern).pack(side='left', padx=(6, 0))
        ctk.CTkLabel(btn_row, text="提示：双击行可切换启用状态",
                     text_color='#9ba8b7', font=get_ui_font(9)).pack(
            side='left', padx=(10, 0))

        self.tree.bind('<Double-1>', lambda e: self._toggle_pattern())

        # ── 底部按钮 ──────────────────────────────────────────────────────
        footer = ctk.CTkFrame(self, fg_color='transparent')
        footer.pack(fill='x', padx=12, pady=(0, 12))
        ctk.CTkButton(footer, text="取消", width=80,
                      font=get_ui_font(10),
                      command=self._on_cancel).pack(side='right')
        ctk.CTkButton(footer, text="💾 保存", width=90,
                      font=get_ui_font(10, 'bold'),
                      command=self._on_save).pack(side='right', padx=(0, 6))

    def _load_settings(self):
        self.output_dir_var.set(config.get('default_output_dir', ''))
        self._refresh_pattern_list()

    def _refresh_pattern_list(self):
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
        pattern = self.new_pattern_var.get().strip()
        if not pattern:
            messagebox.showwarning("提示", "请输入正则表达式")
            return
        try:
            re.compile(pattern)
        except re.error as e:
            messagebox.showerror("正则错误", f"正则表达式无效:\n{e}")
            return
        ptype = self.new_type_var.get().strip() or 'custom'
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
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择一条规则")
            return
        values = self.tree.item(selected[0], 'values')
        pattern = values[1]
        if messagebox.askyesno("确认", f"确定删除这条规则吗？\n\n{pattern}"):
            config.remove_chapter_pattern(pattern)
            self._refresh_pattern_list()
            self.result = True
            print(f"✓ 已删除正则规则: {pattern}")

    def _toggle_pattern(self):
        selected = self.tree.selection()
        if not selected:
            return
        item = selected[0]
        for pv in self._pattern_vars:
            if pv['item'] == item:
                pv['enabled'] = not pv['enabled']
                patterns = config.get_chapter_patterns()
                for p in patterns:
                    if p['pattern'] == pv['pattern']:
                        p['enabled'] = pv['enabled']
                        break
                config.set('custom_chapter_patterns', patterns)
                self.tree.item(item, values=(
                    '✓' if pv['enabled'] else '✗',
                    pv['pattern'], pv['type']
                ))
                self.result = True
                break

    def _on_save(self):
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
