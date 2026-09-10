"""封面下载模块（多候选架构）

支持从多个来源搜索小说封面：
- 晋江文学城（jjwxc.net）：搜索页解析 → 详情页封面
- 长佩文学（gongzicp.com）：搜索页 HTML 解析
- 豆瓣读书（book.douban.com）：subject_suggest JSON 接口
- Bing 图片（兜底）

设计要点：
- 多候选机制：每个源返回 List[CoverCandidate]，由 GUI 让用户选择
- 相关性过滤：宽高比 0.5-0.95（书封面标准）、最小尺寸、文件大小阈值
- 本地缓存：~/.txt2epub/covers/{书名hash}.jpg，避免重复搜索
- 健壮性：每个源独立 try/except，单源失败不影响其他源
"""

import os
import re
import json
import hashlib
import ssl
import gzip
import urllib.request
import urllib.parse
from dataclasses import dataclass
from typing import Optional, List, Tuple


# ======================================================================
# 数据类
# ======================================================================
@dataclass
class CoverCandidate:
    """封面候选项"""
    image_url: str           # 图片 URL
    source: str              # 来源标识（jjwxc/gongzicp/douban/bing）
    source_name: str         # 来源中文名（用于展示）
    referer: str = ''        # 下载时需要带的 Referer 头
    book_id: str = ''        # 平台书籍 ID
    book_title: str = ''     # 候选对应的书名
    author: str = ''         # 候选对应的作者
    confidence: float = 0.0  # 相关性置信度（0-1，越高越匹配）


# ======================================================================
# 常量
# ======================================================================
_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
       'AppleWebKit/537.36 (KHTML, like Gecko) '
       'Chrome/120.0.0.0 Safari/537.36')

# 封面尺寸/比例过滤阈值
MIN_FILE_SIZE = 10 * 1024        # 10KB
MIN_WIDTH = 200
MIN_HEIGHT = 280
ASPECT_RATIO_MIN = 0.5           # 宽/高（书封面典型 0.7-0.8）
ASPECT_RATIO_MAX = 0.95

# 缓存目录
CACHE_DIR = os.path.expanduser('~/.txt2epub/covers')


