# txt-convert 设计文档

> 当前版本：**v2.5**  最后更新：2026-09-28

---

## 1. 项目概述

将网络小说 TXT 文件处理为干净的 EPUB 电子书。提供三种入口：

| 入口 | 文件 | 说明 |
|------|------|------|
| Web UI（推荐） | `web_server.py` | FastAPI + Tailwind + Alpine.js，端口 8765 |
| 桌面 GUI | `gui.py` → `gui/` | CustomTkinter，macOS/Windows/Linux |
| 命令行 | `txt_optimizer.py` | 批量/自动化脚本 |

---

## 2. 整体数据流

```
原始 TXT
  │
  ▼  EncodingDetector         自动检测编码（UTF-8/GBK/GB2312…）
  ▼  AdFilter                 广告行过滤（URL / 下载引导 / 平台推广）
  ▼  NameCleaner              独立行水印清理（读者ID / 转载署名）
  ▼  ChapterAnalyzer          三遍扫描章节结构（候选 → 过滤作者Note → 去重）
  ▼  ConsistencyChecker       多书合并检测（累积实体池，连续3章零重叠则报错）
  ▼  EasyPubOptimizer         标题标准化 / 段落合并 / 场景分隔符处理
  │
  ▼  *_epub_ready.txt
  │
  ▼  EPUBGenerator
     ├─ 文案简介章节（前言）
     ├─ 目录章节（超链接）
     └─ 各章节正文（含「作者有话要说」嵌套子节）
  │
  ▼  .epub 文件
```

主入口函数：`easypub.py::convert_for_easypub()`

---

## 3. 模块说明

### 3.1 `encoding.py` — EncodingDetector

- 依次尝试 UTF-8-BOM → UTF-8 → GBK → GB2312 → chardet 检测
- 返回 `(content: str, encoding: str)`

### 3.2 `adfilter.py` — AdFilter

- **硬关键词**：命中即过滤（URL、下载链接等）
- **软关键词**：累积评分，超阈值（默认 0.68）才过滤
- 规则持久化：`~/.txt2epub/adfilter_rules.json`
- Web API：`GET/POST /api/adfilter/rules`

### 3.3 `namecleaner.py` — NameCleaner

- 识别并清除独立行水印（单行读者 ID、"转自 xxx"等）
- 返回 `(cleaned_content, count, list_of_removed)`

### 3.4 `chapter.py` — ChapterAnalyzer

三遍扫描，O(n log n)（bisect）：

1. **第一遍**：逐行匹配所有章节格式正则（来自 `chapter_config.py`），收集候选
2. **第二遍**：过滤落在「作者有话要说」区域内的假标题
3. **第三遍**：按章节号去重，用 bisect 计算每章 `end_line`

返回值结构：
```python
{
  'total_chapters': int,
  'total_lines': int,
  'total_chars': int,
  'chapters': [
    {
      'number': int,       # 章节编号（番外≥999）
      'title': str,        # 含编号的完整标题
      'start_line': int,   # 1-based
      'end_line': int,     # 1-based，含
      'line_count': int,
      'char_count': int,
    }, ...
  ]
}
```

### 3.5 `chapter_config.py` — ChapterConfig

- 内置 16 种格式正则（标准章 / 番外 / 楔子 / 完结章 / 等号分隔…）
- 用户自定义规则：`~/.txt2epub/chapter_rules.json`，ptype = `'custom'`，**前置**于内置列表（更高优先级）
- Web API：`GET/POST /api/chapter/rules`
- `_STANDARD` 字典定义每种 ptype 的 group 映射：`(章节号group, 标题group, 单位, 是否中文数字)`

### 3.6 `consistency.py` — ConsistencyChecker

**目的**：检测多本小说被合并成一个 TXT 文件的情况。

**算法**（累积实体池，v2.5 改为此方式）：

1. 对每章提取人名/地名实体集（`_extract_entities`）
2. 维护 `cumulative_pool`（所有已处理章节的并集）
3. 当前章与 `cumulative_pool` 无交集：`zero_streak += 1`
4. 连续 `confirm_n`（默认 3）章零重叠 → 报错

**NER 三条正则**：

| 正则 | 捕获目标 | 关键约束 |
|------|----------|----------|
| `_ACTION_RE` | 动作动词前的人名（2-3 字） | 孤立 `道` 必须后跟引号/冒号，避免误匹配「知道」 |
| `_QUOTE_RE` | 引号/冒号前的人名（2-3 字） | 后接中文字符确认是引语 |
| `_PLACE_RE` | 常见地点后缀词（1-4 字前缀） | 城/国/山/河/殿/宫/门/村… 共 22 种后缀 |

**过滤层**：
- `_BAD_STARTS`：以功能词开头的捕获直接丢弃（不/没/他/她/这/那/一/些/了/们/偶…）
- `_PHRASE_CHARS`：含 `了` 或 `的` 的捕获视为语法短语而非实体

失败时抛 `ContentMismatchError`；Web 端返回 HTTP 422。

可通过 `ignore_mismatch=True` 跳过检测。

### 3.7 `easypub.py` — EasyPubOptimizer / convert_for_easypub

**`optimize_for_epub()`** 主要处理：
- 章节标题标准化（统一为 `第N章 标题` 格式）
- 段落合并：连续非空行拼成一段，分隔条件为空行或章节标题
- 对话拆行修复：`EPUBGenerator._merge_dialogue_splits()` 合并被换行拆开的引语
- **场景分隔符**：`^[\*＊·•\s]+$` 且 ≤5 字符的行保留为独立段落（`<p class="scene-break">`），不与下一段合并

