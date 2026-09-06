# TXT 优化器与 EPUB 转换器

模块化 Python 脚本，用于优化 TXT 小说文件并转换为 EPUB 格式。提供 **Web 界面**（推荐）和命令行两种使用方式。

## 功能特性

### 🌐 Web 界面（v2.3）

- FastAPI + 浏览器，无需安装 tkinter，macOS/Windows/Linux 通用
- 深色 / 浅色主题切换，偏好持久化
- 实时日志流（SSE），关闭浏览器标签自动退出服务
- 文件选择自动提取书名/作者，显示「自动识别」标签
- Toast 通知、动画进度条、导航徽标

### 🖥️ 桌面 GUI（v2.1）

- CustomTkinter 现代化侧边栏导航，可视化操作
- 命令行模式：批量处理、自动化脚本

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
- **自动生成目录页**（含章节超链接）
- 支持本地封面 / 在线 URL / 自动搜索（晋江、豆瓣等平台）
- 封面候选选择对话框：缩略图网格，置信度标注

### 章节识别支持

| 格式 | 示例 |
| ------ | ------ |
| 标准格式 | `第1章 标题` / `第一章 标题` |
| 等号分隔 | `==第1章 标题==` |
| 数字序号 | `1、第一章 标题` |
| 特殊章节 | `楔子` / `番外` / `终章` |
| 英文格式 | `Chapter 1` |

---

## 项目结构

```text
txt-convert/
├── web_server.py             # Web UI 服务器（FastAPI + uvicorn）
├── static/
│   └── index.html            # 浏览器界面（Tailwind + Alpine.js）
├── txt_optimizer.py          # CLI 主入口
├── gui.py                    # GUI 兼容入口（→ gui/ 包）
├── config.py                 # 配置持久化
├── encoding.py               # 编码检测
├── chapter.py                # 章节分析（bisect 优化，O(n log n)）
├── chapter_config.py         # 章节识别配置
├── chapter_numberer.py       # 章节连续编号
├── clean_rules.py            # 清洗规则
├── adfilter.py               # 广告内容过滤
├── namecleaner.py            # 独立行水印清理
├── consistency.py            # 跨章节内容一致性检测
├── display.py                # 目录显示
├── cover.py                  # 封面下载（多候选架构）
├── cover_picker_dialog.py    # 封面候选选择对话框
├── easypub.py                # EasyPub 优化流程
├── epub.py                   # EPUB 生成
└── gui/                      # GUI 包
    ├── app.py                # 主窗口（左侧导航栏 + 页面切换）
    ├── constants.py          # 全局常量
    ├── theme.py              # 主题样式
    ├── log_panel.py          # 日志重定向
    ├── task_runner.py        # 后台任务
    ├── settings_dialog.py    # 设置对话框
    └── tabs/
        ├── base_tab.py
        ├── convert_tab.py
        ├── batch_tab.py
        ├── epub_tab.py
        └── catalog_tab.py
```

---

## 安装依赖

```bash
# Web UI（推荐）
pip3 install fastapi "uvicorn[standard]"

# EPUB 生成 + 封面下载 + 桌面 GUI
pip3 install ebooklib pillow requests sv-ttk
```

---

## 快速开始

### 🌐 启动 Web 界面（推荐）

```bash
cd txt-convert
python3 web_server.py
# 自动打开 http://127.0.0.1:8765
# 关闭浏览器标签后服务自动退出
```

### 🖥️ 启动桌面 GUI

```bash
cd txt-convert
python3 gui.py
```

### 💻 命令行

```bash
# 优化单个文件
python3 txt_optimizer.py novel.txt

# 指定输出路径
python3 txt_optimizer.py novel.txt -o novel_clean.txt
```

---

## Web UI 功能说明

**单文件转换**：选择 TXT 文件后自动识别书名/作者（字段旁显示「自动识别」标签），点击「▶ 开始转换」。

**批量转换**：选择文件夹，批量处理所有 TXT 文件，结果以表格展示（文件名/状态/章节数/大小）。

**生成 EPUB**：封面选项包括无封面 / 本地图片 / 图片 URL / 自动搜索。生成的 EPUB 结构：文案简介 → 目录页 → 各章节正文。

**目录查看**：加载 TXT 文件，查看识别出的章节列表和统计信息（章节数/总行数/总字数）。

---

## 文本清洗流程

```text
原始 TXT 文件
      │
      ▼  AdFilter           广告行过滤（URL / 下载引导 / 平台推广）
      ▼  NameCleaner        独立行水印清理（读者 ID / 转载署名）
      ▼  ChapterAnalyzer    章节结构分析
      ▼  ConsistencyChecker 多书合并检测 → 不一致时停止并提示
      ▼  EasyPubOptimizer   标题标准化 / 段落合并
      │
      ▼  *_epub_ready.txt
      │
      ▼  EPUBGenerator
         ├── 文案简介章节
         ├── 目录章节（超链接）
         └── 正文各章
      │
      ▼  .epub 文件
```

---

## 多书合并检测

当相邻章节的人名/地名实体**完全不重叠**（连续 2 章）时，自动停止并输出诊断：

```text
⛔  检测到内容不连续
   断裂位置：「第214章 决战」→「第215章 太古圣体」
   前段出现：萧炎、纳兰嫣然、迦南学院、天焰山
   后段出现：叶凡、姜焕、圣体殿、太古神山
   疑似多部小说合并文件，已停止处理。
   建议在「第214章 决战」末尾处手动拆分文件后重新运行。
```

如需强制继续：`convert_for_easypub(..., ignore_mismatch=True)`

---

## 封面搜索来源

| 来源 | 方式 | 状态 |
| ------ | ------ | ------ |
| 晋江文学城 | JSON API → 详情页 | ✅ 可用 |
| 豆瓣读书 | `j/subject_suggest` JSON 接口 | ✅ 可用 |
| 长佩文学 | SPA 页面解析 | ⚠️ 骨架（反爬严格） |
| Bing 图片 | `mediaurl=` 正则提取 | ⚠️ 兜底备选 |

---

## 支持的平台

- macOS ✓
- Windows ✓
- Linux ✓

---

详细修改记录见 [CHANGELOG_v2.0.md](CHANGELOG_v2.0.md)。
