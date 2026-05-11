"""封面下载模块"""

import os
import re
import json
from typing import Optional, List


class CoverDownloader:
    """小说封面下载器"""

    @staticmethod
    def _create_ssl_context():
        """创建SSL上下文，跳过证书验证"""
        try:
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        except:
            return None

    @staticmethod
    def _download_image(url: str, local_path: str) -> bool:
        """下载图片到本地"""
        try:
            import urllib.request
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            req = urllib.request.Request(url, headers=headers)
            ssl_ctx = CoverDownloader._create_ssl_context()
            with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) if ssl_ctx else urllib.request.urlopen(req, timeout=15) as response:
                image_data = response.read()
            return len(image_data) >= 5000 and open(local_path, 'wb').write(image_data)
        except:
            return False

    @staticmethod
    def _is_valid_image(file_path: str) -> bool:
        """检查下载的文件是否是有效的图片"""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(20)
            return header.startswith(b'\xff\xd8\xff') or header.startswith(b'\x89PNG') or b'JFIF' in header or b'Exif' in header
        except:
            return False

    @staticmethod
    def _extract_bing_image_urls(html_content: str) -> List[str]:
        """从Bing搜索结果中提取图片URL"""
        urls = []
        for pattern in [r'mediaurl=(https?://[^&"]+\.(?:jpg|jpeg|png))', r'src="(https?://[^"]+\.(?:jpg|jpeg|png))"']:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            urls.extend([m for m in matches if 'bing' not in m and 'microsoft' not in m and len(m) < 300])
        return list(dict.fromkeys(urls))

    @staticmethod
    def _search_via_google(query: str, site: str, output_dir: str) -> Optional[str]:
        """通过Google图片搜索获取封面"""
        try:
            import urllib.request
            import urllib.parse
            encoded_query = urllib.parse.quote(f"{query} site:{site} cover")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'}
            search_url = f"https://www.google.com/search?q={encoded_query}&tbm=isch"
            req = urllib.request.Request(search_url, headers=headers)
            ssl_ctx = CoverDownloader._create_ssl_context()
            context = ssl_ctx if ssl_ctx else None
            with urllib.request.urlopen(req, timeout=15, context=context) as response:
                html_content = response.read().decode('utf-8', errors='ignore')

            for pattern in [r'data-src="(https?://[^"]+\.(?:jpg|jpeg|png))"', r'src="(https?://[^"]*' + site.replace('.', r'\.') + r'[^"]*\.(?:jpg|jpeg|png))"', r'"(https?://[^"]*cover[^"]*\.(?:jpg|jpeg|png))"']:
                for img_url in re.findall(pattern, html_content, re.IGNORECASE):
                    if len(img_url) > 50:
                        local_path = os.path.join(output_dir, "cover.jpg")
                        if CoverDownloader._download_image(img_url, local_path):
                            return local_path
            return None
        except Exception as e:
            print(f"   {site} 搜索失败: {e}")
            return None

    @staticmethod
    def _search_via_openlibrary(book_title: str, author: str, output_dir: str) -> Optional[str]:
        """通过Open Library搜索封面"""
        try:
            import urllib.request
            import urllib.parse
            query = urllib.parse.quote(f"{book_title} {author}".strip())
            url = f"https://openlibrary.org/search.json?q={query}&limit=5"
            print(f"   尝试Open Library...")
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            ssl_ctx = CoverDownloader._create_ssl_context()
            with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as response:
                data = json.loads(response.read().decode('utf-8'))
            for doc in data.get('docs', [])[:5]:
                for key in ['cover_i', ('isbn', [])]:
                    if key == 'cover_i':
                        cover_id = doc.get(key)
                        if cover_id:
                            cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                            local_path = os.path.join(output_dir, "cover.jpg")
                            if CoverDownloader._download_image(cover_url, local_path):
                                return local_path
                    elif key == 'isbn':
                        for isbn in doc.get(key, [])[:3]:
                            cover_url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
                            local_path = os.path.join(output_dir, "cover.jpg")
                            if CoverDownloader._download_image(cover_url, local_path):
                                return local_path
            return None
        except Exception as e:
            print(f"   Open Library搜索失败: {e}")
            return None

    @staticmethod
    def _search_via_bing_images(book_title: str, author: str, output_dir: str) -> Optional[str]:
        """通过Bing图片搜索获取封面"""
        try:
            import urllib.request
            import urllib.parse
            query = urllib.parse.quote(f"{book_title} {author} book cover".strip())
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'}
            search_url = f"https://www.bing.com/images/search?q={query}&first=0&count=5"
            req = urllib.request.Request(search_url, headers=headers)
            ssl_ctx = CoverDownloader._create_ssl_context()
            with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as response:
                html_content = response.read().decode('utf-8')
            for img_url in CoverDownloader._extract_bing_image_urls(html_content)[:5]:
                local_path = os.path.join(output_dir, "cover.jpg")
                if CoverDownloader._download_image(img_url, local_path) and CoverDownloader._is_valid_image(local_path):
                    return local_path
                if os.path.exists(local_path):
                    os.remove(local_path)
            return None
        except Exception as e:
            print(f"   Bing图片搜索失败: {e}")
            return None

    @staticmethod
    def search_and_download_cover(book_title: str, author: str = "", output_dir: str = None) -> Optional[str]:
        """搜索并下载小说封面"""
        if not book_title:
            print("⚠️ 未提供书名，无法搜索封面")
            return None
        if output_dir is None:
            output_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"🔍 正在搜索封面: {book_title} {'by ' + author if author else ''}")

        search_methods = [
            lambda: CoverDownloader._search_via_google(f"{book_title} {author}", "jjwxc.net", output_dir),
            lambda: CoverDownloader._search_via_google(f"{book_title} {author}", "gongzicp.com", output_dir),
            lambda: CoverDownloader._search_via_google(f"{book_title} {author}", "qidian.com", output_dir),
            lambda: CoverDownloader._search_via_bing_images(book_title, author, output_dir),
            lambda: CoverDownloader._search_via_openlibrary(book_title, author, output_dir),
        ]

        for method in search_methods:
            cover_path = method()
            if cover_path:
                print(f"✅ 封面下载成功: {cover_path}")
                return cover_path

        print("⚠️ 未能找到封面图片")
        return None

    @staticmethod
    def download_cover_from_url(url: str, output_dir: str = None) -> Optional[str]:
        """从URL下载封面图片"""
        if not url:
            return None
        if output_dir is None:
            output_dir = os.path.dirname(os.path.abspath(__file__))
        try:
            import ssl
            import gzip
            import urllib.request
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, context=context, timeout=30) as response:
                raw_data = response.read()
            try:
                image_data = gzip.decompress(raw_data)
            except:
                image_data = raw_data
            cover_path = os.path.join(output_dir, 'cover.jpg')
            with open(cover_path, 'wb') as f:
                f.write(image_data)
            print(f"✅ 封面下载成功: {cover_path}")
            return cover_path
        except Exception as e:
            print(f"⚠️ 封面下载失败: {e}")
            return None
