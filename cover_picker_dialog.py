"""封面候选选择对话框

从 search_cover_candidates() 返回的候选列表中让用户选择最合适的封面。

使用方式：
    from cover import search_cover_candidates
    from cover_picker_dialog import pick_cover

    candidates = search_cover_candidates("书名", "作者")
    chosen = pick_cover(self, candidates)  # 返回 CoverCandidate 或 None
    if chosen:
        # 下载 chosen 到本地
        ...

设计要点：
- 异步加载缩略图：后台线程下载，queue 传回主线程渲染，避免阻塞 UI
- 模态对话框：grab_set() 阻塞主窗口交互
- 网格布局：每行 4 个候选，缩略图 120×170（约书封面比例）
- 无 PIL 时降级为纯文字按钮（来源 + 书名 + 置信度）
"""

import os
import io
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, List

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from cover import CoverCandidate, _http_get, _is_valid_image


# 缩略图尺寸
THUMB_W, THUMB_H = 120, 170
COLS = 4  # 每行候选数


def _load_thumbnail(candidate: CoverCandidate) -> Optional[bytes]:
    """下载候选图片的原始字节（用于后台线程）"""
    raw, _ = _http_get(candidate.image_url, referer=candidate.referer, timeout=15)
    if not raw or not _is_valid_image(io.BytesIO(raw).getvalue() if raw else b''):
        # _is_valid_image 接受文件路径，这里改用文件头判断
        if not raw:
            return None
        header = raw[:20]
        if not (header.startswith(b'\xff\xd8\xff') or
                header.startswith(b'\x89PNG') or
                b'JFIF' in header or b'Exif' in header):
            return None
    return raw


