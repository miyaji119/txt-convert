"""配置持久化管理

将用户设置保存到 ~/.txt2epub/config.json，启动时自动加载，关闭时自动保存。

支持的配置项：
    - recent_files: 最近输入文件路径（最多 5 个）
    - recent_dirs: 最近输入目录路径（最多 5 个）
    - default_output_dir: 默认输出目录
    - last_title / last_author: 上次使用的书名/作者
    - cover_choice: 上次封面选项 (1-4)
    - last_tab_index: 上次选中的标签页索引
    - window_geometry: 窗口位置和大小
    - custom_chapter_patterns: 自定义章节正则规则列表

用法：
    from config import config
    config.load()                    # 启动时加载
    config.set('last_title', '书名')  # 设置配置项
    value = config.get('key', default)  # 获取配置项
    config.add_recent_file('/path')  # 添加最近文件
    config.save()                    # 关闭时保存
"""

import os
import json
from typing import Any, List, Dict, Optional


# 配置文件路径
CONFIG_DIR = os.path.expanduser('~/.txt2epub')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

# 最近路径最大保留数量
MAX_RECENT = 5

# 默认配置
DEFAULT_CONFIG = {
    'version': 1,
    'recent_files': [],
    'recent_dirs': [],
    'default_output_dir': '',
    'last_title': '',
    'last_author': '',
    'cover_choice': 4,
    'last_tab_index': 0,
    'window_geometry': '',
    'custom_chapter_patterns': [],
}


class Config:
    """配置管理器（单例模式）

    所有配置项在内存中维护，load() 从文件读取，save() 写入文件。
    文件读写失败时静默降级，不影响 GUI 正常运行。
    """

    def __init__(self):
        self._data: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self._loaded = False

    # ------------------------------------------------------------------
    # 加载 / 保存
    # ------------------------------------------------------------------
    def load(self) -> None:
        """从配置文件加载

        文件不存在或解析失败时使用默认值，不抛异常。
        """
        try:
            if os.path.isfile(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    # 合并：用户配置覆盖默认值，保证新字段有默认值
                    for key, default_val in DEFAULT_CONFIG.items():
                        if key in data:
                            self._data[key] = data[key]
                        else:
                            self._data[key] = default_val
        except (json.JSONDecodeError, OSError, ValueError) as e:
            print(f"[CONFIG] 加载配置失败，使用默认值: {e}")
            self._data = dict(DEFAULT_CONFIG)
        self._loaded = True

    def save(self) -> bool:
        """保存配置到文件

        Returns:
            True=保存成功，False=保存失败
        """
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            return True
        except OSError as e:
            print(f"[CONFIG] 保存配置失败: {e}")
            return False

    # ------------------------------------------------------------------
    # 读写配置项
    # ------------------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项，不存在时返回 default"""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置配置项"""
        self._data[key] = value

    def get_all(self) -> Dict[str, Any]:
        """获取所有配置（只读视图）"""
        return dict(self._data)

    # ------------------------------------------------------------------
    # 最近路径管理
    # ------------------------------------------------------------------
    def add_recent_file(self, path: str) -> None:
        """添加最近文件路径（去重，保留前 MAX_RECENT 个）"""
        if not path:
            return
        path = os.path.abspath(path)
        recent = self._data.get('recent_files', [])
        # 去重：移除已存在的
        recent = [p for p in recent if p != path]
        recent.insert(0, path)
        self._data['recent_files'] = recent[:MAX_RECENT]

    def add_recent_dir(self, path: str) -> None:
        """添加最近目录路径（去重，保留前 MAX_RECENT 个）"""
        if not path:
            return
        path = os.path.abspath(path)
        recent = self._data.get('recent_dirs', [])
        recent = [p for p in recent if p != path]
        recent.insert(0, path)
        self._data['recent_dirs'] = recent[:MAX_RECENT]

    def get_recent_files(self) -> List[str]:
        """获取最近文件列表"""
        return list(self._data.get('recent_files', []))

    def get_recent_dirs(self) -> List[str]:
        """获取最近目录列表"""
        return list(self._data.get('recent_dirs', []))

    # ------------------------------------------------------------------
    # 自定义正则规则管理
    # ------------------------------------------------------------------
    def add_chapter_pattern(self, pattern: str, pattern_type: str = '',
                             enabled: bool = True) -> None:
        """添加自定义章节正则规则

        Args:
            pattern: 正则表达式字符串
            pattern_type: 规则类型标识（如 'chinese', 'custom' 等）
            enabled: 是否启用
        """
        if not pattern:
            return
        patterns = self._data.get('custom_chapter_patterns', [])
        # 去重：相同 pattern 不重复添加
        if not any(p.get('pattern') == pattern for p in patterns):
            patterns.append({
                'pattern': pattern,
                'type': pattern_type or 'custom',
                'enabled': enabled,
            })
            self._data['custom_chapter_patterns'] = patterns

    def remove_chapter_pattern(self, pattern: str) -> None:
        """移除自定义章节正则规则"""
        patterns = self._data.get('custom_chapter_patterns', [])
        self._data['custom_chapter_patterns'] = [
            p for p in patterns if p.get('pattern') != pattern
        ]

    def get_chapter_patterns(self) -> List[Dict]:
        """获取自定义章节正则规则列表"""
        return list(self._data.get('custom_chapter_patterns', []))

    def get_enabled_chapter_patterns(self) -> List[tuple]:
        """获取已启用的自定义正则规则（返回 (pattern, type) 元组列表）

        可直接传给 ChapterConfig 使用：
            config = ChapterConfig('default')
            config.CHAPTER_PATTERNS = custom_patterns + config.CHAPTER_PATTERNS
        """
        patterns = self._data.get('custom_chapter_patterns', [])
        return [(p['pattern'], p['type'])
                for p in patterns if p.get('enabled', True)]


# 全局单例
config = Config()