# ======================================================================
# 通用工具函数
# ======================================================================
def _create_ssl_context() -> ssl.SSLContext:
    """创建跳过证书验证的 SSL 上下文"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _http_get(url: str, referer: str = '', timeout: int = 15,
              encoding: str = None) -> Tuple[Optional[bytes], Optional[str]]:
    """通用 HTTP GET，返回 (原始字节, 解码文本)

    若指定 encoding 则同时返回解码后的文本，否则文本为 None。
    """
    headers = {
        'User-Agent': _UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    if referer:
        headers['Referer'] = referer

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout,
                                     context=_create_ssl_context()) as resp:
            raw = resp.read()
            # 尝试 gzip 解压
            if resp.headers.get('Content-Encoding') == 'gzip':
                try:
                    raw = gzip.decompress(raw)
                except Exception:
                    pass
            text = None
            if encoding:
                try:
                    text = raw.decode(encoding, errors='ignore')
                except Exception:
                    text = raw.decode('utf-8', errors='ignore')
            return raw, text
    except Exception as e:
        print(f"[DEBUG] HTTP GET 失败: {url} - {e}")
        return None, None


def _is_valid_image(file_path: str) -> bool:
    """检查文件是否是有效图片（通过文件头）"""
    try:
        with open(file_path, 'rb') as f:
            header = f.read(20)
        return (header.startswith(b'\xff\xd8\xff') or        # JPEG
                header.startswith(b'\x89PNG') or              # PNG
                b'JFIF' in header or
                b'Exif' in header)
    except Exception:
        return False


def _get_image_size(file_path: str) -> Optional[Tuple[int, int]]:
    """读取图片尺寸 (width, height)，不依赖 PIL

    优先用 PIL，失败则解析文件头（JPEG/PNG）。
    """
    # 优先用 PIL（如果可用）
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            return img.size
    except ImportError:
        pass
    except Exception:
        pass

    # 回退到文件头解析
    try:
        with open(file_path, 'rb') as f:
            header = f.read(32)

        # PNG: 宽高在 16-24 字节
        if header.startswith(b'\x89PNG'):
            import struct
            w = struct.unpack('>I', header[16:20])[0]
            h = struct.unpack('>I', header[20:24])[0]
            return (w, h)

        # JPEG: 需扫描 SOF0/SOF2 标记
        if header.startswith(b'\xff\xd8'):
            with open(file_path, 'rb') as f:
                f.read(2)  # 跳过 SOI
                while True:
                    marker = f.read(2)
                    if len(marker) < 2:
                        break
                    if marker[0] != 0xff:
                        break
                    # SOF0=0xC0, SOF2=0xC2 等
                    if marker[1] in (0xc0, 0xc1, 0xc2, 0xc3,
                                     0xc5, 0xc6, 0xc7,
                                     0xc9, 0xca, 0xcb,
                                     0xcd, 0xce, 0xcf):
                        f.read(3)  # 长度(2) + 精度(1)
                        h = int.from_bytes(f.read(2), 'big')
                        w = int.from_bytes(f.read(2), 'big')
                        return (w, h)
                    else:
                        length = int.from_bytes(f.read(2), 'big')
                        f.read(length - 2)
    except Exception:
        pass

    return None


def _is_book_cover_shape(file_path: str) -> bool:
    """检查图片是否像书封面（竖向、比例合适、尺寸达标）"""
    size = _get_image_size(file_path)
    if not size:
        # 无法识别尺寸时，仅按文件大小判断
        try:
            return os.path.getsize(file_path) >= MIN_FILE_SIZE
        except Exception:
            return False

    w, h = size
    if w < MIN_WIDTH or h < MIN_HEIGHT:
        return False
    if h <= 0:
        return False
    ratio = w / h
    return ASPECT_RATIO_MIN <= ratio <= ASPECT_RATIO_MAX


def _download_image(url: str, local_path: str,
                    referer: str = '', min_size: int = MIN_FILE_SIZE) -> bool:
    """下载图片到本地，带尺寸校验"""
    raw, _ = _http_get(url, referer=referer, timeout=20)
    if not raw:
        return False
    if len(raw) < min_size:
        print(f"[DEBUG] 图片太小 ({len(raw)}B)，跳过: {url}")
        return False
    try:
        with open(local_path, 'wb') as f:
            f.write(raw)
        if not _is_valid_image(local_path):
            print(f"[DEBUG] 不是有效图片格式: {url}")
            os.remove(local_path)
            return False
        return True
    except Exception as e:
        print(f"[DEBUG] 保存失败: {url} - {e}")
        return False


# ======================================================================
# 缓存
# ======================================================================
def _cache_key(book_title: str, author: str = '') -> str:
    """生成缓存键（书名+作者的 MD5）"""
    key = f"{book_title.strip()}|{author.strip()}".encode('utf-8')
    return hashlib.md5(key).hexdigest()[:16]


def _get_cache_path(book_title: str, author: str = '') -> str:
    """获取缓存文件路径"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{_cache_key(book_title, author)}.jpg")


def _save_to_cache(book_title: str, image_path: str, author: str = '') -> str:
    """将下载的图片复制到缓存"""
    try:
        import shutil
        cache_path = _get_cache_path(book_title, author)
        shutil.copy2(image_path, cache_path)
        return cache_path
    except Exception as e:
        print(f"[DEBUG] 缓存写入失败: {e}")
        return ''


def _load_from_cache(book_title: str, author: str = '') -> Optional[str]:
    """从缓存加载封面，命中返回路径，未命中返回 None"""
    cache_path = _get_cache_path(book_title, author)
    if os.path.isfile(cache_path) and os.path.getsize(cache_path) >= MIN_FILE_SIZE:
        if _is_valid_image(cache_path):
            return cache_path
    return None


