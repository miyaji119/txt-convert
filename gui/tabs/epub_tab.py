"""EPUB 生成 Tab"""

import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from gui.tabs.base_tab import BaseTab
from gui.constants import EPUB_SUPPORT
from config import config
from encoding import EncodingDetector
from easypub import convert_for_easypub
from epub import EPUBGenerator
from chapter import ChapterAnalyzer
from cover import search_cover_candidates, download_candidate
from cover_picker_dialog import pick_cover


class EpubTab(BaseTab):
    """EPUB 生成标签页：一键转换并生成 EPUB，含封面候选选择"""

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

        self.cover_var = tk.IntVar(value=config.get('cover_choice', 4))
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
            btn_frame, text="🚀 一键转换并生成 EPUB", style='Accent.TButton',
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
            # 记录到最近文件列表
            config.add_recent_file(path)
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
            # 自动搜索：先弹出候选选择对话框，用户选中后再下载
            self._start_auto_cover_search(path, title, author)
            return

        # 其他封面选项：直接启动生成流程
        self._run_generate_pipeline(path, title, author, cover_image,
                                    auto_search, cover_url, choice)

    # ------------------------------------------------------------------
    # 封面候选选择流程（choice == 4）
    # ------------------------------------------------------------------
    def _start_auto_cover_search(self, path: str, title: str, author: str):
        """自动搜索封面：后台搜索候选 → 弹出对话框 → 下载选中候选 → 启动生成流程"""
        if not title:
            # 无书名无法搜索，回退到原 auto_search 流程（由 epub.py 内部处理）
            messagebox.showwarning(
                "提示",
                "自动搜索封面需要先填写书名。\n"
                "请填写书名，或选择其他封面选项。"
            )
            return

        self.generate_btn.config(state='disabled')
        self.reload_btn.config(state='disabled')
        self.app.set_status("正在搜索封面候选...")
        print("=" * 60)
        print(f"🔍 自动搜索封面候选: 《{title}》" +
              (f" / {author}" if author else ""))
        print("=" * 60)

        def _search_task():
            try:
                candidates = search_cover_candidates(title, author)
                # 用默认参数冻结 candidates，避免闭包陷阱
                self.app.root.after(
                    0, lambda cs=candidates:
                    self._on_candidates_ready(cs, path, title, author))
            except Exception as e:
                self.app.root.after(
                    0, lambda err=e:
                    self._on_candidates_search_failed(err, path, title, author))

        threading.Thread(target=_search_task, daemon=True).start()

    def _on_candidates_ready(self, candidates, path: str,
                              title: str, author: str):
        """候选搜索完成：弹出对话框让用户选择"""
        self.app.set_status("就绪")
        self.generate_btn.config(state='normal')
        self.reload_btn.config(state='normal')

        if not candidates:
            print("⚠️ 未找到任何封面候选")
            if messagebox.askyesno(
                "未找到封面",
                f"未能为《{title}》找到封面候选。\n是否继续生成（无封面）？"
            ):
                self._run_generate_pipeline(path, title, author,
                                            None, False, None, 4)
            return

        print(f"✓ 共找到 {len(candidates)} 个候选，请选择")
        chosen = pick_cover(self.app.root, candidates, title)
        if chosen is None:
            # 用户取消选择
            print("ℹ️ 用户取消封面选择")
            return

        print(f"✓ 已选择: [{chosen.source_name}] {chosen.book_title!r} "
              f"(置信度 {chosen.confidence:.0%})")

        # 下载选中的候选到本地
        self.generate_btn.config(state='disabled')
        self.reload_btn.config(state='disabled')
        self.app.set_status(f"正在下载封面（{chosen.source_name}）...")
        print(f"   ⏳ 正在下载封面: {chosen.image_url[:80]}")

        def _download_task():
            try:
                output_dir = os.path.dirname(path) or '.'
                local_path = download_candidate(
                    chosen, output_dir, filename='cover_selected.jpg')
                self.app.root.after(
                    0, lambda lp=local_path:
                    self._on_cover_downloaded(lp, path, title, author))
            except Exception as e:
                self.app.root.after(
                    0, lambda err=e:
                    self._on_cover_download_failed(err, path, title, author))

        threading.Thread(target=_download_task, daemon=True).start()

    def _on_cover_downloaded(self, local_path, path: str,
                              title: str, author: str):
        """封面下载完成：用本地封面路径启动生成流程"""
        if local_path:
            print(f"✅ 封面下载成功: {local_path}")
            self.app.set_status("就绪")
            # 用本地封面路径，auto_search=False
            self._run_generate_pipeline(path, title, author,
                                        local_path, False, None, 4)
        else:
            print("⚠️ 封面下载失败（候选未通过校验）")
            if messagebox.askyesno(
                "封面下载失败",
                "封面下载失败（候选可能未通过尺寸校验）。\n"
                "是否继续生成（无封面）？"
            ):
                self._run_generate_pipeline(path, title, author,
                                            None, False, None, 4)
            else:
                self.generate_btn.config(state='normal')
                self.reload_btn.config(state='normal')
                self.app.set_status("就绪")

    def _on_cover_download_failed(self, err, path: str,
                                   title: str, author: str):
        """封面下载异常"""
        print(f"❌ 封面下载异常: {err}")
        if messagebox.askyesno(
            "封面下载失败",
            f"封面下载异常: {err}\n是否继续生成（无封面）？"
        ):
            self._run_generate_pipeline(path, title, author,
                                        None, False, None, 4)
        else:
            self.generate_btn.config(state='normal')
            self.reload_btn.config(state='normal')
            self.app.set_status("就绪")

    def _on_candidates_search_failed(self, err, path: str,
                                      title: str, author: str):
        """候选搜索异常"""
        print(f"❌ 封面搜索异常: {err}")
        if messagebox.askyesno(
            "封面搜索失败",
            f"封面搜索异常: {err}\n是否继续生成（无封面）？"
        ):
            self._run_generate_pipeline(path, title, author,
                                        None, False, None, 4)
        else:
            self.generate_btn.config(state='normal')
            self.reload_btn.config(state='normal')
            self.app.set_status("就绪")

    # ------------------------------------------------------------------
    # 生成 EPUB 主流程
    # ------------------------------------------------------------------
    def _run_generate_pipeline(self, path: str, title: str, author: str,
                                cover_image, auto_search, cover_url, choice):
        """执行生成 EPUB 的完整流程"""
        # 自动判断是否需要先转换（不再需要用户勾选）
        need_convert = not self._is_epub_ready(path)
        _IDLE_GEN = "🚀 一键转换并生成 EPUB"
        _work_text = "⏳ 转换+生成中…" if need_convert else "⏳ 生成 EPUB…"

        self.app.set_btn_working(self.generate_btn, True, _IDLE_GEN, _work_text)
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
                self.app.set_output_file(epub_path)
                self.app.flash_btn_done(self.generate_btn, _IDLE_GEN, success=True)
                self.app.set_nav_badge(2, '✓', '#86efac')
                messagebox.showinfo(
                    "成功",
                    f"EPUB 生成完成！\n\n"
                    f"📕 EPUB 文件:\n{epub_path}\n\n"
                    f"💡 可在底部点击「打开文件」按钮直接查看。"
                )
                if need_convert:
                    self.path_var.set(final_txt_path)
                    self._load_catalog(final_txt_path)
            else:
                self.app.flash_btn_done(self.generate_btn, _IDLE_GEN, success=False)
                self.app.set_nav_badge(2, '✗', '#fca5a5')
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
            self.app.flash_btn_done(self.generate_btn, _IDLE_GEN, success=False)
            self.app.set_nav_badge(2, '✗', '#fca5a5')
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
