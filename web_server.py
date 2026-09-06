#!/usr/bin/env python3
"""TXT→EPUB Web UI 服务器

用法:
    cd txt-convert
    pip install fastapi "uvicorn[standard]"
    python web_server.py
"""

import sys
import os
import json
import queue
import signal
import asyncio
import threading
import webbrowser
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import StreamingResponse, FileResponse, Response
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
except ImportError:
    print("❌ 缺少依赖，请运行: pip install fastapi 'uvicorn[standard]'")
    sys.exit(1)

from encoding import EncodingDetector
from easypub import convert_for_easypub, batch_convert_for_easypub
from epub import EPUBGenerator
from chapter import ChapterAnalyzer
from config import config
from consistency import ContentMismatchError
from cover import search_cover_candidates

config.load()

# ── 日志捕获 ──────────────────────────────────────────────────
log_queue: queue.Queue = queue.Queue(maxsize=1000)


class _Tee:
    def __init__(self, orig):
        self._orig = orig

    def write(self, text):
        self._orig.write(text)
        for line in text.splitlines():
            if line.strip():
                try:
                    log_queue.put_nowait(line)
                except queue.Full:
                    try:
                        log_queue.get_nowait()
                    except Exception:
                        pass
                    try:
                        log_queue.put_nowait(line)
                    except Exception:
                        pass

    def flush(self):
        self._orig.flush()

    def __getattr__(self, name):
        return getattr(self._orig, name)


sys.stdout = _Tee(sys.__stdout__)

# ── FastAPI ───────────────────────────────────────────────────
app = FastAPI(title="TXT→EPUB")
executor = ThreadPoolExecutor(max_workers=3)

# ── 浏览器关闭自动退出 ────────────────────────────────────────
_sse_connections = 0
_shutdown_task: asyncio.Task = None


async def _shutdown_if_idle():
    await asyncio.sleep(4)
    if _sse_connections == 0:
        print("\n🔌 浏览器已关闭，服务自动退出")
        os.kill(os.getpid(), signal.SIGINT)
STATIC = Path(__file__).parent / "static"

app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/")
def index():
    return FileResponse(str(STATIC / "index.html"))


# ── SSE 日志流 ─────────────────────────────────────────────────
@app.get("/api/logs/stream")
async def log_stream():
    global _sse_connections, _shutdown_task
    _sse_connections += 1
    if _shutdown_task and not _shutdown_task.done():
        _shutdown_task.cancel()

    async def gen():
        global _sse_connections, _shutdown_task
        try:
            yield ": keepalive\n\n"
            while True:
                try:
                    line = log_queue.get_nowait()
                    yield f"data: {json.dumps(line)}\n\n"
                except queue.Empty:
                    await asyncio.sleep(0.08)
        except asyncio.CancelledError:
            pass
        finally:
            _sse_connections -= 1
            if _sse_connections == 0:
                loop = asyncio.get_event_loop()
                _shutdown_task = loop.create_task(_shutdown_if_idle())

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 文件对话框（macOS osascript）──────────────────────────────
class DialogReq(BaseModel):
    mode: str = "file"  # "file" | "dir"
    title: str = "选择"


def _pick_file(title: str) -> str:
    r = subprocess.run(
        ["osascript", "-e", f'choose file with prompt "{title}"'],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return ""
    alias = r.stdout.strip()
    r2 = subprocess.run(
        ["osascript", "-e", f'POSIX path of ("{alias}")'],
        capture_output=True, text=True,
    )
    return r2.stdout.strip().rstrip("/")


def _pick_dir(title: str) -> str:
    r = subprocess.run(
        ["osascript", "-e", f'choose folder with prompt "{title}"'],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return ""
    alias = r.stdout.strip()
    r2 = subprocess.run(
        ["osascript", "-e", f'POSIX path of ("{alias}")'],
        capture_output=True, text=True,
    )
    return r2.stdout.strip().rstrip("/")


@app.post("/api/dialog")
async def open_dialog(req: DialogReq):
    loop = asyncio.get_event_loop()
    if req.mode == "dir":
        path = await loop.run_in_executor(executor, lambda: _pick_dir(req.title))
    else:
        path = await loop.run_in_executor(executor, lambda: _pick_file(req.title))
    return {"path": path}


# ── 最近文件 ───────────────────────────────────────────────────
@app.get("/api/recent")
def get_recent():
    return {"files": config.get_recent_files(), "dirs": config.get_recent_dirs()}


# ── 提取元数据 ─────────────────────────────────────────────────
class PathReq(BaseModel):
    path: str


@app.post("/api/extract-meta")
async def extract_meta(req: PathReq):
    if not os.path.isfile(req.path):
        raise HTTPException(404, "文件不存在")
    loop = asyncio.get_event_loop()

    def _run():
        content, _ = EncodingDetector.read_file_with_auto_encoding(req.path)
        title = EPUBGenerator._extract_title(content) or ""
        author = EPUBGenerator._extract_author(content) or ""
        size = os.path.getsize(req.path)
        return {
            "title": title,
            "author": author,
            "size": size,
            "name": os.path.basename(req.path),
        }

    return await loop.run_in_executor(executor, _run)


# ── 单文件转换 ─────────────────────────────────────────────────
class ConvertReq(BaseModel):
    path: str
    title: str = ""
    author: str = ""


@app.post("/api/convert")
async def api_convert(req: ConvertReq):
    if not os.path.isfile(req.path):
        raise HTTPException(404, "文件不存在")
    config.add_recent_file(req.path)
    loop = asyncio.get_event_loop()

    def _run():
        return convert_for_easypub(req.path, None, req.title, req.author, show_catalog=True)

    try:
        out, analysis = await loop.run_in_executor(executor, _run)
    except ContentMismatchError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))
    if not out:
        raise HTTPException(500, "转换失败，请查看日志")
    return {"output_file": out, "analysis": analysis or {}}