# ======================================================================
# 搜索源 1：晋江文学城
# ======================================================================
def _search_via_jjwxc(book_title: str, author: str = '') -> List[CoverCandidate]:
    """晋江搜索：调用 search_ajax.php JSON API → 详情页 → 封面

    晋江搜索页是 JS 渲染，实际数据通过 AJAX API 获取：
        https://www.jjwxc.net/search/search_ajax.php?action=search&keywords={kw}&type=1&version=1&getfull=1

    返回 JSON: {"status":200, "data":[{"novelid":xxx, "novelname":xxx, "authorname":xxx}, ...]}

    拿到 novelid 后访问详情页 onebook.php?novel_id={id} 提取封面图。
    详情页封面: <img itemprop="image" src="...">
    """
    candidates: List[CoverCandidate] = []
    kw = book_title.strip()
    if not kw:
        return candidates

    # 步骤 1：调用搜索 API
    api_url = (f"https://www.jjwxc.net/search/search_ajax.php"
               f"?action=search&keywords={urllib.parse.quote(kw)}"
               f"&type=1&version=1&getfull=1")
    print(f"   [晋江] 搜索: {kw}")

    raw, _ = _http_get(api_url, referer='https://www.jjwxc.net/',
                       timeout=15, encoding=None)
    if not raw:
        print(f"   [晋江] 搜索 API 请求失败")
        return candidates

    try:
        data = json.loads(raw.decode('utf-8', errors='ignore'))
    except Exception as e:
        print(f"   [晋江] JSON 解析失败: {e}")
        return candidates

    if data.get('status') != 200 or not data.get('data'):
        print(f"   [晋江] 搜索无结果 (status={data.get('status')})")
        return candidates

    books = data['data'][:5]  # 最多取前 5 本
    print(f"   [晋江] 找到 {len(books)} 本候选书")

    # 步骤 2：对每本书访问详情页提取封面
    for book in books:
        nid = str(book.get('novelid', ''))
        novelname = book.get('novelname', '')
        authorname = book.get('authorname', '')
        if not nid:
            continue

        detail_url = f"https://www.jjwxc.net/onebook.php?novelid={nid}"
        _, detail_html = _http_get(detail_url, referer='https://www.jjwxc.net/',
                                    timeout=15, encoding='gb18030')
        if not detail_html:
            continue

        # 提取封面图：<img itemprop="image" src="..."> 优先
        cover_match = re.search(
            r'<img[^>]*itemprop=["\']image["\'][^>]*src=["\']([^"\']+)["\']',
            detail_html, re.IGNORECASE
        )
        if not cover_match:
            # 兜底：找 jjwxc 域名下的 .jpg/.png 大图
            for m in re.finditer(
                r'<img[^>]*src=["\']([^"\']+\.(?:jpg|jpeg|png))["\']',
                detail_html, re.IGNORECASE
            ):
                url = m.group(1)
                if not any(k in url.lower() for k in ['logo', 'icon', 'avatar', 'btn', 'header']):
                    cover_match = m
                    break

        if not cover_match:
            continue

        img_url = cover_match.group(1)
        # 补全协议和域名
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif img_url.startswith('/'):
            img_url = 'https://www.jjwxc.net' + img_url
        elif not img_url.startswith('http'):
            img_url = 'https://www.jjwxc.net/' + img_url

        # 相关性：API 返回的 novelname 与查询书名比对
        confidence = 0.0
        if novelname == kw:
            confidence = 1.0
        elif kw in novelname:
            confidence = 0.85
        elif novelname and novelname in kw:
            confidence = 0.65

        # 作者匹配提升置信度
        if author.strip() and authorname and author.strip() in authorname:
            confidence = min(1.0, confidence + 0.1)

        candidates.append(CoverCandidate(
            image_url=img_url,
            source='jjwxc',
            source_name='晋江文学城',
            referer=detail_url,
            book_id=nid,
            book_title=novelname,
            author=authorname,
            confidence=confidence,
        ))

    print(f"   [晋江] 解析出 {len(candidates)} 个封面候选")
    return candidates


