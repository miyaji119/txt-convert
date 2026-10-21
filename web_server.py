#!/usr/bin/env python3
"""TXT→EPUB Web UI 服务器

用法:
    cd txt-convert
    pip install fastapi "uvicorn[standard]"
    python web_server.py
"""

import sys
import os
import re
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
from easypub import convert_for_easypub, batch_convert_for_easypub, normalize_numeric_chapters
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
                loop = asyncio.get_running_loop()
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
        ["osascript", "-e", f'POSIX path of (choose file with prompt "{title}")'],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return ""
    return r.stdout.strip().rstrip("/")


def _pick_dir(title: str) -> str:
    r = subprocess.run(
        ["osascript", "-e", f'POSIX path of (choose folder with prompt "{title}")'],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return ""
    return r.stdout.strip().rstrip("/")


@app.post("/api/dialog")
async def open_dialog(req: DialogReq):
    loop = asyncio.get_running_loop()
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


_FILENAME_WATERMARK_RE = re.compile(
    r'[_\s\-]+(?:笔趣阁|起点|晋江|纵横|17k|腾讯|阅文|番茄|米读|七猫|掌阅|多看'
    r'|po18|jjwxc|笔力阅读|阅笔小说|润文网|书趣网|新笔趣阁|顶点小说|飞卢小说'
    r'|爱好中文|biliyd|yoabc)(?:小说|阅读|文学|网|app)?[_\s\-]*$',
    re.I,
)


def _clean_filename_title(stem: str) -> str:
    """清理文件名中的站点水印后缀，如"书名_润文网" → "书名"。"""
    cleaned = _FILENAME_WATERMARK_RE.sub('', stem).strip()
    # "书名 - 作者名" 格式：取 - 前的部分作为书名
    if ' - ' in cleaned:
        cleaned = cleaned.split(' - ', 1)[0].strip()
    return cleaned or stem


@app.post("/api/extract-meta")
async def extract_meta(req: PathReq):
    if not os.path.isfile(req.path):
        raise HTTPException(404, "文件不存在")
    loop = asyncio.get_running_loop()

    def _run():
        content, _ = EncodingDetector.read_file_with_auto_encoding(req.path)
        title = EPUBGenerator._extract_title(content) or ""
        author = EPUBGenerator._extract_author(content) or ""
        if not title:
            stem = os.path.splitext(os.path.basename(req.path))[0]
            title = _clean_filename_title(stem)
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
    filter_ads: bool = True


@app.post("/api/convert")
async def api_convert(req: ConvertReq):
    if not os.path.isfile(req.path):
        raise HTTPException(404, "文件不存在")
    config.add_recent_file(req.path)
    loop = asyncio.get_running_loop()

    def _run():
        return convert_for_easypub(req.path, None, req.title, req.author, show_catalog=True,
                                   filter_ads=req.filter_ads, ad_rules=_get_ad_rules())

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
    filter_ads: bool = True


@app.post("/api/batch")
async def api_batch(req: BatchReq):
    if not os.path.isdir(req.dir_path):
        raise HTTPException(404, "目录不存在")
    config.add_recent_dir(req.dir_path)
    loop = asyncio.get_running_loop()

    def _run():
        return batch_convert_for_easypub(req.dir_path, None, None, show_summary=True,
                                         filter_ads=req.filter_ads, ad_rules=_get_ad_rules())

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
    description: str = ""
    publisher: str = ""
    cover_image: str = ""
    cover_url: str = ""
    auto_search_cover: bool = False
    filter_ads: bool = True
    margin: str = "0 4%"
    line_height: float = 1.8
    text_indent: str = "2em"
    custom_css: str = ""
    # 对话 span 样式，如 {"dlg-cn": {"color": "#1a1a8c"}, "dlg-sq": {"color": "#5c1a1a"}}
    dialog_styles: dict = {}
    isbn: str = ""
    pubdate: str = ""           # ISO 日期，如 "2023-01-15"
    language: str = "zh"
    tags: str = ""              # 逗号/顿号分隔，如 "玄幻,仙侠"
    drop_cap: bool = False      # 首字下沉
    # 手动卷分配：{章节标题: 卷名}，如 {"第一章 序": "第一卷 初相遇"}
    volume_map: dict = {}
    # 样式预设（空列表 = 使用服务端默认）
    style_presets: list = []
    # 头图配置列表：[{"path": "/path/img.jpg", "edge": "fade"}]
    header_images: list = []
    # 字体路径：{"body": "/path/body.ttf", "title": ..., "dlg": ..., "toc": ...}
    fonts: dict = {}
    # 插图页：[{"path": "/path/img.jpg", "after_chapter": 0, "caption": ""}]
    illustrations: list = []
    # 自动生成封面风格（空字符串 = 不生成；"minimal_light" 等见 cover_gen.py）
    generate_cover_style: str = ""


@app.post("/api/epub")
async def api_epub(req: EpubReq):
    if not os.path.isfile(req.path):
        raise HTTPException(404, "文件不存在")
    config.add_recent_file(req.path)
    loop = asyncio.get_running_loop()

    def _run():
        cur = req.path
        if "_epub_ready" not in os.path.basename(cur):
            out, _ = convert_for_easypub(cur, None, req.title, req.author, show_catalog=False,
                                         filter_ads=req.filter_ads, ad_rules=_get_ad_rules())
            if not out:
                raise RuntimeError("转换失败")
            cur = out
        epub_path = EPUBGenerator.txt_to_epub(
            cur, None, req.title, req.author,
            req.cover_image or None, req.auto_search_cover, req.cover_url or None,
            req.description, req.publisher,
            req.margin, req.line_height, req.text_indent, req.custom_css,
            req.dialog_styles or None,
            req.isbn, req.pubdate, req.language or "zh",
            req.tags or None, req.drop_cap,
            req.volume_map or None,
            req.style_presets or None,
            req.header_images or None,
            req.fonts or None,
            req.illustrations or None,
            generate_cover_style=req.generate_cover_style or "",
        )
        return epub_path

    try:
        epub_path = await loop.run_in_executor(executor, _run)
    except Exception as e:
        raise HTTPException(500, str(e))
    _save_profile(req.dict())
    return {"epub_path": epub_path}


# ── 配置 Profile（跨书籍样式偏好持久化）────────────────────────
PROFILE_FILE = os.path.join(os.path.expanduser('~'), '.txt2epub', 'profile.json')
_PROFILE_KEYS = ("margin", "line_height", "text_indent", "custom_css",
                 "dialog_styles", "publisher", "language")


def _save_profile(data: dict):
    os.makedirs(os.path.dirname(PROFILE_FILE), exist_ok=True)
    profile = {k: data[k] for k in _PROFILE_KEYS if k in data}
    with open(PROFILE_FILE, 'w', encoding='utf-8') as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def _load_profile() -> dict:
    if not os.path.isfile(PROFILE_FILE):
        return {}
    try:
        with open(PROFILE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


@app.get("/api/profile")
async def get_profile():
    return _load_profile()


# ── 样式预设管理 ──────────────────────────────────────────────
from epub import EPUBGenerator as _EPUBGenerator

STYLE_PRESETS_FILE = os.path.join(os.path.expanduser('~'), '.txt2epub', 'style_presets.json')


def _load_style_presets() -> list:
    if not os.path.isfile(STYLE_PRESETS_FILE):
        return []
    try:
        with open(STYLE_PRESETS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


@app.get("/api/style/presets")
async def get_style_presets():
    user = _load_style_presets()
    return {
        "presets": user if user else _EPUBGenerator.DEFAULT_STYLE_PRESETS,
        "defaults": _EPUBGenerator.DEFAULT_STYLE_PRESETS,
        "file_path": STYLE_PRESETS_FILE,
    }


class StylePresetsReq(BaseModel):
    presets: list


@app.post("/api/style/presets")
async def save_style_presets(req: StylePresetsReq):
    os.makedirs(os.path.dirname(STYLE_PRESETS_FILE), exist_ok=True)
    with open(STYLE_PRESETS_FILE, 'w', encoding='utf-8') as f:
        json.dump(req.presets, f, ensure_ascii=False, indent=2)
    return {"ok": True, "file_path": STYLE_PRESETS_FILE}
@app.post("/api/catalog/analyze")
async def api_catalog(req: PathReq):
    if not os.path.isfile(req.path):
        raise HTTPException(404, "文件不存在")
    loop = asyncio.get_running_loop()

    def _run():
        content, _ = EncodingDetector.read_file_with_auto_encoding(req.path)
        return ChapterAnalyzer.analyze_chapter_structure(content)

    return await loop.run_in_executor(executor, _run)


# ── 章节保存 ───────────────────────────────────────────────
class SaveCatalogReq(BaseModel):
    path: str
    chapters: List[dict]
    output_path: str = ""


@app.post("/api/catalog/save")
async def api_catalog_save(req: SaveCatalogReq):
    if not os.path.isfile(req.path):
        raise HTTPException(404, "文件不存在")
    if not req.chapters:
        raise HTTPException(400, "章节列表为空")
    loop = asyncio.get_running_loop()

    def _run():
        content, _ = EncodingDetector.read_file_with_auto_encoding(req.path)
        lines = content.split('\n')
        chapter_contents = []
        for ch in req.chapters:
            s = ch.get('content_start', ch.get('start_line', 0)) - 1
            e = ch.get('content_end', ch.get('end_line', 0)) - 1
            s = max(0, min(s, len(lines) - 1))
            e = max(s, min(e, len(lines) - 1))
            section = lines[s:e + 1]
            if section:
                import re as _re
                new_title = ch['title']
                stripped = section[0].lstrip()
                if stripped and stripped[0] in '=*#':
                    m = _re.match(r'^([=*#◇◆•·\s]+)', section[0])
                    prefix = m.group(1) if m else ''
                    section[0] = f"{prefix}{new_title}"
                else:
                    section[0] = new_title
            chapter_contents.append('\n'.join(section))

        first_start = max(0, req.chapters[0].get(
            'content_start', req.chapters[0].get('start_line', 0)) - 1)
        pre = '\n'.join(lines[:first_start])
        parts = ([pre] if pre.strip() else []) + chapter_contents
        output_text = '\n\n'.join(parts) + '\n'

        out = req.output_path or (os.path.splitext(req.path)[0] + '_edited.txt')
        with open(out, 'w', encoding='utf-8') as f:
            f.write(output_text)
        return out

    try:
        out = await loop.run_in_executor(executor, _run)
    except Exception as e:
        raise HTTPException(500, str(e))
    config.add_recent_file(out)
    return {"output_path": out}


# ── 章节标题规范化（数字 → 第X章）────────────────────────────────
class NormalizeChaptersReq(BaseModel):
    path: str
    output_path: str = ""   # 留空则写到 {stem}_normalized.txt
    dry_run: bool = False   # True 时只返回变更列表，不写文件


@app.post("/api/chapters/normalize")
async def api_chapters_normalize(req: NormalizeChaptersReq):
    if not os.path.isfile(req.path):
        raise HTTPException(404, "文件不存在")
    loop = asyncio.get_running_loop()

    def _run():
        content, _ = EncodingDetector.read_file_with_auto_encoding(req.path)
        new_content, changes = normalize_numeric_chapters(content)
        if req.dry_run or not changes:
            return {"output_path": "", "changes": changes}
        out = req.output_path or (os.path.splitext(req.path)[0] + '_normalized.txt')
        with open(out, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return {"output_path": out, "changes": changes}

    try:
        result = await loop.run_in_executor(executor, _run)
    except Exception as e:
        raise HTTPException(500, str(e))
    if result["output_path"]:
        config.add_recent_file(result["output_path"])
    return result


# ── 全书查找/替换 ──────────────────────────────────────────────
@app.get("/api/find")
async def api_find(path: str, q: str, case_sensitive: bool = False):
    if not os.path.isfile(path):
        raise HTTPException(404, "文件不存在")
    if not q:
        raise HTTPException(400, "查找内容不能为空")
    loop = asyncio.get_running_loop()

    def _run():
        content, _ = EncodingDetector.read_file_with_auto_encoding(path)
        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = re.compile(re.escape(q), flags)
        results = []
        for i, line in enumerate(content.split('\n')):
            if pattern.search(line):
                results.append({'line_num': i + 1, 'text': line.strip()})
        return {'count': len(results), 'results': results}

    return await loop.run_in_executor(executor, _run)


class ReplaceReq(BaseModel):
    path: str
    find: str
    replace: str = ""
    case_sensitive: bool = False
    output_path: str = ""   # 留空则写到 {stem}_replaced.txt


@app.post("/api/replace")
async def api_replace(req: ReplaceReq):
    if not os.path.isfile(req.path):
        raise HTTPException(404, "文件不存在")
    if not req.find:
        raise HTTPException(400, "查找内容不能为空")
    loop = asyncio.get_running_loop()

    def _run():
        content, _ = EncodingDetector.read_file_with_auto_encoding(req.path)
        flags = 0 if req.case_sensitive else re.IGNORECASE
        pattern = re.compile(re.escape(req.find), flags)
        count = len(pattern.findall(content))
        if count == 0:
            return {'count': 0, 'output_path': ''}
        new_content = pattern.sub(req.replace, content)
        out = req.output_path or (os.path.splitext(req.path)[0] + '_replaced.txt')
        with open(out, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return {'count': count, 'output_path': out}

    try:
        result = await loop.run_in_executor(executor, _run)
    except Exception as e:
        raise HTTPException(500, str(e))
    if result['output_path']:
        config.add_recent_file(result['output_path'])
    return result


# ── 重新分章 ───────────────────────────────────────────────────
class ResplitReq(BaseModel):
    path: str
    config_name: str = "default"       # 预设配置名
    extra_patterns: List[str] = []     # 额外自定义正则（优先于配置中的模式）
    output_path: str = ""
    dry_run: bool = True               # 默认只预览，不写文件


@app.post("/api/resplit")
async def api_resplit(req: ResplitReq):
    if not os.path.isfile(req.path):
        raise HTTPException(404, "文件不存在")
    loop = asyncio.get_running_loop()

    def _run():
        content, _ = EncodingDetector.read_file_with_auto_encoding(req.path)
        structure = ChapterAnalyzer.analyze_chapter_structure(
            content,
            config_name=req.config_name,
            extra_patterns=req.extra_patterns or None,
        )
        if req.dry_run or not structure['chapters']:
            return {"output_path": "", "structure": structure}
        out = req.output_path or (os.path.splitext(req.path)[0] + '_resplit.txt')
        with open(out, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"output_path": out, "structure": structure}

    try:
        result = await loop.run_in_executor(executor, _run)
    except Exception as e:
        raise HTTPException(500, str(e))
    if result["output_path"]:
        config.add_recent_file(result["output_path"])
    return result


# ── 广告过滤规则 ───────────────────────────────────────────────
from adfilter import AdFilter as _AdFilter

AD_RULES_FILE = os.path.join(os.path.expanduser('~'), '.txt2epub', 'adfilter_rules.json')


def _load_ad_rules_file() -> dict:
    """从独立规则文件读取，不存在时返回 None（调用方按默认处理）。"""
    if not os.path.isfile(AD_RULES_FILE):
        return {}
    try:
        with open(AD_RULES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _get_ad_rules() -> dict:
    """返回当前广告过滤规则，用于传给 convert_for_easypub。"""
    data = _load_ad_rules_file()
    return {
        'hard_kw':  data.get('hard_kw'),   # None → AdFilter 使用内置默认
        'soft_kw':  data.get('soft_kw'),
        'threshold': data.get('threshold', 0.68),
    }


@app.get("/api/adfilter/rules")
async def get_adfilter_rules():
    data = _load_ad_rules_file()
    return {
        "hard_kw":           data.get('hard_kw', _AdFilter._HARD_KW),
        "soft_kw":           data.get('soft_kw', _AdFilter._SOFT_KW),
        "threshold":         data.get('threshold', 0.68),
        "default_hard_kw":   _AdFilter._HARD_KW,
        "default_soft_kw":   _AdFilter._SOFT_KW,
        "default_threshold": 0.68,
        "file_path":         AD_RULES_FILE,
    }


class AdFilterRulesReq(BaseModel):
    hard_kw: List[str]
    soft_kw: List[str]
    threshold: float = 0.68


@app.post("/api/adfilter/rules")
async def save_adfilter_rules(req: AdFilterRulesReq):
    os.makedirs(os.path.dirname(AD_RULES_FILE), exist_ok=True)
    data = {
        "hard_kw":   req.hard_kw,
        "soft_kw":   req.soft_kw,
        "threshold": round(max(0.1, min(1.0, req.threshold)), 4),
    }
    with open(AD_RULES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"ok": True, "file_path": AD_RULES_FILE}


class AdScanReq(BaseModel):
    path: str


@app.post("/api/adfilter/scan")
async def api_adfilter_scan(req: AdScanReq):
    if not os.path.isfile(req.path):
        raise HTTPException(404, "文件不存在")
    loop = asyncio.get_running_loop()

    def _run():
        content, _ = EncodingDetector.read_file_with_auto_encoding(req.path)
        rules = _get_ad_rules()
        return _AdFilter.scan_content(
            content,
            threshold=rules.get('threshold', 0.68),
            hard_kw=rules.get('hard_kw'),
            soft_kw=rules.get('soft_kw'),
        )

    return {'suspicious': await loop.run_in_executor(executor, _run)}


class AdDeleteReq(BaseModel):
    path: str
    line_nums: List[int]          # 1-indexed，来自 scan 接口返回的 line_num 字段
    output_path: str = ""         # 留空则写到 {stem}_adcleaned.txt


@app.post("/api/adfilter/delete")
async def api_adfilter_delete(req: AdDeleteReq):
    if not os.path.isfile(req.path):
        raise HTTPException(404, "文件不存在")
    if not req.line_nums:
        raise HTTPException(400, "line_nums 不能为空")
    loop = asyncio.get_running_loop()

    def _run():
        content, enc = EncodingDetector.read_file_with_auto_encoding(req.path)
        lines = content.split('\n')
        remove_set = {n - 1 for n in req.line_nums if 1 <= n <= len(lines)}
        cleaned = '\n'.join(l for i, l in enumerate(lines) if i not in remove_set)
        out = req.output_path or (
            os.path.splitext(req.path)[0] + '_adcleaned.txt'
        )
        with open(out, 'w', encoding='utf-8') as f:
            f.write(cleaned)
        return {"output_path": out, "removed": len(remove_set)}

    try:
        result = await loop.run_in_executor(executor, _run)
    except Exception as e:
        raise HTTPException(500, str(e))
    return result


# ── 章节识别规则 ───────────────────────────────────────────────
from chapter_config import CHAPTER_RULES_FILE, DEFAULT_CHAPTER_PATTERNS as _DEFAULT_CHAPTER_PATTERNS

CHAPTER_RULES_FILE = CHAPTER_RULES_FILE  # re-export for clarity


def _load_chapter_rules_file() -> dict:
    if not os.path.isfile(CHAPTER_RULES_FILE):
        return {}
    try:
        with open(CHAPTER_RULES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


@app.get("/api/chapter/rules")
async def get_chapter_rules():
    data = _load_chapter_rules_file()
    return {
        "patterns":         data.get('patterns', []),
        "default_patterns": [p[0] for p in _DEFAULT_CHAPTER_PATTERNS],
        "file_path":        CHAPTER_RULES_FILE,
    }


class ChapterRulesReq(BaseModel):
    patterns: List[dict]


@app.post("/api/chapter/rules")
async def save_chapter_rules(req: ChapterRulesReq):
    os.makedirs(os.path.dirname(CHAPTER_RULES_FILE), exist_ok=True)
    with open(CHAPTER_RULES_FILE, 'w', encoding='utf-8') as f:
        json.dump({"patterns": req.patterns}, f, ensure_ascii=False, indent=2)
    return {"ok": True, "file_path": CHAPTER_RULES_FILE}


# ── EPUB 编辑器会话 ────────────────────────────────────────────
import threading as _threading

_SESSION_LOCK = _threading.Lock()
_SESSION: dict = {
    "loaded": False,
    "source_path": "",
    "source_type": "",   # "txt" | "epub"
    "title": "",
    "author": "",
    "description": "",
    "publisher": "",
    "isbn": "",
    "pubdate": "",
    "language": "zh",
    "tags": [],
    "chapters": [],      # [{"title": str, "content": str}]
}

SESSION_FILE = os.path.join(os.path.expanduser('~'), '.txt2epub', 'editor_session.json')


def _save_session():
    os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
    with open(SESSION_FILE, 'w', encoding='utf-8') as f:
        json.dump(_SESSION, f, ensure_ascii=False, indent=2)


def _session_snapshot() -> dict:
    """返回会话摘要（不含完整 content）。"""
    with _SESSION_LOCK:
        chs = _SESSION["chapters"]
        return {
            "loaded":       _SESSION["loaded"],
            "source_path":  _SESSION["source_path"],
            "source_type":  _SESSION["source_type"],
            "title":        _SESSION["title"],
            "author":       _SESSION["author"],
            "description":  _SESSION["description"],
            "publisher":    _SESSION["publisher"],
            "isbn":         _SESSION["isbn"],
            "pubdate":      _SESSION["pubdate"],
            "language":     _SESSION["language"],
            "tags":         _SESSION["tags"],
            "chapters_count": len(chs),
            "chars_total":  sum(len(c.get("content", "")) for c in chs),
        }


# ── 加载文件到编辑器会话 ───────────────────────────────────────
class EditorLoadReq(BaseModel):
    path: str


@app.post("/api/editor/load")
async def api_editor_load(req: EditorLoadReq):
    if not os.path.isfile(req.path):
        raise HTTPException(404, "文件不存在")
    loop = asyncio.get_running_loop()

    def _run():
        ext = os.path.splitext(req.path)[1].lower()
        if ext == '.epub':
            data = EPUBGenerator.parse_epub(req.path)
            src_type = 'epub'
        else:
            content, _ = EncodingDetector.read_file_with_auto_encoding(req.path)
            title = EPUBGenerator._extract_title(content) or ''
            author = EPUBGenerator._extract_author(content) or ''
            chapters = EPUBGenerator._parse_chapters(content)
            if not chapters:
                chapters = [{'title': '正文', 'content': content}]
            data = {
                'title': title, 'author': author, 'description': '',
                'language': 'zh', 'publisher': '', 'isbn': '',
                'pubdate': '', 'tags': [], 'chapters': chapters,
            }
            src_type = 'txt'

        with _SESSION_LOCK:
            _SESSION.update({
                'loaded': True,
                'source_path': req.path,
                'source_type': src_type,
                'title': data.get('title', ''),
                'author': data.get('author', ''),
                'description': data.get('description', ''),
                'publisher': data.get('publisher', ''),
                'isbn': data.get('isbn', ''),
                'pubdate': data.get('pubdate', ''),
                'language': data.get('language', 'zh'),
                'tags': data.get('tags', []),
                'chapters': data.get('chapters', []),
            })
        config.add_recent_file(req.path)
        return _session_snapshot()

    try:
        snap = await loop.run_in_executor(executor, _run)
    except Exception as e:
        raise HTTPException(500, str(e))
    return snap


# ── 会话状态 ────────────────────────────────────────────────────
@app.get("/api/editor/book")
async def api_editor_book():
    return _session_snapshot()


# ── 章节列表 ───────────────────────────────────────────────────
@app.get("/api/editor/chapters")
async def api_editor_chapters():
    with _SESSION_LOCK:
        if not _SESSION["loaded"]:
            raise HTTPException(400, "尚未加载书籍")
        result = []
        for i, ch in enumerate(_SESSION["chapters"]):
            content = ch.get("content", "")
            first_line = content.strip().split('\n')[0][:80] if content.strip() else ''
            result.append({
                "i": i,
                "title": ch["title"],
                "chars": len(content),
                "first_line": first_line,
            })
    return {"chapters": result}


# ── 读/写单个章节 ──────────────────────────────────────────────
@app.get("/api/editor/chapter/{i}")
async def api_editor_chapter_get(i: int):
    with _SESSION_LOCK:
        if not _SESSION["loaded"]:
            raise HTTPException(400, "尚未加载书籍")
        chs = _SESSION["chapters"]
        if i < 0 or i >= len(chs):
            raise HTTPException(404, f"章节 {i} 不存在（共 {len(chs)} 章）")
        return {"i": i, "title": chs[i]["title"], "content": chs[i].get("content", "")}


class ChapterEditReq(BaseModel):
    title: str = ""
    content: str = ""


@app.put("/api/editor/chapter/{i}")
async def api_editor_chapter_put(i: int, req: ChapterEditReq):
    with _SESSION_LOCK:
        if not _SESSION["loaded"]:
            raise HTTPException(400, "尚未加载书籍")
        chs = _SESSION["chapters"]
        if i < 0 or i >= len(chs):
            raise HTTPException(404, f"章节 {i} 不存在")
        chs[i]["title"] = req.title if req.title else chs[i]["title"]
        chs[i]["content"] = req.content
    return {"ok": True, "i": i}


@app.delete("/api/editor/chapter/{i}")
async def api_editor_chapter_delete(i: int):
    with _SESSION_LOCK:
        if not _SESSION["loaded"]:
            raise HTTPException(400, "尚未加载书籍")
        chs = _SESSION["chapters"]
        if i < 0 or i >= len(chs):
            raise HTTPException(404, f"章节 {i} 不存在")
        removed = chs.pop(i)
    return {"ok": True, "removed_title": removed["title"], "chapters_count": len(chs)}


# ── 合并章节（与前一章合并）───────────────────────────────────
@app.post("/api/editor/chapters/merge/{i}")
async def api_editor_chapters_merge(i: int):
    with _SESSION_LOCK:
        if not _SESSION["loaded"]:
            raise HTTPException(400, "尚未加载书籍")
        chs = _SESSION["chapters"]
        if i <= 0 or i >= len(chs):
            raise HTTPException(400, f"章节 {i} 无法与前一章合并（越界）")
        prev = chs[i - 1]
        curr = chs[i]
        prev["content"] = (prev.get("content", "").rstrip('\n')
                           + '\n' + curr.get("content", "").lstrip('\n'))
        chs.pop(i)
    return {"ok": True, "merged_into": i - 1, "chapters_count": len(chs)}


# ── 更新元数据 ────────────────────────────────────────────────
class EditorMetaReq(BaseModel):
    title: str = ""
    author: str = ""
    description: str = ""
    publisher: str = ""
    isbn: str = ""
    pubdate: str = ""
    language: str = ""
    tags: List[str] = []


@app.post("/api/editor/meta")
async def api_editor_meta(req: EditorMetaReq):
    with _SESSION_LOCK:
        if not _SESSION["loaded"]:
            raise HTTPException(400, "尚未加载书籍")
        if req.title:     _SESSION["title"]       = req.title
        if req.author:    _SESSION["author"]      = req.author
        if req.description is not None:  _SESSION["description"] = req.description
        if req.publisher: _SESSION["publisher"]   = req.publisher
        if req.isbn:      _SESSION["isbn"]        = req.isbn
        if req.pubdate:   _SESSION["pubdate"]     = req.pubdate
        if req.language:  _SESSION["language"]    = req.language
        if req.tags is not None:  _SESSION["tags"] = req.tags
    return _session_snapshot()


# ── 全文查找 ──────────────────────────────────────────────────
class EditorFindReq(BaseModel):
    q: str
    case_sensitive: bool = False


@app.post("/api/editor/find")
async def api_editor_find(req: EditorFindReq):
    if not req.q:
        raise HTTPException(400, "查找内容不能为空")
    with _SESSION_LOCK:
        if not _SESSION["loaded"]:
            raise HTTPException(400, "尚未加载书籍")
        flags = 0 if req.case_sensitive else re.IGNORECASE
        pattern = re.compile(re.escape(req.q), flags)
        hits = []
        for i, ch in enumerate(_SESSION["chapters"]):
            for li, line in enumerate(ch.get("content", "").split('\n')):
                if pattern.search(line):
                    hits.append({
                        "chapter_i": i,
                        "chapter_title": ch["title"],
                        "line": li,
                        "text": line.strip()[:120],
                    })
                    if len(hits) >= 500:
                        break
            if len(hits) >= 500:
                break
    return {"count": len(hits), "results": hits}


# ── 全文替换 ──────────────────────────────────────────────────
class EditorReplaceReq(BaseModel):
    find: str
    replace: str = ""
    case_sensitive: bool = False


@app.post("/api/editor/replace")
async def api_editor_replace(req: EditorReplaceReq):
    if not req.find:
        raise HTTPException(400, "查找内容不能为空")
    loop = asyncio.get_running_loop()

    def _run():
        flags = 0 if req.case_sensitive else re.IGNORECASE
        pattern = re.compile(re.escape(req.find), flags)
        total = 0
        with _SESSION_LOCK:
            if not _SESSION["loaded"]:
                raise RuntimeError("尚未加载书籍")
            for ch in _SESSION["chapters"]:
                content = ch.get("content", "")
                new_content, n = pattern.subn(req.replace, content)
                if n:
                    ch["content"] = new_content
                    total += n
        return total

    try:
        replaced = await loop.run_in_executor(executor, _run)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"replaced": replaced}


# ── 从会话构建 EPUB ────────────────────────────────────────────
class EditorBuildReq(BaseModel):
    output_path: str = ""
    cover_image: str = ""
    cover_url: str = ""
    auto_search_cover: bool = False
    margin: str = "0 4%"
    line_height: float = 1.8
    text_indent: str = "2em"
    custom_css: str = ""
    dialog_styles: dict = {}
    drop_cap: bool = False
    style_presets: list = []
    header_images: list = []
    fonts: dict = {}
    illustrations: list = []
    generate_cover_style: str = ""


@app.post("/api/editor/build")
async def api_editor_build(req: EditorBuildReq):
    loop = asyncio.get_running_loop()

    def _run():
        with _SESSION_LOCK:
            if not _SESSION["loaded"]:
                raise RuntimeError("尚未加载书籍")
            chapters  = [dict(c) for c in _SESSION["chapters"]]
            title     = _SESSION["title"]
            author    = _SESSION["author"]
            desc      = _SESSION["description"]
            publisher = _SESSION["publisher"]
            isbn      = _SESSION["isbn"]
            pubdate   = _SESSION["pubdate"]
            language  = _SESSION["language"]
            tags      = list(_SESSION["tags"])

        output_path = req.output_path or None
        epub_path = EPUBGenerator.txt_to_epub(
            None, output_path,
            title, author,
            req.cover_image or None, req.auto_search_cover, req.cover_url or None,
            desc, publisher,
            req.margin, req.line_height, req.text_indent, req.custom_css,
            req.dialog_styles or None,
            isbn, pubdate, language,
            tags or None, req.drop_cap,
            None,                    # volume_map — editor 中已手动排列
            req.style_presets or None,
            req.header_images or None,
            req.fonts or None,
            req.illustrations or None,
            generate_cover_style=req.generate_cover_style or "",
            chapters=chapters,
        )
        if not epub_path:
            raise RuntimeError("EPUB 构建失败")
        return epub_path

    try:
        epub_path = await loop.run_in_executor(executor, _run)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"epub_path": epub_path}


# ── 保存会话到文件 ─────────────────────────────────────────────
@app.post("/api/editor/save-session")
async def api_editor_save_session():
    with _SESSION_LOCK:
        if not _SESSION["loaded"]:
            raise HTTPException(400, "尚未加载书籍")
        _save_session()
    return {"ok": True, "session_file": SESSION_FILE}


# ── 恢复上次会话 ───────────────────────────────────────────────
@app.post("/api/editor/restore-session")
async def api_editor_restore_session():
    if not os.path.isfile(SESSION_FILE):
        raise HTTPException(404, "没有已保存的会话")
    try:
        with open(SESSION_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        with _SESSION_LOCK:
            _SESSION.update(data)
        return _session_snapshot()
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Finder 集成 ────────────────────────────────────────────────
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
    loop = asyncio.get_running_loop()
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


@app.get("/api/epub/cover-styles")
async def cover_styles():
    from cover_gen import list_styles
    return {"styles": list_styles()}


class PreviewCoverReq(BaseModel):
    title: str
    author: str = ""
    style: str = "minimal_light"


@app.post("/api/epub/preview-cover")
async def preview_cover(req: PreviewCoverReq):
    import base64
    from cover_gen import generate_cover as _gen
    loop = asyncio.get_running_loop()
    img_bytes = await loop.run_in_executor(
        executor,
        lambda: _gen(req.title or "书名", req.author, req.style, thumb=True),
    )
    return {"data_url": "data:image/jpeg;base64," + base64.b64encode(img_bytes).decode()}


@app.get("/api/cover-proxy")
async def cover_proxy(url: str, referer: str = ""):
    from cover import _http_get
    loop = asyncio.get_running_loop()
    raw, _ = await loop.run_in_executor(executor, lambda: _http_get(url, referer=referer, timeout=15))
    if not raw:
        raise HTTPException(404, "图片获取失败")
    ct = "image/png" if raw[:4] == b'\x89PNG' else "image/jpeg"
    return Response(content=raw, media_type=ct,
                    headers={"Cache-Control": "public, max-age=3600"})


# ── 文件上传（头图/字体/插图）────────────────────────────────────
from fastapi import UploadFile, File, Form

_UPLOAD_DIR = os.path.join(os.path.expanduser('~'), '.txt2epub', 'uploads')


@app.post("/api/upload/header")
async def upload_header(file: UploadFile = File(...)):
    os.makedirs(os.path.join(_UPLOAD_DIR, 'headers'), exist_ok=True)
    dest = os.path.join(_UPLOAD_DIR, 'headers', file.filename)
    with open(dest, 'wb') as f:
        f.write(await file.read())
    return {"path": dest, "filename": file.filename}


@app.post("/api/upload/font")
async def upload_font(file: UploadFile = File(...), role: str = Form(default="body")):
    os.makedirs(os.path.join(_UPLOAD_DIR, 'fonts'), exist_ok=True)
    dest = os.path.join(_UPLOAD_DIR, 'fonts', file.filename)
    with open(dest, 'wb') as f:
        f.write(await file.read())
    return {"path": dest, "filename": file.filename, "role": role}


@app.post("/api/upload/illust")
async def upload_illust(file: UploadFile = File(...)):
    os.makedirs(os.path.join(_UPLOAD_DIR, 'illusts'), exist_ok=True)
    dest = os.path.join(_UPLOAD_DIR, 'illusts', file.filename)
    with open(dest, 'wb') as f:
        f.write(await file.read())
    return {"path": dest, "filename": file.filename}


@app.get("/api/header/edge-styles")
async def get_edge_styles():
    try:
        from header_image import list_edge_styles
        return {"styles": list_edge_styles()}
    except ImportError:
        return {"styles": []}


# ── 入口 ───────────────────────────────────────────────────────
def main():
    url = "http://127.0.0.1:8765"
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"🌐 TXT→EPUB Web UI 已启动: {url}")
    print("按 Ctrl+C 退出")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")


if __name__ == "__main__":
    main()
