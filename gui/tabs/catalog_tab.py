"""章节目录编辑 Tab"""

import os
import re
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from gui.tabs.base_tab import BaseTab
from config import config
from encoding import EncodingDetector
from chapter import ChapterAnalyzer


class CatalogTab(BaseTab):
    """章节目录编辑标签页：查看、编辑、移动、删除、保存章节"""

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
            btn_frame, text="▶ 加载", style='Accent.TButton',
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
            config.add_recent_file(path)
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