# ======================================================================
# 搜索源 2：长佩文学
# ======================================================================
def _search_via_gongzicp(book_title: str, author: str = '') -> List[CoverCandidate]:
    """长佩搜索：解析搜索结果页中的书籍封面

    ⚠️ 限制说明：长佩是纯 SPA（Vue 渲染），搜索页 HTML 不含数据，
    webapi 端点（/webapi/search/getSearchPageList 等）有反爬保护，
    返回 "访问异常"。因此本函数当前通常返回空候选。

    保留函数骨架供未来扩展（如集成浏览器自动化或第三方接口）。
    当前主要依赖晋江和豆瓣两个源。
    """
    candidates: List[CoverCandidate] = []
    kw = book_title.strip()
    if not kw:
        return candidates

    search_url = f"https://www.gongzicp.com/search?key={urllib.parse.quote(kw)}"
    print(f"   [长佩] 搜索: {kw}")

    _, html = _http_get(search_url, referer='https://www.gongzicp.com/',
                       timeout=15, encoding='utf-8')
    if not html:
        print(f"   [长佩] 搜索页获取失败")
        return candidates

    # 策略1：解析 HTML 中的 novel 详情页链接
    # 长佩详情页 URL 形式：/novel/{id} 或 /book/{id}
    novel_ids = re.findall(r'/(?:novel|book)/(\d+)', html)
    seen = set()
    unique_ids = []
    for nid in novel_ids:
        if nid not in seen:
            seen.add(nid)
            unique_ids.append(nid)
            if len(unique_ids) >= 5:
                break

    if unique_ids:
        print(f"   [长佩] 找到 {len(unique_ids)} 本候选书")
        for nid in unique_ids:
            detail_url = f"https://www.gongzicp.com/novel/{nid}"
            _, detail_html = _http_get(detail_url, referer=search_url,
                                        timeout=15, encoding='utf-8')
            if not detail_html:
                continue

            # 提取封面：og:image meta 标签优先
            cover_match = re.search(
                r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']',
                detail_html, re.IGNORECASE
            )
            if not cover_match:
                # 兜底：找 .jpg/.png 大图
                for m in re.finditer(
                    r'<img[^>]*src=["\']([^"\']+\.(?:jpg|jpeg|png))["\']',
                    detail_html, re.IGNORECASE
                ):
                    url = m.group(1)
                    if not any(k in url.lower() for k in ['logo', 'icon', 'avatar', 'btn', 'default']):
                        cover_match = m
                        break

            if not cover_match:
                continue

            img_url = cover_match.group(1)
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            elif img_url.startswith('/'):
                img_url = 'https://www.gongzicp.com' + img_url
            elif not img_url.startswith('http'):
                img_url = 'https://www.gongzicp.com/' + img_url

            # 提取书名
            title_match = re.search(
                r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']',
                detail_html, re.IGNORECASE
            ) or re.search(r'<title>([^<]+)</title>', detail_html)
            matched_title = title_match.group(1).strip() if title_match else ''

            confidence = 0.0
            if matched_title == kw:
                confidence = 1.0
            elif kw in matched_title:
                confidence = 0.8

            candidates.append(CoverCandidate(
                image_url=img_url,
                source='gongzicp',
                source_name='长佩文学',
                referer=detail_url,
                book_id=nid,
                book_title=matched_title,
                confidence=confidence,
            ))
    else:
        # 策略2：直接从搜索页 HTML 提取图片 URL（兜底）
        for m in re.finditer(
            r'<img[^>]*src=["\']([^"\']+\.(?:jpg|jpeg|png))["\']',
            html, re.IGNORECASE
        ):
            img_url = m.group(1)
            if any(k in img_url.lower() for k in ['logo', 'icon', 'avatar', 'btn', 'default', 'header']):
                continue
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            candidates.append(CoverCandidate(
                image_url=img_url,
                source='gongzicp',
                source_name='长佩文学',
                referer=search_url,
                book_title='',
                confidence=0.3,  # 低置信度（无法确认书名匹配）
            ))
            if len(candidates) >= 3:
                break

    print(f"   [长佩] 解析出 {len(candidates)} 个封面候选")
    return candidates