def _bytes_to_thumbnail(raw: bytes):
    """将原始字节转为 Tkinter 可用的缩略图 PhotoImage"""
    if not HAS_PIL or not raw:
        return None
    try:
        img = Image.open(io.BytesIO(raw))
        img.thumbnail((THUMB_W, THUMB_H), Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


class CoverPickerDialog(tk.Toplevel):
    """封面候选选择对话框（模态）

    用法：
        dialog = CoverPickerDialog(parent, candidates)
        parent.wait_window(dialog)  # 阻塞直到对话框关闭
        chosen = dialog.result  # CoverCandidate 或 None
    """

    def __init__(self, parent, candidates: List[CoverCandidate],
                 book_title: str = ''):
        super().__init__(parent)
        self.title("选择封面")
        self.result: Optional[CoverCandidate] = None
        self._candidates = candidates
        self._photo_refs = []  # 防止 PhotoImage 被 GC
        self._thumb_queue: queue.Queue = queue.Queue()
        self._thumb_threads = []
        self._closed = False

        # 窗口设置
        self.transient(parent)
        self.grab_set()
        self.resizable(True, True)

        # 计算窗口尺寸（根据候选数）
        n = max(len(candidates), 1)
        rows = (n + COLS - 1) // COLS
        win_w = max(COLS * (THUMB_W + 16) + 40, 400)
        win_h = min(rows * (THUMB_H + 80) + 120, 700)
        self.geometry(f"{win_w}x{win_h}")
        self.minsize(400, 300)

        # 居中显示
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - win_w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - win_h) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        self._build_ui(book_title)

        # 启动异步缩略图加载
        self._start_thumbnail_loading()

        # 关闭窗口的处理
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Escape>", lambda e: self._on_cancel())

    def _build_ui(self, book_title: str):
        # 顶部标题
        header = ttk.Frame(self, padding=(12, 8))
        header.pack(fill='x')
        title_text = f"找到 {len(self._candidates)} 个封面候选"
        if book_title:
            title_text = f"《{book_title}》{title_text}"
        ttk.Label(header, text=title_text,
                  font=('-size', 12, '-weight', 'bold')).pack(side='left')
        ttk.Label(header, text="点击图片选择，或选「不用封面」",
                  foreground='#666').pack(side='left', padx=(12, 0))

        # 候选网格区域（带滚动）
        container = ttk.Frame(self, padding=8)
        container.pack(fill='both', expand=True)

        # Canvas + Scrollbar 实现滚动
        self._canvas = tk.Canvas(container, highlightthickness=0,
                                  bg='#f5f5f5')
        scrollbar = ttk.Scrollbar(container, orient='vertical',
                                   command=self._canvas.yview)
        self._grid_frame = ttk.Frame(self._canvas)
        self._grid_frame.bind(
            '<Configure>',
            lambda e: self._canvas.configure(
                scrollregion=self._canvas.bbox('all'))
        )
        self._canvas.create_window((0, 0), window=self._grid_frame, anchor='nw')
        self._canvas.configure(yscrollcommand=scrollbar.set)
        self._canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # 鼠标滚轮支持
        self._canvas.bind('<Enter>',
                          lambda e: self._bind_mousewheel())
        self._canvas.bind('<Leave>',
                          lambda e: self._unbind_mousewheel())

        # 占位候选卡片（缩略图加载后填充）
        self._cards = []
        for i, cand in enumerate(self._candidates):
            row, col = divmod(i, COLS)
            card = self._create_card(self._grid_frame, cand, i)
            card.grid(row=row, column=col, padx=6, pady=6, sticky='n')
            self._cards.append(card)

        # 底部按钮
        footer = ttk.Frame(self, padding=(12, 8))
        footer.pack(fill='x')
        ttk.Button(footer, text="不用封面",
                   command=self._on_cancel).pack(side='right')
        ttk.Label(footer, text="提示：置信度越高越匹配",
                  foreground='#999').pack(side='left')

    def _create_card(self, parent, candidate: CoverCandidate,
                     idx: int) -> ttk.Frame:
        """创建单个候选卡片"""
        card = ttk.Frame(parent, relief='solid', borderwidth=1)

        # 图片占位区
        img_frame = tk.Frame(card, width=THUMB_W, height=THUMB_H,
                              bg='#e0e0e0', highlightthickness=0)
        img_frame.pack(padx=8, pady=(8, 4))
        img_frame.pack_propagate(False)  # 固定尺寸

        # 加载中提示
        loading = ttk.Label(img_frame, text="加载中...",
                            background='#e0e0e0', foreground='#666')
        loading.place(relx=0.5, rely=0.5, anchor='center')

        # 置信度标签（右上角）
        conf_pct = int(candidate.confidence * 100)
        conf_color = '#2e7d32' if conf_pct >= 80 else (
            '#f57f17' if conf_pct >= 50 else '#999')
        conf_label = tk.Label(img_frame, text=f"{conf_pct}%",
                              background=conf_color, foreground='white',
                              font=('-size', 9, '-weight', 'bold'),
                              padx=4, pady=1)
        conf_label.place(relx=1.0, rely=0.0, anchor='ne', x=-2, y=2)

        # 信息区
        info_text = candidate.book_title or '(未知书名)'
        if len(info_text) > 18:
            info_text = info_text[:17] + '…'
        ttk.Label(card, text=info_text,
                  font=('-size', 9)).pack(padx=4, pady=(0, 2))

        meta_parts = [candidate.source_name]
        if candidate.author:
            author_short = candidate.author[:8]
            meta_parts.append(author_short)
        ttk.Label(card, text=' / '.join(meta_parts),
                  foreground='#888', font=('-size', 8)).pack(padx=4, pady=(0, 4))

        # 保存引用便于后续更新
        card._img_frame = img_frame
        card._loading_label = loading
        card._candidate = candidate
        card._idx = idx

        # 点击事件
        def on_click(event):
            self._on_select(idx)
        for widget in [card, img_frame, loading]:
            widget.bind('<Button-1>', on_click)
        # 鼠标悬停效果
        for widget in [card, img_frame]:
            widget.bind('<Enter>',
                        lambda e, c=card: c.config(relief='raised'))
            widget.bind('<Leave>',
                        lambda e, c=card: c.config(relief='solid'))

        return card

    def _start_thumbnail_loading(self):
        """启动后台线程异步加载缩略图"""
        for i, cand in enumerate(self._candidates):
            t = threading.Thread(
                target=self._load_thumb_thread,
                args=(i, cand),
                daemon=True
            )
            t.start()
            self._thumb_threads.append(t)

        # 主线程轮询 queue 更新 UI
        self._poll_thumb_queue()

    def _load_thumb_thread(self, idx: int, cand: CoverCandidate):
        """后台线程：下载缩略图原始字节"""
        try:
            raw = _load_thumbnail(cand)
            self._thumb_queue.put((idx, raw))
        except Exception:
            self._thumb_queue.put((idx, None))

    def _poll_thumb_queue(self):
        """主线程：检查 queue 并更新 UI"""
        if self._closed:
            return
        try:
            while True:
                idx, raw = self._thumb_queue.get_nowait()
                if idx < len(self._cards):
                    self._update_card_image(idx, raw)
        except queue.Empty:
            pass
        # 每 100ms 检查一次
        self.after(100, self._poll_thumb_queue)

    def _update_card_image(self, idx: int, raw: Optional[bytes]):
        """更新指定卡片的缩略图"""
        if idx >= len(self._cards) or self._closed:
            return
        card = self._cards[idx]

        # 移除"加载中"提示
        try:
            card._loading_label.destroy()
        except Exception:
            pass

        if not raw:
            # 加载失败
            ttk.Label(card._img_frame, text="加载失败",
                      background='#e0e0e0', foreground='#c62828').place(
                relx=0.5, rely=0.5, anchor='center')
            return

        if HAS_PIL:
            photo = _bytes_to_thumbnail(raw)
            if photo:
                self._photo_refs.append(photo)
                lbl = ttk.Label(card._img_frame, image=photo)
                lbl.place(relx=0.5, rely=0.5, anchor='center')
                # 点击图片也能选择
                lbl.bind('<Button-1>',
                         lambda e, i=idx: self._on_select(i))
            else:
                ttk.Label(card._img_frame, text="解析失败",
                          background='#e0e0e0', foreground='#c62828').place(
                    relx=0.5, rely=0.5, anchor='center')
        else:
            # 无 PIL：显示文字提示
            ttk.Label(card._img_frame, text="点击选择\n(无PIL预览)",
                      background='#e0e0e0', foreground='#666',
                      justify='center').place(
                relx=0.5, rely=0.5, anchor='center')

    def _on_select(self, idx: int):
        """用户点击选择某个候选"""
        if idx < 0 or idx >= len(self._candidates):
            return
        self.result = self._candidates[idx]
        self._closed = True
        self.destroy()

    def _on_cancel(self):
        """用户取消选择"""
        self.result = None
        self._closed = True
        self.destroy()

    def _bind_mousewheel(self):
        """绑定鼠标滚轮（macOS/Linux）"""
        self._canvas.bind_all('<MouseWheel>',
                              lambda e: self._canvas.yview_scroll(
                                  int(-1 * (e.delta / 120)), 'units'))
        # Linux 用 Button-4/5
        self._canvas.bind_all('<Button-4>',
                              lambda e: self._canvas.yview_scroll(-1, 'units'))
        self._canvas.bind_all('<Button-5>',
                              lambda e: self._canvas.yview_scroll(1, 'units'))

    def _unbind_mousewheel(self):
        """解绑鼠标滚轮"""
        self._canvas.unbind_all('<MouseWheel>')
        self._canvas.unbind_all('<Button-4>')
        self._canvas.unbind_all('<Button-5>')


def pick_cover(parent, candidates: List[CoverCandidate],
               book_title: str = '') -> Optional[CoverCandidate]:
    """便捷函数：弹出候选选择对话框，返回用户选中的候选

    Args:
        parent: 父窗口
        candidates: 候选列表（按置信度降序）
        book_title: 书名（用于标题显示）

    Returns:
        用户选中的 CoverCandidate，或 None（取消/不用封面）
    """
    if not candidates:
        return None
    dialog = CoverPickerDialog(parent, candidates, book_title)
    parent.wait_window(dialog)
    return dialog.result
