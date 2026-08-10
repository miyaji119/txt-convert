"""章节识别配置文件

支持针对不同小说类型配置不同的过滤规则和章节格式模式。
"""

from typing import List, Dict


class ChapterConfig:
    """章节识别配置类"""

    _CONFIGS = None  # 缓存

    def __init__(self, config_name: str = 'default'):
        self.config_name = config_name
        self.load_config(config_name)

    @classmethod
    def _get_all_configs(cls) -> Dict[str, Dict]:
        """获取所有可用配置（带缓存）"""
        if cls._CONFIGS is None:
            cls._CONFIGS = {
                'default': {
                    'chapter_patterns': DEFAULT_CHAPTER_PATTERNS,
                    'next_chapter_patterns': DEFAULT_NEXT_CHAPTER_PATTERNS,
                    'filter_rules': DEFAULT_FILTER_RULES,
                },
                'bl': {
                    'chapter_patterns': DEFAULT_CHAPTER_PATTERNS,
                    'next_chapter_patterns': DEFAULT_NEXT_CHAPTER_PATTERNS,
                    'filter_rules': DEFAULT_FILTER_RULES + BL_SPECIFIC_FILTERS,
                },
                'fantasy': {
                    'chapter_patterns': DEFAULT_CHAPTER_PATTERNS + FANTASY_PATTERNS,
                    'next_chapter_patterns': DEFAULT_NEXT_CHAPTER_PATTERNS + FANTASY_NEXT_PATTERNS,
                    'filter_rules': DEFAULT_FILTER_RULES,
                },
                'detective': {
                    'chapter_patterns': DEFAULT_CHAPTER_PATTERNS + DETECTIVE_PATTERNS,
                    'next_chapter_patterns': DEFAULT_NEXT_CHAPTER_PATTERNS,
                    'filter_rules': DEFAULT_FILTER_RULES,
                },
            }
        return cls._CONFIGS

    def load_config(self, config_name: str):
        """加载指定的配置"""
        configs = self._get_all_configs()
        config = configs.get(config_name, configs['default'])
        self.CHAPTER_PATTERNS = config['chapter_patterns']
        self.NEXT_CHAPTER_PATTERNS = config['next_chapter_patterns']
        self.FILTER_RULES = config['filter_rules']

    def get_config_names(self) -> List[str]:
        """获取所有可用配置名称"""
        return list(self._get_all_configs().keys())


# ==================== 默认章节格式模式 ====================

DEFAULT_CHAPTER_PATTERNS = [
    (r'^[=]+第\s*(\d+)\s*章\s*(.*?)[=]*$', 'equals'),
    (r'^第\s*([零一二三四五六七八九十百千万\d]+)\s*章\s*(.*)$', 'chinese'),
    (r'^\d+、第([零一二三四五六七八九十百千万\d]+)章\s*(.*)$', 'number_chinese'),
    (r'^(\d+)\s*[·•・]\s*第\s*(\d+)\s*章\s*(.*)$', 'number_dot_chapter'),
    (r'^(\d+)\s*[·•・]\s*(番外.*)$', 'number_dot_fanwai'),
    (r'^(\d+)\s*[·•・]\s*(.+)$', 'number_dot_title'),
    (r'^\d+、番外(.*)$', 'number_fanwai'),
    (r'^番外([零一二三四五六七八九十百千万\d]+)(.*)$', 'fanwai'),
    (r'^(\d+)、(.*)$', 'simple_number'),
    (r'^(\d+)\.?\s*(.+)$', 'number_title_combined'),
    (r'^楔子\s*(.*)$', 'xiezi'),
    (r'^[◇◆\*•·]\s*第(\d+)章\s*(.*)$', 'special_prefix'),
    (r'^第([零一二三四五六七八九十百千万]+)案[：:]\s*(.*)$', 'case_volume'),
    (r'^\[(\d+)\](.*)$', 'bracket_number'),
    (r'^(\d+)$', 'standalone_number'),
]

DEFAULT_NEXT_CHAPTER_PATTERNS = [
    r'^[=]+第\s*\d+\s*章\s*.*[=]*$',
    r'^第[零一二三四五六七八九十百千万\d]+章\s*.*$',
    r'^\d+、[零一二三四五六七八九十百千万\d]+章\s*.*$',
    r'^(攻)?第[零一二三四五六七八九十百千万\d]+章\s*.*$',
    r'^\d+\s*[·•・]\s*第\s*\d+\s*章\s*.*$',
    r'^\d+\s*[·•・]\s*.*$',
]

