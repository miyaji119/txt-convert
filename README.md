# TXT 优化器与 EPUB 转换器

模块化 Python 脚本，用于优化 TXT 小说文件并转换为 EPUB 格式。

## 功能特性

### TXT 文件优化
- 自动检测文件编码（支持 UTF-8、GBK、GB2312 等）
- 标准化章节标题格式
- 智能段落合并与分隔
- 支持多种章节格式识别

### EPUB 生成
- 自动解析章节标题
- 提取小说标题和作者信息
- 支持自定义封面图片
- 自动搜索网络封面（晋江、长佩、起点等平台）
- 保留文案/简介内容在第一章前

### 章节识别支持
| 格式 | 示例 |
|------|------|
| 标准格式 | `第1章 标题` / `第一章 标题` |
| 等号分隔 | `==第1章 标题==` |
| 数字序号 | `1、第一章 标题` |
| 特殊章节 | `楔子` / `番外` |

## 项目结构

```
novel-transfer/
├── txt_optimizer.py   # 主入口
├── encoding.py        # 编码检测
├── chapter.py         # 章节分析
├── display.py         # 目录显示
├── cover.py           # 封面下载
├── easypub.py         # EasyPub优化
└── epub.py            # EPUB生成
```

## 安装依赖

```bash
pip3 install ebooklib pillow requests
```

## 使用方法

### 命令行模式

#### 1. 优化 TXT 文件（生成 *epub_ready.txt）
```bash
python3 txt_optimizer.py --convert ~/Downloads/novel.txt
```

#### 2. 生成 EPUB 文件
```bash
python3 txt_optimizer.py --epub ~/Downloads/novel_epub_ready.txt
```

#### 3. 指定书名和作者
```bash
python3 txt_optimizer.py --epub novel.txt --title "书名" --author "作者"
```

#### 4. 指定封面图片
```bash
python3 txt_optimizer.py --epub novel.txt --cover ~/Downloads/cover.jpg
```

#### 5. 自动搜索封面（推荐）
```bash
python3 txt_optimizer.py --epub novel.txt --auto-cover
```

#### 6. 查看章节目录
```bash
python3 txt_optimizer.py --catalog ~/Downloads/novel.txt
```

#### 7. 查看目录结构
```bash
python3 txt_optimizer.py --tree ~/Downloads/
```

#### 8. 批量转换文件夹
```bash
python3 txt_optimizer.py --batch ~/Downloads/novels/
```

#### 9. 显示帮助
```bash
python3 txt_optimizer.py --guide
```

## 命令行参数

| 参数 | 说明 |
|------|------|
| `--convert <文件>` | 转换单个文件为EasyPub友好格式 |
| `--batch <文件夹>` | 批量转换文件夹内的所有txt文件 |
| `--epub <文件>` | 将优化后的TXT文件转换为EPUB |
| `--tree <路径>` | 显示文件或目录结构 |
| `--catalog <文件>` | 显示TXT文件的章节目录 |
| `--guide` | 显示使用指南 |
| `--author <作者>` | 指定作者名 |
| `--title <书名>` | 指定书名 |
| `--cover <图片>` | 指定封面图片路径 |
| `--cover-url <URL>` | 指定封面图片URL |
| `--auto-cover` | 自动搜索封面 |

## 工作流程

```
原始TXT文件
    │
    ▼
┌─────────────────┐
│  --convert      │  标准化章节格式
│  生成*_epub_ready.txt │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  --epub         │  生成EPUB
│  (可选封面搜索)  │
└─────────────────┘
    │
    ▼
   EPUB文件
```

## 支持的章节格式

脚本自动识别多种章节格式：

| 格式类型 | 示例 | 说明 |
|---------|------|------|
| 标准章节 | `第1章 标题`、`第一章 标题` | 支持中文数字和阿拉伯数字 |
| 特殊前缀 | `◇ 第20章 标题`、`◆ 第25章 标题` | 支持 ◇、◆、*、•、· 等符号前缀 |
| 方括号编号 | `[289]福利番外`、`[100]标题` | 方括号包裹的数字编号 |
| 分卷名 | `第一案：标题`、`第二卷：标题` | 以"案"或"卷"结尾的分卷名称 |
| 楔子 | `楔子`、`楔子 标题` | 小说序章 |
| 番外 | `番外1 标题`、`番外一 标题` | 额外故事章节 |
| 简单编号 | `1、第1章 标题` | 数字+顿号格式 |

## 输出文件

- 优化后的 TXT：`{书名}_epub_ready.txt`
- 章节分析：`{书名}_analysis.json`
- 生成的 EPUB：`{书名}.epub`
- 批量报告：`batch_report.md`

## 支持的平台

- macOS ✓
- Windows ✓
- Linux ✓

## 封面搜索来源

1. 晋江文学城 (jjwxc.net)
2. 长佩文学 (gongzicp.com)
3. 起点中文网 (qidian.com)
4. Open Library
5. Bing 图片搜索

## 修改记录

### v1.3 (2026-05-16)
- 新增分卷名识别支持（如 `第一案：标题`、`第二卷：标题`）
- 新增特殊字符前缀章节支持（如 `◇ 第20章`、`◆ 第25章`）
- 新增方括号编号章节支持（如 `[289]福利番外`）
- 新增独立数字行章节支持（如单独一行 `47` 后跟 `第47章`）
- 修复章节标题中数字前后有空格的识别问题（如 `===第 220 章 番外===`）
- 新增数字+标题连在一起的章节格式支持（如 `29同心结`）
- 修复UTF-8 BOM字符导致书名提取失败的问题
- 优化章节识别逻辑，避免章节内小标题被误识别为独立章节
- 修复书名提取逻辑，只在文件开头部分搜索，避免误匹配内容中的书名
- 修复书名前缀识别问题，正确移除"书名："、"题名："等前缀
- 修复书名中方括号 `[]` 被移除的问题，保留书名原始格式
- 新增书名提取和封面下载的详细调试日志，方便排查问题
- 优化段落合并逻辑，正确处理连续空行，避免产生过多段落
- 新增章节内容清理功能，移除章节末尾的单独括号等冗余字符

### v1.2 (2026-05-15)
- 新增自动提取书名和作者功能
- 支持多种书名格式：`《书名》作者`、`书名\n作者：`
- 新增 `--cover-url` 参数支持指定封面图片URL

### v1.1 (2026-05-14)
- 脚本重构为模块化结构
- 支持多种章节格式识别
- 新增番外章节处理逻辑
