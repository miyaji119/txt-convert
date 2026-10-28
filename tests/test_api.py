"""API smoke tests — no server needed, uses httpx.AsyncClient over ASGI transport."""
import pytest
import tempfile
import os
from httpx import AsyncClient, ASGITransport

from web_server import app


@pytest.fixture
def transport():
    return ASGITransport(app=app)


@pytest.fixture
def base_url():
    return "http://test"


# ── 静态路由 ────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_index_returns_html(transport, base_url):
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        r = await c.get("/")
    assert r.status_code == 200
    assert b"html" in r.content.lower()


# ── 字典/列表类端点 ─────────────────────────────────────────────────

@pytest.mark.anyio
async def test_chapter_title_styles(transport, base_url):
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        r = await c.get("/api/epub/chapter-title-styles")
    assert r.status_code == 200
    styles = r.json()
    keys = [s["key"] for s in styles]
    assert "classic" in keys
    assert "plain" in keys
    assert len(styles) >= 4


@pytest.mark.anyio
async def test_edge_styles(transport, base_url):
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        r = await c.get("/api/header/edge-styles")
    assert r.status_code == 200
    data = r.json()
    styles = data["styles"]
    keys = [s["key"] for s in styles]
    assert "none" in keys
    assert "fade" in keys
    assert len(styles) >= 7


@pytest.mark.anyio
async def test_cover_styles(transport, base_url):
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        r = await c.get("/api/epub/cover-styles")
    assert r.status_code == 200
    data = r.json()
    assert "styles" in data
    assert isinstance(data["styles"], list)


@pytest.mark.anyio
async def test_get_recent(transport, base_url):
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        r = await c.get("/api/recent")
    assert r.status_code == 200
    data = r.json()
    assert "files" in data
    assert "dirs" in data


@pytest.mark.anyio
async def test_get_profile(transport, base_url):
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        r = await c.get("/api/profile")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


@pytest.mark.anyio
async def test_adfilter_rules(transport, base_url):
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        r = await c.get("/api/adfilter/rules")
    assert r.status_code == 200
    data = r.json()
    assert "hard_kw" in data
    assert "soft_kw" in data
    assert isinstance(data["threshold"], float)


@pytest.mark.anyio
async def test_chapter_rules(transport, base_url):
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        r = await c.get("/api/chapter/rules")
    assert r.status_code == 200
    data = r.json()
    assert "default_patterns" in data
    assert isinstance(data["default_patterns"], list)


@pytest.mark.anyio
async def test_style_presets(transport, base_url):
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        r = await c.get("/api/style/presets")
    assert r.status_code == 200
    data = r.json()
    assert "presets" in data
    assert "defaults" in data


# ── 路径验证（404）────────────────────────────────────────────────

@pytest.mark.anyio
async def test_extract_meta_missing_file(transport, base_url):
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        r = await c.post("/api/extract-meta", json={"path": "/nonexistent/file.txt"})
    assert r.status_code == 404


@pytest.mark.anyio
async def test_epub_missing_file(transport, base_url):
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        r = await c.post("/api/epub", json={"path": "/nonexistent/file.txt"})
    assert r.status_code == 404


@pytest.mark.anyio
async def test_editor_load_missing_file(transport, base_url):
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        r = await c.post("/api/editor/load", json={"path": "/nonexistent/file.epub"})
    assert r.status_code == 404


@pytest.mark.anyio
async def test_adfilter_scan_missing_file(transport, base_url):
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        r = await c.post("/api/adfilter/scan", json={"path": "/nonexistent/file.txt"})
    assert r.status_code == 404


# ── 输入验证（400）───────────────────────────────────────────────

@pytest.mark.anyio
async def test_cover_proxy_empty_url(transport, base_url):
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        r = await c.get("/api/cover-proxy", params={"url": ""})
    assert r.status_code == 400


@pytest.mark.anyio
async def test_cover_proxy_invalid_url(transport, base_url):
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        r = await c.get("/api/cover-proxy", params={"url": "not-a-url"})
    assert r.status_code == 400


@pytest.mark.anyio
async def test_search_covers_empty_title(transport, base_url):
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        r = await c.post("/api/epub/search-covers", json={"title": "   "})
    assert r.status_code == 400


@pytest.mark.anyio
async def test_editor_find_empty_query(transport, base_url):
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        r = await c.post("/api/editor/find", json={"q": ""})
    assert r.status_code == 400


# ── str_strip_whitespace 生效验证 ─────────────────────────────────

@pytest.mark.anyio
async def test_str_strip_whitespace_on_path(transport, base_url):
    """PathReq.path 应自动去掉首尾空格，确保返回 404 而不是崩溃。"""
    async with AsyncClient(transport=transport, base_url=base_url) as c:
        r = await c.post("/api/extract-meta", json={"path": "  /nonexistent/file.txt  "})
    assert r.status_code == 404  # 路径合法（空格被去掉），但文件不存在


# ── EPUBGenerator 单元测试 ────────────────────────────────────────

def test_chapter_title_styles_dict():
    from epub import EPUBGenerator
    styles = EPUBGenerator.CHAPTER_TITLE_STYLES
    assert isinstance(styles, dict)
    assert len(styles) >= 4
    for key, val in styles.items():
        assert "name" in val
        assert "h1_css" in val
        assert isinstance(val["h1_css"], str)


def test_build_css_with_style():
    from epub import EPUBGenerator
    css = EPUBGenerator._build_css(chapter_title_style="classic")
    assert "h1{" in css or "h1 {" in css


def test_build_css_alignment_overrides():
    from epub import EPUBGenerator
    css_left = EPUBGenerator._build_css(chapter_title_align="left")
    css_right = EPUBGenerator._build_css(chapter_title_align="right")
    assert "text-align:left" in css_left
    assert "text-align:right" in css_right


def test_build_css_unknown_style_ignored():
    """未知样式 key 不应崩溃，也不应写入 h1 规则。"""
    from epub import EPUBGenerator
    css = EPUBGenerator._build_css(chapter_title_style="nonexistent_style_xyz")
    assert "nonexistent_style_xyz" not in css
