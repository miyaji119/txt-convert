"""文件编码检测模块"""

from typing import Optional, Tuple
import codecs


class EncodingDetector:
    """文件编码检测器"""

    ENCODINGS = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312', 'gb18030', 'big5', 'cp1252']

    # BOM 标记与编码的映射
    BOM_MAP = [
        (b'\xff\xfe', 'utf-16-le'),
        (b'\xfe\xff', 'utf-16-be'),
        (b'\xef\xbb\xbf', 'utf-8-sig'),
    ]

    @staticmethod
    def detect_encoding(filepath: str) -> str:
        """自动检测文件编码"""
        # 1. 先检查 BOM 标记
        try:
            with open(filepath, 'rb') as f:
                bom = f.read(4)
            for bom_bytes, enc in EncodingDetector.BOM_MAP:
                if bom.startswith(bom_bytes):
                    return enc
        except (IOError, OSError):
            pass

        # 2. 逐一尝试编码
        for encoding in EncodingDetector.ENCODINGS:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    f.read(1024)
                return encoding
            except (UnicodeDecodeError, LookupError):
                continue
        return 'utf-8'

    @staticmethod
    def read_file_with_auto_encoding(filepath: str) -> Tuple[str, str]:
        """使用自动检测的编码读取文件"""
        encoding = EncodingDetector.detect_encoding(filepath)
        print(f"   编码检测: 使用{encoding}编码")
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                content = f.read()
        except:
            with codecs.open(filepath, 'r', encoding='gbk', errors='ignore') as f:
                content = f.read()
            encoding = 'gbk'
        return content, encoding
