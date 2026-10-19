# TXT 优化器与 EPUB 转换器

模块化 Python 脚本，用于优化 TXT 小说文件并转换为 EPUB 格式。提供 **Web 界面**（推荐）和命令行两种使用方式。

## 功能特性

### 🌐 Web 界面（v2.8）

- FastAPI + 浏览器，无需安装 tkinter，macOS/Windows/Linux 通用
- 深色 / 浅色主题切换，偏好持久化
- 实时日志流（SSE），关闭浏览器标签自动退出服务
- 文件选择自动提取书名/作者，显示「自动识别」标签
- Toast 通知、动画进度条、导航徽标
- **自定义章节识别规则**（章节规则 Tab）：添加/启用/禁用自定义正则，高于内置规则优先匹配
- **广告过滤规则**（广告规则 Tab）：可调整关键词列表与评分阈值
- **广告扫描（预览模式）**（广告规则 Tab 顶部扫描面板）：扫描但不删除内容，以彩色得分表格展示可疑行（≥0.85 红 / ≥0.70 橙）
- **EPUB 排版自定义**（生成 EPUB 标签页「排版样式」可折叠面板）：页面边距、行间距、首行缩进、自定义 CSS 文本框
- **EPUB 编辑器**（v2.8，独立 Tab）：加载已有 EPUB 或 TXT 文件，对章节进行增删改、合并、查找替换、元数据编辑，再重建为 EPUB

### TXT 文件优化

- 自动检测文件编码（支持 UTF-8、GBK、GB2312 等）
- 标准化章节标题格式
- **广告内容过滤**（URL、下载引导、平台推广等）
- **独立行水印清理**（读者 ID、转载者署名）
- **多书合并检测**：相邻章节人名/地名完全不重叠时自动停止并提示
- 段落合并、去重

### EPUB 生成

- 自动解析章节结构、提取书名和作者
- **保留文案简介**作为独立章节
- **目录分页与分卷嵌套**：章节数 > 20 时自动拆分为「目录」「目录（续1）」等多页；自动检测「第X卷」等分卷标题，EPUB NCX 目录生成卷→章两级嵌套结构
- **手动卷分配**：通过 `volume_map` 参数将任意章节指定到卷中
- 支持本地封面 / 在线 URL / 自动搜索（晋江、豆瓣、微信读书、长佩、Bing 五源）
- **封面候选预览弹窗**（Web UI）：缩略图网格，来源标注，置信度色标
- **内嵌章节编辑**（Web UI 生成 EPUB 标签页）：修改标题/编号、调整顺序、删除章节，保存后自动更新转换路径
- **作者有话要说子章节**：章节末尾如含「作者有话说/作者有话要说」段落，自动在 EPUB 目录中生成嵌套子条目
- **`*` 场景分隔符**：单独的 `*` / `＊` 行作为场景分隔保留，不与下一段合并
- **样式预设引擎**：内置双引号/角括号/单引号对话规则，支持 inline span（`<span class="dlg-cn">` 等）和 block 整段 class 两种作用域；可通过 `/api/style/presets` API 自定义
- **脚注系统**：正文中 `{{注:内容}}` 标记自动转换为 EPUB footnote（`<aside epub:type="footnote">`）
- **头图处理**（需 Pillow）：为每章插入带边缘蒙版的头图（fade/cloud/mist/torn/rough 等多种效果），按章节轮换
- **字体子集化**（需 fontTools）：按全书字符集裁剪内嵌字体，将体积从 10MB+ 压缩到几百 KB；支持 body/title/dlg/toc 四个角色分别指定字体
- **插图页**：在指定章节后插入全版面图片页，支持标题注释
- **同名章节自动合并**：自动合并网络抓取断点导致的相邻重复章节，根据末尾标点智能选择拼接方式
- **扩展元数据**：description（简介）、publisher（出版社）、isbn、pubdate、language、tags
- **重新分章**（`/api/resplit`）：支持临时注入自定义正则预览分章结果，dry_run 模式不写文件

### EPUB 编辑器（v2.8）

基于有状态会话（内存 `_SESSION`）的 EPUB 编辑工作流：

