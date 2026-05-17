"""章节识别配置文件

支持针对不同小说类型配置不同的过滤规则和章节格式模式。
"""

import re
from typing import List, Dict, Callable, Any


class ChapterConfig:
    """章节识别配置类"""

    def __init__(self, config_name: str = 'default'):
        self.config_name = config_name
        self.load_config(config_name)

    def load_config(self, config_name: str):
        """加载指定的配置"""
        configs = self._get_all_configs()
        if config_name in configs:
            config = configs[config_name]
            self.CHAPTER_PATTERNS = config.get('chapter_patterns', [])
            self.NEXT_CHAPTER_PATTERNS = config.get('next_chapter_patterns', [])
            self.FILTER_RULES = config.get('filter_rules', [])
        else:
            # 使用默认配置
            self.CHAPTER_PATTERNS = DEFAULT_CHAPTER_PATTERNS
            self.NEXT_CHAPTER_PATTERNS = DEFAULT_NEXT_CHAPTER_PATTERNS
            self.FILTER_RULES = DEFAULT_FILTER_RULES

    def _get_all_configs(self) -> Dict[str, Dict]:
        """获取所有可用配置"""
        return {
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

    def get_config_names(self) -> List[str]:
        """获取所有可用配置名称"""
        return list(self._get_all_configs().keys())


# ==================== 默认章节格式模式 ====================

DEFAULT_CHAPTER_PATTERNS = [
    # (正则表达式, 模式名称)
    (r'^[=]+第\s*(\d+)\s*章\s*(.*?)[=]*$', 'equals'),           # =====第X章=====
    (r'^第\s*([零一二三四五六七八九十百千万\d]+)\s*章\s*(.*)$', 'chinese'),    # 第X章 标题
    (r'^\d+、第([零一二三四五六七八九十百千万\d]+)章\s*(.*)$', 'number_chinese'), # 1、第X章 标题
    (r'^\d+、番外(.*)$', 'number_fanwai'),                    # 1、番外标题
    (r'^番外([零一二三四五六七八九十百千万\d]+)(.*)$', 'fanwai'),            # 番外X标题
    (r'^(\d+)、(.*)$', 'simple_number'),                      # 1、标题
    (r'^(\d+)\.?\s*(.+)$', 'number_title_combined'),         # 1. 标题 或 1 标题
    (r'^楔子\s*(.*)$', 'xiezi'),                              # 楔子
    (r'^[◇◆\*•·]\s*第(\d+)章\s*(.*)$', 'special_prefix'),      # ◇第X章 标题
    (r'^第([零一二三四五六七八九十百千万]+)案[：:]\s*(.*)$', 'case_volume'),   # 第一案：标题
    (r'^\[(\d+)\](.*)$', 'bracket_number'),                   # [1]标题
    (r'^(\d+)$', 'standalone_number'),                        # 单独数字
]

DEFAULT_NEXT_CHAPTER_PATTERNS = [
    r'^[=]+第\s*\d+\s*章\s*.*[=]*$',
    r'^第[零一二三四五六七八九十百千万\d]+章\s*.*$',
    r'^\d+、[零一二三四五六七八九十百千万\d]+章\s*.*$',
    r'^(攻)?第[零一二三四五六七八九十百千万\d]+章\s*.*$',
]

# ==================== 特定类型小说的额外模式 ====================

# 奇幻小说特有模式
FANTASY_PATTERNS = [
    (r'^卷\s*([零一二三四五六七八九十百千万\d]+)\s*(.*)$', 'volume'),         # 卷X 标题
    (r'^第\s*([零一二三四五六七八九十百千万\d]+)\s*卷\s*(.*)$', 'chinese_volume'), # 第X卷 标题
]

FANTASY_NEXT_PATTERNS = [
    r'^卷[零一二三四五六七八九十百千万\d]+\s*.*$',
    r'^第[零一二三四五六七八九十百千万\d]+卷\s*.*$',
]

# 推理小说特有模式
DETECTIVE_PATTERNS = [
    (r'^[第]?([零一二三四五六七八九十百千万\d]+)部分[：:]\s*(.*)$', 'part'),   # 第一部分：标题
    (r'^[第]?([零一二三四五六七八九十百千万\d]+)节[：:]\s*(.*)$', 'section'),   # 第一节：标题
]

# ==================== 过滤规则 ====================

def filter_percent(title_part: str, **kwargs) -> bool:
    """过滤百分比格式（如25%、99%的玩家）"""
    return title_part.startswith('%')

def filter_dialogue(title_part: str, **kwargs) -> bool:
    """过滤对话格式（如：正义的毒雾）"""
    return title_part.startswith('：') or title_part.startswith(':')

def filter_question(title_part: str, **kwargs) -> bool:
    """过滤问题格式（如为什么、既然、怎么...）"""
    if '？' in title_part or '?' in title_part:
        question_prefixes = ['为什么', '既然', '怎么', '如何', '什么', '谁', '何时', '何地']
        return any(title_part.startswith(prefix) for prefix in question_prefixes)
    return False

def filter_update_notice(title_part: str, **kwargs) -> bool:
    """过滤更新公告（包含更新时间信息）"""
    return '更新' in title_part or '日~' in title_part or '（周' in title_part

def filter_content_fragment(title_part: str, **kwargs) -> bool:
    """过滤内容片段（如"了，"开头）"""
    return title_part.startswith('了，') or title_part.startswith('的，')

def filter_countdown(title_part: str, ptype: str = None, chapter_match=None, **kwargs) -> bool:
    """过滤倒计时格式（如6、5……）"""
    if ptype not in ['simple_number', 'number_title_combined']:
        return False
    if not chapter_match:
        return False
    cleaned_title = title_part.lstrip('、，,．.')
    if cleaned_title.startswith('5') or cleaned_title.startswith('4') or \
       cleaned_title.startswith('3') or cleaned_title.startswith('2') or cleaned_title.startswith('1'):
        try:
            chapter_num_int = int(chapter_match.group(1))
            return chapter_num_int - int(cleaned_title[0]) == 1
        except:
            return False
    return False

def filter_repeat_chapter(chapter_num: int = None, seen_chapter_nums: set = None, **kwargs) -> bool:
    """过滤重复章节号"""
    if chapter_num is None or seen_chapter_nums is None:
        return False
    return chapter_num in seen_chapter_nums

def filter_zero_chapter(chapter_match=None, ptype: str = None, **kwargs) -> bool:
    """过滤第0章（通常不是有效章节）"""
    if not chapter_match:
        return False
    try:
        if ptype == 'simple_number':
            chapter_num = int(chapter_match.group(1))
            if chapter_num == 0:
                # 检查标题是否包含多个数字用顿号分隔的模式（如01、36、35）
                title_part = chapter_match.group(2).strip() if chapter_match.lastindex >= 2 else ''
                if '、' in title_part:
                    parts = title_part.split('、')
                    # 如果有多个数字用顿号分隔，很可能是游戏数据或其他内容
                    if len(parts) >= 3 and all(p.isdigit() or (p.endswith('。') and p[:-1].isdigit()) for p in parts):
                        return True
            return chapter_num == 0
    except:
        return False
    return False

def filter_description_lines(chapter_match=None, ptype: str = None, **kwargs) -> bool:
    """过滤文案描述行（如1、1v1，xxx；2、攻xxx等格式）"""
    if not chapter_match or ptype != 'simple_number':
        return False
    try:
        title_part = chapter_match.group(2).strip() if chapter_match.lastindex >= 2 else ''
        
        # 如果标题部分以'第'开头，说明这是真正的章节标题，让其他模式处理（不过滤）
        if title_part.startswith('第'):
            return False
        
        # 检查是否是文案描述格式
        description_patterns = [
            # 常见的文案标签
            '1v1', 'he', 'be', 'np',
            # 攻受描述
            '攻', '受', '攻受', '主角', '主角攻', '主角受',
            # 情节警告
            '慎入', '避雷', '注意', '警告',
            # 标签格式
            '标签：', '文案：', '简介：',
            # CP描述
            'x', '×', '×', '和', '与', '攻x受', '受x攻',
        ]
        # 如果标题包含这些关键词且长度较短，很可能是文案描述
        if len(title_part) < 100 and any(pattern in title_part for pattern in description_patterns):
            return True
        return False
    except:
        return False

# 默认过滤规则
DEFAULT_FILTER_RULES = [
    {'name': 'percent', 'func': filter_percent, 'description': '过滤百分比格式'},
    {'name': 'dialogue', 'func': filter_dialogue, 'description': '过滤对话格式'},
    {'name': 'question', 'func': filter_question, 'description': '过滤问题格式'},
    {'name': 'update_notice', 'func': filter_update_notice, 'description': '过滤更新公告'},
    {'name': 'content_fragment', 'func': filter_content_fragment, 'description': '过滤内容片段'},
    {'name': 'countdown', 'func': filter_countdown, 'description': '过滤倒计时格式'},
    {'name': 'repeat_chapter', 'func': filter_repeat_chapter, 'description': '过滤重复章节'},
    {'name': 'zero_chapter', 'func': filter_zero_chapter, 'description': '过滤第0章'},
    {'name': 'description_lines', 'func': filter_description_lines, 'description': '过滤文案描述行'},
]

# BL小说特有过滤规则
BL_SPECIFIC_FILTERS = [
    # BL小说可能有更多特殊格式需要过滤
    {'name': 'bl_special', 'func': lambda title_part, **kwargs: '攻' in title_part and '受' in title_part and len(title_part) < 10, 
     'description': '过滤BL特殊标记'},
]

# ==================== 全局配置实例 ====================

# 创建默认配置实例
default_config = ChapterConfig('default')

# 创建不同类型的配置实例
bl_config = ChapterConfig('bl')
fantasy_config = ChapterConfig('fantasy')
detective_config = ChapterConfig('detective')
