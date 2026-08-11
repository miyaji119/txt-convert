"""批量转换 Tab"""

import os
from tkinter import ttk, messagebox

from gui.tabs.base_tab import BaseTab
from config import config
from display import DirectoryDisplay
from easypub import batch_convert_for_easypub


class BatchTab(BaseTab):
    """批量转换标签页：批量处理文件夹内所有 TXT 文件"""

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
            btn_frame, text="▶ 开始批量转换", style='Accent.TButton',
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

        config.add_recent_dir(dir_path)

        # 清空之前的结果
        for item in self.tree.get_children():
            self.tree.delete(item)

        _IDLE = "▶ 开始批量转换"
        self.app.set_btn_working(self.batch_btn, True, _IDLE, "⏳ 批量处理中…")
        self.app.set_status("批量处理中...")

        def _task():
            results = batch_convert_for_easypub(
                dir_path, None, None, show_summary=True
            )
            return results

        def _on_complete(results):
            success_count = 0
            if results:
                for r in results:
                    filename = r.get('filename', '')
                    if 'error' in r:
                        self.tree.insert('', 'end', values=(filename, "失败", "-", "-"),
                                         tags=('error',))
                    else:
                        success_count += 1
                        size = DirectoryDisplay.format_size(r.get('size', 0))
                        chapters = r.get('chapters', 0)
                        self.tree.insert('', 'end',
                                         values=(filename, "成功", chapters, size),
                                         tags=('success',))
                if results and 'output_file' in results[0]:
                    self.app.set_output_file(os.path.dirname(results[0]['output_file']))
                print(f"\n✅ 批量转换完成！共处理 {len(results)} 个文件")
            ok = success_count > 0
            self.app.flash_btn_done(self.batch_btn, _IDLE, success=ok)
            self.app.set_nav_badge(1, f'{success_count}✓' if ok else '✗',
                                   '#86efac' if ok else '#fca5a5')

        def _on_error(e):
            self.app.flash_btn_done(self.batch_btn, _IDLE, success=False)
            self.app.set_nav_badge(1, '✗', '#fca5a5')

        self.app.run_task(_task, on_complete=_on_complete, on_error=_on_error)