# ==================== 特定类型小说的额外模式 ====================

FANTASY_PATTERNS = [
    (r'^卷\s*([零一二三四五六七八九十百千万\d]+)\s*(.*)$', 'volume'),
    (r'^第\s*([零一二三四五六七八九十百千万\d]+)\s*卷\s*(.*)$', 'chinese_volume'),
]

FANTASY_NEXT_PATTERNS = [
    r'^卷[零一二三四五六七八九十百千万\d]+\s*.*$',
    r'^第[零一二三四五六七八九十百千万\d]+卷\s*.*$',
]

DETECTIVE_PATTERNS = [
    (r'^[第]?([零一二三四五六七八九十百千万\d]+)部分[：:]\s*(.*)$', 'part'),
    (r'^[第]?([零一二三四五六七八九十百千万\d]+)节[：:]\s*(.*)$', 'section'),
]

# ==================== 过滤规则 ====================

def filter_percent(title_part: str, **kwargs) -> bool:
    return title_part.startswith('%')

def filter_dialogue(title_part: str, **kwargs) -> bool:
    return title_part.startswith('：') or title_part.startswith(':')

def filter_question(title_part: str, **kwargs) -> bool:
    if '？' not in title_part and '?' not in title_part:
        return False
    return any(title_part.startswith(p) for p in
               ['为什么', '既然', '怎么', '如何', '什么', '谁', '何时', '何地'])

def filter_update_notice(title_part: str, **kwargs) -> bool:
    return '更新' in title_part or '日~' in title_part or '（周' in title_part

def filter_content_fragment(title_part: str, **kwargs) -> bool:
    return title_part.startswith('了，') or title_part.startswith('的，')

def filter_countdown(title_part: str, ptype: str = None, chapter_match=None, **kwargs) -> bool:
    if ptype not in ('simple_number', 'number_title_combined') or not chapter_match:
        return False
    cleaned = title_part.lstrip('、，,．.')
    if cleaned[:1] not in '12345':
        return False
    try:
        return int(chapter_match.group(1)) - int(cleaned[0]) == 1
    except (ValueError, IndexError):
        return False

def filter_repeat_chapter(chapter_num: int = None, seen_chapter_nums: set = None, **kwargs) -> bool:
    if chapter_num is None or seen_chapter_nums is None:
        return False
    return chapter_num in seen_chapter_nums

def filter_zero_chapter(chapter_match=None, ptype: str = None, **kwargs) -> bool:
    """过滤第0章及游戏数据行"""
    if not chapter_match or ptype != 'simple_number':
        return False
    try:
        chapter_num = int(chapter_match.group(1))
        if chapter_num != 0:
            return False
        title_part = chapter_match.group(2).strip() if chapter_match.lastindex >= 2 else ''
        if '、' in title_part:
            parts = title_part.split('、')
            if len(parts) >= 3 and all(p.isdigit() or (p.endswith('。') and p[:-1].isdigit()) for p in parts):
                return True
        return True
    except (ValueError, IndexError):
        return False

def filter_description_lines(chapter_match=None, ptype: str = None, **kwargs) -> bool:
    """过滤文案描述行（如1、1v1，xxx）"""
    if not chapter_match or ptype != 'simple_number':
        return False
    try:
        title_part = chapter_match.group(2).strip() if chapter_match.lastindex >= 2 else ''
        if title_part.startswith('第'):
            return False
        keywords = ('1v1', 'he', 'be', 'np', '攻', '受', '攻受', '主角',
                    '慎入', '避雷', '注意', '警告', '标签：', '文案：', '简介：')
        return len(title_part) < 100 and any(k in title_part for k in keywords)
    except (ValueError, IndexError):
        return False

DEFAULT_FILTER_RULES = [
    {'name': 'percent', 'func': filter_percent},
    {'name': 'dialogue', 'func': filter_dialogue},
    {'name': 'question', 'func': filter_question},
    {'name': 'update_notice', 'func': filter_update_notice},
    {'name': 'content_fragment', 'func': filter_content_fragment},
    {'name': 'countdown', 'func': filter_countdown},
    {'name': 'repeat_chapter', 'func': filter_repeat_chapter},
    {'name': 'zero_chapter', 'func': filter_zero_chapter},
    {'name': 'description_lines', 'func': filter_description_lines},
]

BL_SPECIFIC_FILTERS = [
    {'name': 'bl_special', 'func': lambda title_part, **kw: '攻' in title_part and '受' in title_part and len(title_part) < 10},
]