# ── 批量转换 ───────────────────────────────────────────────────
class BatchReq(BaseModel):
    dir_path: str


@app.post("/api/batch")
async def api_batch(req: BatchReq):
    if not os.path.isdir(req.dir_path):
        raise HTTPException(404, "目录不存在")
    config.add_recent_dir(req.dir_path)
    loop = asyncio.get_event_loop()

    def _run():
        return batch_convert_for_easypub(req.dir_path, None, None, show_summary=True)

    try:
        results = await loop.run_in_executor(executor, _run)
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"results": results or []}


# ── 生成 EPUB ──────────────────────────────────────────────────
class EpubReq(BaseModel):
    path: str
    title: str = ""
    author: str = ""
    cover_image: str = ""
    cover_url: str = ""
    auto_search_cover: bool = False


@app.post("/api/epub")
async def api_epub(req: EpubReq):
    if not os.path.isfile(req.path):
        raise HTTPException(404, "文件不存在")
    config.add_recent_file(req.path)
    loop = asyncio.get_event_loop()

    def _run():
        cur = req.path
        if "_epub_ready" not in os.path.basename(cur):
            out, _ = convert_for_easypub(cur, None, req.title, req.author, show_catalog=False)
            if not out:
                raise RuntimeError("转换失败")
            cur = out
        epub_path = EPUBGenerator.txt_to_epub(
            cur, None, req.title, req.author,
            req.cover_image or None, req.auto_search_cover, req.cover_url or None,
        )
        if not epub_path:
            raise RuntimeError("EPUB 生成失败")
        return epub_path

    try:
        epub_path = await loop.run_in_executor(executor, _run)
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"epub_path": epub_path}


# ── 章节分析 ───────────────────────────────────────────────────
@app.post("/api/catalog/analyze")
async def api_catalog(req: PathReq):
    if not os.path.isfile(req.path):
        raise HTTPException(404, "文件不存在")
    loop = asyncio.get_event_loop()

    def _run():
        content, _ = EncodingDetector.read_file_with_auto_encoding(req.path)
        return ChapterAnalyzer.analyze_chapter_structure(content)

    return await loop.run_in_executor(executor, _run)


# ── Finder 集成 ────────────────────────────────────────────────
@app.post("/api/open-in-finder")
async def open_finder(req: PathReq):
    p = req.path
    if os.path.isfile(p):
        subprocess.Popen(["open", "-R", p])
    elif os.path.isdir(p):
        subprocess.Popen(["open", p])
    return {"ok": True}


@app.post("/api/open-file")
async def open_file_req(req: PathReq):
    if not os.path.exists(req.path):
        raise HTTPException(404, "路径不存在")
    subprocess.Popen(["open", req.path])
    return {"ok": True}


# ── 封面搜索 ───────────────────────────────────────────────────
class SearchCoverReq(BaseModel):
    title: str
    author: str = ""


@app.post("/api/epub/search-covers")
async def search_covers(req: SearchCoverReq):
    if not req.title.strip():
        raise HTTPException(400, "书名不能为空")
    loop = asyncio.get_event_loop()
    candidates = await loop.run_in_executor(
        executor, lambda: search_cover_candidates(req.title, req.author)
    )
    return {
        "candidates": [
            {
                "image_url":   c.image_url,
                "referer":     c.referer,
                "source_name": c.source_name,
                "book_title":  c.book_title,
                "author":      c.author,
                "confidence":  c.confidence,
            }
            for c in candidates[:12]
        ]
    }


@app.get("/api/cover-proxy")
async def cover_proxy(url: str, referer: str = ""):
    from cover import _http_get
    loop = asyncio.get_event_loop()
    raw, _ = await loop.run_in_executor(executor, lambda: _http_get(url, referer=referer, timeout=15))
    if not raw:
        raise HTTPException(404, "图片获取失败")
    ct = "image/png" if raw[:4] == b'\x89PNG' else "image/jpeg"
    return Response(content=raw, media_type=ct,
                    headers={"Cache-Control": "public, max-age=3600"})


# ── 入口 ───────────────────────────────────────────────────────
def main():
    url = "http://127.0.0.1:8765"
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"🌐 TXT→EPUB Web UI 已启动: {url}")
    print("按 Ctrl+C 退出")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")


if __name__ == "__main__":
    main()
