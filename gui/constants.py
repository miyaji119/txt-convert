"""GUI 全局常量"""

APP_VERSION = "v2.0"
APP_TITLE = f"TXT 转 EPUB 工具 {APP_VERSION}"

# EPUB 支持标志（依赖 ebooklib）
try:
    from ebooklib import epub  # noqa: F401
    EPUB_SUPPORT = True
except ImportError:
    EPUB_SUPPORT = False
