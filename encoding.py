"""文件编码检测模块"""

from typing import Optional, Tuple
import codecs


class EncodingDetector:
    """文件编码检测器"""

    ENCODINGS = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'gb18030', 'big5', 'cp1252']

    @staticmethod
    def detect_encoding(filepath: str) -> str:
        """自动检测文件编码"""
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