**`convert_for_easypub()`** 完整流程签名：
```python
convert_for_easypub(
    input_file: str,
    output_file: str = None,
    book_title: str = "",
    author: str = "",
    show_catalog: bool = True,
    ignore_mismatch: bool = False,
    filter_ads: bool = True,
    ad_rules: dict = None,
) -> Tuple[Optional[str], Optional[Dict]]
```

### 3.8 `epub.py` — EPUBGenerator

**`txt_to_epub()`** 处理步骤：
1. 读文件 → `_extract_title()` / `_extract_author()` 自动提取元数据
2. `_parse_chapters()` 解析章节（调用 ChapterAnalyzer）
3. 前言/文案简介 → 目录页（带超链接）→ 各章节
4. 每章调用 `_split_author_note()` 拆出「作者有话说」子节
5. HTML 模板写入 `epub_chapter.content`（**必须 `.encode('utf-8')` 为 bytes**，否则 lxml 抛 ValueError 被 ebooklib 静默吞掉导致空章节）

**关键注意事项**：
- `epub_chapter.content` 类型必须是 `bytes`，不能是 `str`（XML 声明与 lxml HTMLParser 不兼容）
- 特殊章节（目录页）用 `{'title': '...', '_html': '...'}` 跳过正常 `_chapter_to_html()` 渲染
- CSS 内嵌于 `_EPUB_CSS` 字符串常量，字体栈：思源宋体 → STSong → SimSun

### 3.9 `web_server.py` — FastAPI 服务

**端口**：8765，启动后自动打开浏览器

**自动退出机制**：SSE 连接断开后 4 秒内无新连接，调用 `os.kill(os.getpid(), signal.SIGINT)`

**API 一览**：

| Method | Path | 说明 |
|--------|------|------|
| GET | `/` | 返回 `static/index.html` |
| GET | `/api/logs/stream` | SSE 实时日志流 |
| POST | `/api/dialog` | 打开系统文件对话框 |
| GET | `/api/recent` | 最近使用文件列表 |
| POST | `/api/extract-meta` | 从 TXT 提取书名/作者 |
| POST | `/api/convert` | 优化 TXT（单文件） |
| POST | `/api/batch` | 批量优化 |
| POST | `/api/epub` | 生成 EPUB |
| POST | `/api/catalog/analyze` | 分析章节目录 |
| POST | `/api/catalog/save` | 保存编辑后的章节目录 |
| GET/POST | `/api/adfilter/rules` | 广告过滤规则 |
| GET/POST | `/api/chapter/rules` | 章节识别自定义规则 |
| POST | `/api/open-file` | 在系统文件管理器中显示文件 |
| POST | `/api/epub/search-covers` | 搜索封面候选 |
| GET | `/api/cover-proxy` | 封面图片反代（绕过 CORS） |

`ContentMismatchError` → HTTP 422，响应体含断裂位置和实体样本。

### 3.10 `static/index.html` — 前端

- **技术栈**：Tailwind CSS CDN + Alpine.js，单文件，无构建步骤
- **主题**：CSS 变量 + `body[data-theme="light"]` 切换，偏好存 localStorage
- **标签页**：单文件转换 / 批量转换 / 生成 EPUB / 广告规则 / 章节规则 / 目录编辑
- **封面候选预览**：弹窗网格，缩略图 + 来源标注 + 置信度色标
- **章节内嵌编辑**（EPUB Tab）：修改标题/编号、上移/下移、删除，保存为新文件后自动切换路径
- **EPUB Tab 章节编辑保存逻辑**：保存后端点 `POST /api/catalog/save`，返回新路径，前端 `epubFile` 字段自动更新

---

## 4. 配置文件

| 文件 | 说明 |
|------|------|
| `~/.txt2epub/config.json` | 通用偏好（主题、最近文件等） |
| `~/.txt2epub/adfilter_rules.json` | 广告过滤规则（硬关键词/软关键词/阈值） |
| `~/.txt2epub/chapter_rules.json` | 用户自定义章节正则（格式见下） |

`chapter_rules.json` 格式：
```json
{
  "patterns": [
    { "pattern": "^第(\\d+)回\\s*(.*)$", "enabled": true },
    { "pattern": "^回\\s*(\\d+)\\s+(.*)$", "enabled": false }
  ]
}
```
group 1 = 章节号（阿拉伯数字），group 2 = 章节标题。

---

## 5. 封面搜索

| 来源 | 方式 | 状态 |
|------|------|------|
| 晋江文学城 | JSON API → 详情页 | ✅ |
| 豆瓣读书 | `j/subject_suggest` JSON | ✅ |
| 长佩文学 | SPA 页面解析 | ⚠️ 骨架（反爬严格） |
| Bing 图片 | `mediaurl=` 正则提取 | ⚠️ 兜底备选 |

---

## 6. 已知边界情况

| 场景 | 处理方式 |
|------|----------|
| 第 1-70 章无标题，第 71+ 章有标题 | ChapterAnalyzer 正常识别；EasyPubOptimizer 标准化时无标题则只输出 `第N章` |
| 番外章节角色与正文不同 | ConsistencyChecker 用累积池（含正文全部实体），不会误判 |
| 章节末尾「作者有话说」含章节编号 | ChapterAnalyzer 第二遍扫描排除作者Note区域内的候选行 |
| `epub_chapter.content` 传 str | lxml 抛 ValueError，ebooklib 静默返回 `b""`，导致 EPUB 所有章节空白——必须传 bytes |
| 对话被换行拆开（`说："` + 换行 + `"xxx"`） | `_merge_dialogue_splits()` 在生成 HTML 前合并 |