1. **加载**（`POST /api/editor/load`）：读取 `.epub` 文件（解析回章节/元数据）或 `.txt` 文件（直接解析章节）
2. **编辑**：章节 CRUD（GET/PUT/DELETE）、合并章节、元数据更新、全文查找/替换
3. **构建**（`POST /api/editor/build`）：从当前会话状态重新生成 EPUB，支持所有排版参数
4. **持久化**：`POST /api/editor/save-session` 保存到 `~/.txt2epub/editor_session.json`

### 章节识别支持

| 格式 | 示例 |
| ------ | ------ |
| 标准格式 | `第1章 标题` / `第一章 标题` |
| 等号分隔 | `==第1章 标题==` |
| 数字序号 | `1、第一章 标题` |
| 特殊章节 | `楔子` / `番外` / `终章` |
| 英文格式 | `Chapter 1` |
| **自定义正则** | 用户在 Web UI 章节规则 Tab 中配置 |

---

## 项目结构

```text
txt-convert/
├── adfilter.py            # 广告过滤模块
├── chapter.py             # 章节识别模块
├── chapter_config.py      # 章节规则配置
├── chapter_numberer.py    # 章节编号处理
├── clean_rules.py         # 清洗规则定义
├── config.py              # 全局配置
├── consistency.py         # 多书合并检测
├── cover.py               # 封面管理（五源搜索：晋江/豆瓣/微信读书/长佩/Bing）
├── cover_picker_dialog.py # 封面候选预览（桌面 GUI）
├── display.py             # 显示工具
├── easypub.py             # EasyPub 格式导出
├── encoding.py            # 编码检测
├── epub.py                # EPUB 生成 + EPUB 解析（parse_epub）
├── font_subset.py         # 字体子集化（fontTools）
├── gui.py                 # 桌面 GUI 主程序（已归并到 Web UI）
├── gui/                   # 桌面 GUI 组件
├── header_image.py        # 头图边缘蒙版处理（Pillow）
├── namecleaner.py         # 水印/署名清理
├── txt_optimizer.py       # TXT 优化主模块
├── web_server.py          # FastAPI Web 服务 + EPUB 编辑器 API
├── static/
│   └── index.html         # Web UI 前端
└── requirements.txt
```

---

## 安装依赖

```bash
pip install -r txt-convert/requirements.txt
```

主要依赖：`fastapi`、`uvicorn`、`ebooklib`、`chardet`、`requests`。

可选增强：`Pillow`（头图处理）、`fontTools`（字体子集化）。

---

## 快速开始

**Web 界面（推荐）：**

```bash
cd txt-convert
python3 web_server.py
# 浏览器自动打开 http://127.0.0.1:8765
```

**命令行：**

```bash
# 生成 EPUB
python3 txt-convert/epub.py input.txt

# 优化 TXT
python3 txt-convert/txt_optimizer.py input.txt
```

---

## Web UI 功能说明

**单文件转换**：选择 TXT 文件后自动识别书名/作者，点击「▶ 开始转换」。

**批量转换**：选择文件夹，批量处理所有 TXT 文件，结果以表格展示（文件名/状态/章节数/大小）。

**生成 EPUB**：封面选项包括无封面 / 本地图片 / 图片 URL / 自动搜索（含五源封面候选预览弹窗）。选择文件后自动分析章节，内嵌章节编辑区域。「排版样式」可折叠面板提供页面边距（窄/标准/宽/超宽）、行间距（1.5–2.2）、首行缩进（0/1/2/2.5em）选项及自定义 CSS 文本框。

**EPUB 编辑器（v2.8）**：独立 Tab。加载任意 EPUB 或 TXT 文件进入编辑会话，对章节标题/正文进行修改、合并重复章节、删除章节、全文查找替换、修改元数据（书名/作者/简介等），编辑完成后一键重建为新 EPUB。会话可保存/恢复。

**章节规则**：添加自定义正则（group 1 = 章节号，group 2 = 标题），启用/禁用单条规则，优先级高于内置规则。规则持久化到 `~/.txt2epub/chapter_rules.json`。

**广告规则**：调整硬关键词、软关键词和匹配阈值，持久化到 `~/.txt2epub/adfilter_rules.json`。标签页顶部「扫描广告（预览，不删除）」面板：选择文件后点击「扫描」，以彩色得分表格展示可疑行。

**目录查看**：独立加载 TXT 文件，查看、编辑、重排章节，统计信息（章节数/总行数/总字数），保存为 `*_edited.txt`。