# ======================================================================
# 搜索源 3：豆瓣读书
# ======================================================================
def _search_via_douban(book_title: str, author: str = '') -> List[CoverCandidate]:
    """豆瓣搜索：使用 subject_suggest JSON 接口

    接口：https://book.douban.com/j/subject_suggest?q={kw}
    返回 JSON 数组，含 title/url/pic/author_name/id
    pic 是小图（/s/），需转换为 /l/ 获取大图。

    接口只返回最匹配的少数结果，所以分别用「书名」「书名+作者」查询。
    """
    candidates: List[CoverCandidate] = []
    queries = [book_title.strip()]
    if author.strip() and author.strip() not in book_title:
        queries.append(f"{book_title.strip()} {author.strip()}")

    seen_ids = set()
    for q in queries:
        if not q:
            continue
        print(f"   [豆瓣] 搜索: {q}")
        url = f"https://book.douban.com/j/subject_suggest?q={urllib.parse.quote(q)}"
        raw, _ = _http_get(url, referer='https://book.douban.com/',
                           timeout=10, encoding=None)
        if not raw:
            continue
        try:
            data = json.loads(raw.decode('utf-8', errors='ignore'))
        except Exception as e:
            print(f"   [豆瓣] JSON 解析失败: {e}")
            continue

        if not isinstance(data, list):
            continue

        for item in data:
            if not isinstance(item, dict):
                continue
            item_id = item.get('id', '')
            if not item_id or item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            pic = item.get('pic', '')
            if not pic:
                continue

            # 小图转大图：/view/subject/s/ → /view/subject/l/
            large_pic = pic.replace('/view/subject/s/', '/view/subject/l/')
            if large_pic == pic:
                # 兜底：URL 末尾的 sXXXX.jpg → lXXXX.jpg
                large_pic = re.sub(r'/s\d+', '/l', pic)

            title = item.get('title', '')
            item_author = item.get('author_name', '')

            # 相关性：书名完全匹配 1.0，包含 0.8
            confidence = 0.0
            if title == book_title.strip():
                confidence = 1.0
            elif book_title.strip() in title:
                confidence = 0.8
            elif title and title in book_title.strip():
                confidence = 0.6

            # 作者匹配提升置信度
            if author.strip() and item_author and author.strip() in item_author:
                confidence = min(1.0, confidence + 0.1)

            candidates.append(CoverCandidate(
                image_url=large_pic,
                source='douban',
                source_name='豆瓣读书',
                referer=item.get('url', 'https://book.douban.com/'),
                book_id=item_id,
                book_title=title,
                author=item_author,
                confidence=confidence,
            ))

    print(f"   [豆瓣] 解析出 {len(candidates)} 个封面候选")
    return candidates


# ======================================================================
# 搜索源 4：Bing 图片（兜底）
# ======================================================================
def _search_via_bing(book_title: str, author: str = '') -> List[CoverCandidate]:
    """Bing 图片搜索（兜底）"""
    candidates: List[CoverCandidate] = []
    kw = f"{book_title.strip()} {author.strip()} 封面".strip()
    if not kw:
        return candidates

    print(f"   [Bing] 搜索: {kw}")
    search_url = f"https://www.bing.com/images/search?q={urllib.parse.quote(kw)}&first=0&count=8"
    _, html = _http_get(search_url, timeout=15, encoding='utf-8')
    if not html:
        return candidates

    # 提取 mediaurl= 参数
    urls = re.findall(
        r'mediaurl=(https?://[^&"]+\.(?:jpg|jpeg|png))',
        html, re.IGNORECASE
    )
    # 去重，过滤 bing/microsoft 自家图
    seen = set()
    for u in urls:
        if u in seen:
            continue
        if any(k in u.lower() for k in ['bing.com', 'microsoft.com', 'msn.com']):
            continue
        seen.add(u)
        candidates.append(CoverCandidate(
            image_url=u,
            source='bing',
            source_name='Bing 图片',
            referer=search_url,
            confidence=0.2,  # 低置信度（无法确认相关性）
        ))
        if len(candidates) >= 5:
            break

    print(f"   [Bing] 解析出 {len(candidates)} 个封面候选")
    return candidates


# ======================================================================
# 主搜索接口
# ======================================================================
def search_cover_candidates(book_title: str,
                             author: str = '') -> List[CoverCandidate]:
    """搜索封面，返回所有候选（按置信度降序）

    依次调用晋江、长佩、豆瓣、Bing 四个源，合并去重。
    单源失败不影响其他源。
    """
    if not book_title or not book_title.strip():
        print("⚠️ 未提供书名，无法搜索封面")
        return []

    print(f"🔍 正在搜索封面: {book_title}{' by ' + author if author else ''}")

    all_candidates: List[CoverCandidate] = []

    # 按优先级顺序调用各搜索源
    sources = [
        ('晋江文学城', lambda: _search_via_jjwxc(book_title, author)),
        ('豆瓣读书', lambda: _search_via_douban(book_title, author)),
        ('长佩文学', lambda: _search_via_gongzicp(book_title, author)),
        ('Bing 图片', lambda: _search_via_bing(book_title, author)),
    ]

    for source_name, search_fn in sources:
        try:
            cs = search_fn()
            all_candidates.extend(cs)
        except Exception as e:
            print(f"   [{source_name}] 搜索异常: {e}")
            continue

    # 按 confidence 降序排序
    all_candidates.sort(key=lambda c: c.confidence, reverse=True)

    # 去重（同 URL 只保留置信度最高的）
    seen_urls = set()
    unique: List[CoverCandidate] = []
    for c in all_candidates:
        if c.image_url in seen_urls:
            continue
        seen_urls.add(c.image_url)
        unique.append(c)

    print(f"✓ 共获取 {len(unique)} 个封面候选")
    return unique


def download_candidate(candidate: CoverCandidate,
                       output_dir: str = None,
                       filename: str = 'cover.jpg') -> Optional[str]:
    """下载单个候选到本地，返回本地路径

    下载后会校验：文件大小、图片格式、宽高比。
    校验失败返回 None。
    """
    if not candidate or not candidate.image_url:
        return None

    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(output_dir, exist_ok=True)

    local_path = os.path.join(output_dir, filename)

    print(f"[DEBUG] 下载候选: {candidate.image_url[:80]}... (来自 {candidate.source_name})")
    if not _download_image(candidate.image_url, local_path,
                           referer=candidate.referer):
        return None

    # 尺寸/比例校验
    if not _is_book_cover_shape(local_path):
        print(f"[DEBUG] 候选不符合书封面形状，跳过: {candidate.image_url[:80]}")
        try:
            os.remove(local_path)
        except Exception:
            pass
        return None

    print(f"✅ 候选下载成功: {local_path}")
    return local_path


def search_and_download_cover(book_title: str, author: str = '',
                               output_dir: str = None) -> Optional[str]:
    """向后兼容的封面搜索接口

    自动选择最佳候选下载。若需要用户选择，请改用：
        search_cover_candidates() + download_candidate()
    """
    if not book_title or not book_title.strip():
        print("⚠️ 未提供书名，无法搜索封面")
        return None

    # 1. 检查缓存
    cached = _load_from_cache(book_title, author)
    if cached:
        print(f"✓ 命中封面缓存: {cached}")
        if output_dir:
            import shutil
            target = os.path.join(output_dir, 'cover.jpg')
            try:
                shutil.copy2(cached, target)
                return target
            except Exception:
                pass
        return cached

    # 2. 搜索候选
    candidates = search_cover_candidates(book_title, author)
    if not candidates:
        print("⚠️ 未能找到封面图片")
        return None

    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(__file__))

    # 3. 按置信度顺序尝试下载，第一个通过校验的即返回
    for candidate in candidates:
        result = download_candidate(candidate, output_dir)
        if result:
            # 写入缓存
            _save_to_cache(book_title, result, author)
            return result

    print("⚠️ 所有候选均未通过校验")
    return None


def download_cover_from_url(url: str, output_dir: str = None) -> Optional[str]:
    """从 URL 下载封面图片（保留原接口）"""
    if not url:
        return None
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"[DEBUG] 从 URL 下载: {url}")

    local_path = os.path.join(output_dir, 'cover.jpg')
    if _download_image(url, local_path, min_size=1024):
        print(f"✅ 封面下载成功: {local_path}")
        return local_path
    print(f"⚠️ 封面下载失败: {url}")
    return None


# ======================================================================
# 兼容层：保留旧类接口
# ======================================================================
class CoverDownloader:
    """小说封面下载器（兼容旧接口，内部委托给模块函数）

    新代码建议直接调用模块级函数：
        from cover import search_cover_candidates, download_candidate
    """

    # 通用工具（静态方法委托）
    _create_ssl_context = staticmethod(_create_ssl_context)
    _is_valid_image = staticmethod(_is_valid_image)
    _download_image = staticmethod(_download_image)

    # 搜索源
    _search_via_jjwxc = staticmethod(_search_via_jjwxc)
    _search_via_gongzicp = staticmethod(_search_via_gongzicp)
    _search_via_douban = staticmethod(_search_via_douban)
    _search_via_bing_images = staticmethod(_search_via_bing)

    # 主接口
    search_cover_candidates = staticmethod(search_cover_candidates)
    download_candidate = staticmethod(download_candidate)
    search_and_download_cover = staticmethod(search_and_download_cover)
    download_cover_from_url = staticmethod(download_cover_from_url)
