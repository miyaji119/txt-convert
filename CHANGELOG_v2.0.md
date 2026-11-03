# v3.0 变更记录

> **版本**: v3.0
> **日期**: 2026-11-03
> **变更范围**: Web UI 工具台重构、响应式与可访问性增强、EPUB 编辑器构建稳定性修复、文档与 standalone skill 同步

---

## 一、变更概览

| 模块 | 内容 | 新增文件 | 修改文件 |
|------|------|---------|---------|
| Web UI | App Shell + Hero + Step Card 工具台视觉体系；多 Tab 统一布局；sticky 生成操作区 | — | `static/index.html` |
| 响应式 | 小屏侧边栏横向滚动；表单、设置、EPUB 编辑器双列自动折叠 | — | `static/index.html` |
| 可访问性 | 导航键盘切换；统一 focus ring；图标按钮 / 状态栏按钮补充 `aria-label` | — | `static/index.html` |
| 组件化 | 抽取 quick chip、关键词 chip、配置文件行、状态栏、编辑器网格等 CSS 类 | — | `static/index.html` |
| EPUB 编辑器 | `EditorBuildReq` 补齐 `chapter_title_align`，与主 EPUB 生成接口保持一致 | — | `web_server.py` |
| 测试 | 新增编辑器构建请求模型回归测试 | — | `tests/test_api.py` |
| 文档 | README / 设计文档更新到 v3.0；standalone skill 对齐 v3.0 能力基线 | — | `README.md`, `design-docs/txt-convert_DESIGN.md`, `.claude/agents/novel-epub-typeset-standalone.md` |

---

## 二、Web UI v3.0

### 2.1 App Shell 与统一页面结构

`static/index.html` 从功能堆叠型页面升级为工具台式结构：

- 新增 `.app-body`、`.app-header`、`.app-layout`、`.app-sidebar`、`.app-main`
- 顶部品牌区使用 `.brand-mark`，主题切换使用 `.theme-toggle`
- 主内容区增加轻量径向渐变背景，提升层次但不引入新依赖
- 主要页面统一为 `.page-wrap` + `.mini-hero`
- `TXT → EPUB` 主流程使用更完整的 `.page-hero` + `.hero-stats`

### 2.2 Hero + Step Card 流程化

新增流程组件：

| 类名 | 用途 |
| ---- | ---- |
| `.page-hero` / `.hero-stats` | `TXT → EPUB` 顶部状态总览：当前文件、章节数、输出状态 |
| `.mini-hero` / `.mini-hero-badge` | 其他 Tab 标题与状态徽章 |
| `.step-card` / `.step-no` | 步骤卡片，强化“下一步该做什么” |
| `.action-bar` | `epub` 页底部 sticky 生成操作区 |

`TXT → EPUB` 页面拆为：

1. 选择 TXT 文件
2. 确认章节目录
3. 确认书籍信息
4. 封面选项
5. 排版样式

底部 sticky action bar 集中放置：输出目录、广告过滤、仅清洗 TXT、一键生成 EPUB。

### 2.3 多 Tab 统一

- **批量转换**：Hero 徽章显示成功数 / 总数；最近目录改为 chip；批量处理结果表格保留错误摘要。
- **目录编辑**：Hero 显示章节数；加载 TXT 改为 Step 入口；章节编辑、拖拽排序、保存逻辑不变。
- **广告扫描**：Hero 显示规则同步状态；扫描入口改为 Step；关键词展示改为可删除 chip。
- **章节识别**：Hero 显示规则同步状态；自定义规则列表改为 Step；配置文件操作行统一样式。
- **EPUB 编辑器**：加载文件改为 Step；章节列表 + 编辑区使用响应式双列布局。

---

## 三、响应式与可访问性

### 3.1 响应式布局

新增布局类：

- `.field-row`：输入框 + 按钮响应式行
- `.settings-grid`：设置双列，小屏折叠
- `.editor-grid`：EPUB 编辑器章节列表 + 编辑区双栏，小屏折叠
- `.two-col-grid` / `.span-all`：查找替换、元数据表单布局
- `.wide-page`：宽页面容器

`@media (max-width: 860px)` 下：

- body 改为可滚动
- sidebar 改为横向滚动导航
- Hero / 表单 / 编辑器双列布局折叠为单列
- action bar 按钮自动拉伸，避免横向溢出

### 3.2 可访问性

- 导航项增加 `role="button"`、`tabindex="0"`、`aria-current`
- 导航支持 Enter / Space 切换
- `.btn`、`.inp`、`.nav-item`、`.quick-chip`、`.theme-toggle`、`.icon-btn`、`.status-link` 统一 `:focus-visible`
- 主题切换、删除关键词、删除章节规则、查找、配置文件操作、底部状态栏操作补充 `aria-label`

---

## 四、CSS 组件化清理

新增或强化的可复用类：

| 类名 | 用途 |
| ---- | ---- |
| `.quick-chip` | 最近文件 / 最近目录 |
| `.kw-chip` / `.kw-chip-hard` / `.kw-chip-soft` | 广告关键词标签 |
| `.icon-btn` | `×` 等小图标按钮 |
| `.config-row` / `.config-path` | 配置文件路径 + 操作按钮行 |
| `.status-bar` / `.status-link` | 底部输出状态栏 |

同时修复多处重复静态 class，例如：

```html
<!-- 修复前 -->
<div class="card" class="mb3">

<!-- 修复后 -->
<div class="card mb3">
```

---

## 五、EPUB 编辑器稳定性修复

### 问题

`/api/editor/build` 内部调用：

```python
chapter_title_align=req.chapter_title_align or "center"
```

但 `EditorBuildReq` 未声明 `chapter_title_align` 字段。某些编辑器重建 EPUB 请求会触发 `AttributeError`。

### 修复

`web_server.py` 中 `EditorBuildReq` 新增：

```python
# 章节标题对齐：'left'|'center'|'right'；需与 EpubReq 保持一致
chapter_title_align: str = "center"
```

与主 EPUB 生成接口 `EpubReq` 保持一致。

### 回归测试

`tests/test_api.py` 新增：

```python
def test_editor_build_req_supports_chapter_title_align():
    from web_server import EditorBuildReq

    default_req = EditorBuildReq()
    assert default_req.chapter_title_align == "center"

    explicit_req = EditorBuildReq(chapter_title_align="right")
    assert explicit_req.chapter_title_align == "right"
```

全量测试结果：

```text
23 passed, 1 warning in 0.47s
```

---

## 六、文档与 Skill 同步

### README

`README.md` Web UI 版本更新为 `v3.0`，新增：

- 现代化工具台 UI（v3.0）
- 响应式布局优化
- 可访问性增强
- 编辑器重建稳定性修复

### 设计文档

`design-docs/txt-convert_DESIGN.md` 新增 `v3.0 稳定版深化`，记录：

- App Shell / Hero / Step Card 结构
- responsive class 约定
- 可访问性策略
- `EditorBuildReq.chapter_title_align` 稳定性修复

### Standalone Skill

`.claude/agents/novel-epub-typeset-standalone.md` 对齐 txt-convert v3.0 能力基线：

- 行内广告截取 + 全角域名归一化
- `split_plain` / `split_ruled` 章节标题样式
- `chapter_title_align` 参数语义
- 晋江 / 长佩 / 起点 / 微信读书 / 豆瓣 / Bing 六源封面思路
- Step 6/7/8/9 流程编号修正

---

# v2.3 变更记录

> **版本**: v2.3
> **日期**: 2026-08-31
> **变更范围**: Web UI 发布、广告/水印过滤、多书合并检测、EPUB 结构改进

---

## 一、变更概览

| 模块 | 内容 | 新增文件 | 修改文件 |
|------|------|---------|---------|
| Web UI | FastAPI 服务器 + 浏览器界面 | `web_server.py`, `static/index.html` | — |
| 广告过滤 | 多信号评分，连续块删除 | `adfilter.py` | `easypub.py` |
| 水印清理 | 独立行水印识别与删除 | `namecleaner.py` | `easypub.py` |
| 一致性检测 | 跨章节内容检测，多书合并识别 | `consistency.py` | `easypub.py`, `web_server.py` |
| EPUB 结构 | 文案简介保留、目录页生成 | — | `epub.py` |

---

## 二、Web UI

### `web_server.py`（新增，~320 行）

**架构**：FastAPI + uvicorn，单命令启动，自动打开浏览器。

- **日志捕获**：`_Tee` 类劫持 `sys.stdout`，将每行写入 `asyncio.Queue`
- **SSE 日志流**：`GET /api/logs/stream`，浏览器 `EventSource` 实时接收
- **自动退出**：SSE 连接断开（浏览器关闭标签）后 4 秒无新连接则 `os.kill(SIGINT)`
- **macOS 文件对话框**：`osascript choose file/folder`，避开 tkinter 主线程限制
- **线程安全**：所有阻塞 Python 函数通过 `ThreadPoolExecutor` + `run_in_executor` 执行

#### API 端点

| 端点 | 说明 |
|------|------|
| `GET /` | 返回 `static/index.html` |
| `GET /api/logs/stream` | SSE 日志流 |
| `POST /api/dialog` | 打开文件/文件夹选择对话框 |
| `GET /api/recent` | 最近文件/目录列表 |
| `POST /api/extract-meta` | 提取书名/作者/文件大小 |
| `POST /api/convert` | 单文件转换 |
| `POST /api/batch` | 批量转换 |
| `POST /api/epub` | 生成 EPUB |
| `POST /api/catalog/analyze` | 章节结构分析 |
| `POST /api/open-in-finder` | 在 Finder 中显示 |
| `POST /api/open-file` | 用默认程序打开文件 |

### `static/index.html`（新增，~700 行）

**技术栈**：Tailwind CSS（CDN）+ Alpine.js（CDN），零构建步骤。

**视觉设计**：

- 深色主题（`#0b0e12` 底色，琥珀 `#d97706` 强调色）
- 浅色主题（暖纸白 `#f5f0e8`，棕琥珀 `#b45309`），CSS 变量切换
- 偏好保存在 `localStorage`
- 动画进度条（shimmer 效果 / 绿色完成 / 红色失败）
- Toast 通知（滑入动画，4 秒自动消失）
- 导航徽标（`✓`/`✗`/章节数）
- JetBrains Mono 字体用于日志面板

**交互特性**：

- 文件选择后自动调用 `/api/extract-meta`，书名/作者自动填充并显示「自动识别」标签
- 用户手动修改输入框后标签消失（`@input` 设置 `edited` 标志）
- SSE 连接断线后 3 秒自动重连

---

## 三、广告过滤 `adfilter.py`（新增，~110 行）

### 评分机制

每行打 0–1 广告概率分：

| 信号 | 分值 |
|------|------|
| URL / 域名 | 0.88 |
| 平台名称 + 关键词（笔趣阁、起点等） | 0.82 |
| 硬关键词（下载APP、扫码、公众号等） | 0.78 |
| 软关键词累加（书友、更新最快等） | +0.18/个 |
| 短行（< 20 字） | +0.08 |
| 文件首尾 30 行（near_boundary） | ×1.4 |

### 过滤规则

- 单行分值 ≥ 0.68 → 删除
- 连续 ≥3 行分值均 ≥ 0.45 → 整块删除
- 章节标题行（`第X章/卷`）永远豁免
- 过滤后合并多余空行（保留最多 2 个）

### 集成

`convert_for_easypub()` 读文件后、`ChapterAnalyzer` 之前调用，输出 `🧹 过滤广告行: N 行`。

---

## 四、水印清理 `namecleaner.py`（新增，~100 行）

### 角色名单提取

从全文提取合法角色名（豁免集合）：

- 动作动词前缀：`X说道/问道/道/喊道` 等
- 引号/冒号前缀：`X：…` / `X「…`

### 检测逻辑

候选独立行需同时满足：

1. 纯汉字 2–8 字（`[一-龥·]{2,8}`）
2. 前后均为空行（独立行）
3. 不是章节标题（`第X章/卷`）
4. 不在角色名单中（包含子串匹配）

### 集成

`AdFilter` 之后调用，输出 `🔤 清理独立行水印: 落叶知秋、书友521 共 N 处`。

---

## 五、一致性检测 `consistency.py`（新增，~120 行）

### 实体提取

每章提取：

- **人名**：动作动词前缀 + 引号前缀（同 NameCleaner 逻辑）
- **地名**：`[一-龥]{1,4}[城国山河殿宫门村镇县府道阁岛峰谷林原界域]`

### 检测算法

滑动窗口比较：

```
left_pool = union(entities[i-3 : i])   # 前3章实体池
current   = entities[i]

若 len(left_pool) >= 4 且 len(current) >= 3 且 overlap == 0:
    zero_streak += 1
    if zero_streak >= 2: → ContentMismatchError
```

### 错误处理

`ContentMismatchError` 携带：

- `split_after`：断裂章节索引
- `left_title` / `right_title`：断裂前后章节标题
- `left_sample` / `right_sample`：各 6 个实体示例

**Web 端**：`ContentMismatchError` → HTTP 422，诊断信息显示在 Toast。

**跳过**：`convert_for_easypub(..., ignore_mismatch=True)`。

---

## 六、EPUB 结构改进（`epub.py`）

### 文案简介保留

**原逻辑**：仅从 `INTRO_MARKERS`（`文案：`/`简介：`）出现后开始收集，标题/作者行等前置内容丢失。

**新逻辑**：收集第一章之前的**所有**非注释行，首尾空行去掉后作为独立章节；含简介标记则命名「文案简介」，否则命名「前言」。

### 目录页生成

在「文案简介/前言」之后插入目录章节：

- `<ol class="toc">` 列表，每项 `<a href="chapter_NNN.xhtml">` 超链接
- 文件编号计算时已偏移（+1 for TOC），链接不错位
- 目录 CSS 独立内联，不影响正文章节

### 章节生成逻辑

新增 `_html` 键支持：若章节 dict 含 `_html`，直接使用该 HTML 内容，跳过 `_chapter_to_html()`。目录章节和未来其他特殊章节可用此机制。

---

## 七、`easypub.py` 变更

### 函数签名

```python
def convert_for_easypub(
    input_file, output_file=None, book_title="", author="",
    show_catalog=True,
    ignore_mismatch=False,    # 新增：跳过一致性检测
) -> Tuple[Optional[str], Optional[Dict]]:
```

### 新增调用链

```
读文件
  → AdFilter.filter_content()        # 广告过滤
  → NameCleaner.clean()              # 水印清理
  → ChapterAnalyzer.analyze()        # 章节分析
  → ConsistencyChecker.check()       # 一致性检测（可跳过）
  → EasyPubOptimizer.optimize()      # 优化
  → 写文件
```

---

# v2.0 代码变更总结



> **版本**: v2.0  
> **日期**: 2026-08-10  
> **变更范围**: 封面下载重构、GUI 架构拆分、TaskRunner 机制优化、配置持久化、主题迁移

---

## 一、变更概览

| 阶段 | 内容 | 新增文件 | 修改文件 | 代码行数 |
|------|------|---------|---------|---------|
| 1 | 封面下载重构 | cover_picker_dialog.py | cover.py | ~500 行 |
| 2 | GUI 拆分为包 | 11 个文件 | gui.py | ~2100 行重组 |
| 3 | TaskRunner 重构 | task_runner.py | app.py | ~170 行 |
| 4 | 配置持久化 | config.py, settings_dialog.py | app.py + 4 Tab | ~370 行 |
| 5 | sv-ttk 主题迁移 | — | theme.py + 6 文件 | ~190 行 |

**总计**: 新增 15 个文件，修改 10+ 个文件，新增代码约 3200 行。

---

## 二、阶段 1：封面下载重构

### 问题诊断

原 `cover.py` 的 5 个搜索源全部失效：

| 搜索源 | 失效原因 |
|--------|---------|
| Google 图片 | 反爬严格，返回 HTML 不含真实图片 URL |
| Bing 图片 | `mediaurl=` 正则易匹配到无关图 |
| OpenLibrary | 英文书为主，中文网络小说几乎无数据 |

根本缺陷：无相关性验证 + 无候选选择 + 无尺寸过滤。

### 改动内容

#### `cover.py` 完全重写（217 行 → 792 行）

**新增架构**：
- `CoverCandidate` 数据类：`image_url/source/confidence/book_title/author`
- `CoverDownloader` 类：多候选搜索 + 置信度排序 + 本地缓存
- 多源搜索：晋江 JSON API、豆瓣 suggest 接口、长佩（骨架）、Bing 兜底

**核心特性**：
1. **置信度排序**：完全匹配 1.0 / 包含 0.85 / 作者匹配 +0.1
2. **封面形状过滤**：宽高比 0.5-0.95、最小 200×280、文件 ≥10KB
3. **本地缓存**：`~/.txt2epub/covers/{书名+作者hash}.jpg`
4. **PIL 优先 + 文件头回退**：无 PIL 时解析 JPEG SOF0/PNG IHDR

#### `cover_picker_dialog.py` 新增（273 行）

**封面候选选择对话框**：
- 网格布局展示候选缩略图（120×170）
- 异步加载：后台线程下载缩略图，queue 传回主线程
- 置信度标签：≥80% 绿色 / ≥50% 橙色 / 其他灰色
- 无 PIL 时降级为文字卡片

### 实测结果

| 测试用例 | 命中源 | 置信度 | 下载尺寸 |
|---------|--------|--------|---------|
| 天官赐福 / 墨香铜臭 | 豆瓣 | 1.00 | 700×980 |
| 全职高手 / 蝴蝶蓝 | 豆瓣 | 0.90 | 750×1082 |
| 魔道祖师 / 墨香铜臭 | 晋江 | 1.00 | 300×420 |

---

## 三、阶段 2：GUI 拆分为包

### 改动内容

原 `gui.py`（2069 行单文件）拆分为 11 个文件的 `gui/` 包：

```
txt-convert/
├── gui.py                          # 兼容入口（27 行）
└── gui/
    ├── __init__.py                 # 包入口，导出 main + sys.path 设置
    ├── constants.py                # APP_VERSION/APP_TITLE/EPUB_SUPPORT
    ├── theme.py                    # COLORS + setup_style()
    ├── log_panel.py                # TextRedirector 类
    ├── task_runner.py              # TaskRunner 类（阶段 3 新增）
    ├── settings_dialog.py          # 设置对话框（阶段 4 新增）
    ├── app.py                      # TxtToEpubGUI 主窗口（~450 行）
    └── tabs/
        ├── __init__.py
        ├── base_tab.py             # BaseTab 基类（~95 行）
        ├── convert_tab.py          # ConvertTab 单文件转换（~140 行）
        ├── batch_tab.py            # BatchTab 批量转换（~130 行）
        ├── epub_tab.py             # EpubTab EPUB生成（~450 行）
        └── catalog_tab.py          # CatalogTab 章节编辑（~540 行）
```

### 关键设计决策

1. **sys.path 处理**：`gui/__init__.py` 顶部将上级目录加入 sys.path
2. **循环依赖规避**：`base_tab.py` 用 `TYPE_CHECKING` + 字符串注解
3. **theme 模块化**：`_setup_style` 提取为独立函数 `setup_style(root, colors)`
4. **兼容入口**：`gui.py` 保留为 27 行入口，`python3 gui.py` 和 `python3 -m gui` 均可运行

### 收益

- 单文件 2069 行 → 11 个文件各 27-540 行
- 闭包陷阱更易审查（每个 Tab 独立，回调嵌套更浅）
- 各 Tab 可独立导入和单测

---

## 四、阶段 3：TaskRunner 重构

### 问题背景

原 `run_task` 方法用 `lambda: on_error(e)` 在 `root.after` 中延迟执行，except 块结束后 `e` 被 Python 自动删除，导致 `NameError: cannot access free variable 'e'`。

### 改动内容

#### `gui/task_runner.py` 新增（126 行）

**核心设计**：用 `functools.partial` 在提交时冻结所有参数，机制性杜绝闭包陷阱。

```python
def submit(self, target, *args, on_complete=None, on_error=None, **kwargs):
    # 第 1 层：submit 时冻结 target/args/kwargs/回调
    task_fn = functools.partial(
        self._execute_task, target, args, kwargs, on_complete, on_error)
    self._current_future = self._executor.submit(task_fn)

def _execute_task(self, target, args, kwargs, on_complete, on_error):
    try:
        result = target(*args, **kwargs)
        if on_complete:
            # 第 2 层：成功结果立即绑定
            self._schedule_main(functools.partial(on_complete, result))
    except Exception as e:
        if on_error:
            # 第 3 层：except 块异常对象立即绑定（关键！）
            self._schedule_main(functools.partial(on_error, e))
```

#### `gui/app.py` 修改

- `__init__` 用 TaskRunner 替换原 `worker_thread`/`cancel_flag`
- `run_task` 委托给 `task_runner.submit`（删除 42 行内联 _worker 闭包）
- 新增 `worker_thread`/`cancel_flag` property 委托给 task_runner
- `_cancel_task` 委托给 `task_runner.cancel`
- `_on_close` 添加 `task_runner.shutdown`

### 对比：原方案 vs 新方案

| 对比项 | 原方案（lambda 默认参数） | 新方案（functools.partial） |
|--------|-------------------------|--------------------------|
| 成功回调 | `lambda r=result: on_complete(r)` | `functools.partial(on_complete, result)` |
| 异常回调 | `lambda err=e: on_error(err)` | `functools.partial(on_error, e)` |
| 安全性 | 依赖开发者记得写默认参数 | 机制强制，无法写错 |
| 线程管理 | 手动 `threading.Thread` | `ThreadPoolExecutor(max_workers=1)` |
| 任务串行 | 手动检查 `is_alive()` | `future.done()` 自动检查 |

---

## 五、阶段 4：配置持久化

### 改动内容

#### `config.py` 新增（160 行）

配置文件：`~/.txt2epub/config.json`

```json
{
  "version": 1,
  "recent_files": [],
  "recent_dirs": [],
  "default_output_dir": "",
  "last_title": "",
  "last_author": "",
  "cover_choice": 4,
  "last_tab_index": 0,
  "window_geometry": "",
  "custom_chapter_patterns": []
}
```

**Config 类 API**：
- `load()` / `save()`：加载/保存配置
- `get(key, default)` / `set(key, value)`：读写配置项
- `add_recent_file(path)` / `add_recent_dir(path)`：最近路径管理（去重，保留 5 个）
- `add_chapter_pattern(pattern, type)` / `remove_chapter_pattern(pattern)`：正则规则管理
- `get_enabled_chapter_patterns()`：获取已启用规则 → `[(pattern, type), ...]`

#### `gui/settings_dialog.py` 新增（208 行）

**设置对话框**（菜单 `文件 → 设置...`）：
1. 默认输出目录设置
2. 自定义章节正则规则管理（添加/删除/启用/禁用）
3. 正则合法性校验（`re.compile` 验证）

#### 各 Tab 集成

- **EpubTab**：`cover_var` 从 config 读取 + `_on_file_selected` 记录最近文件
- **ConvertTab/CatalogTab**：`_on_file_selected` 记录最近文件
- **BatchTab**：`_start_batch` 记录最近目录
- **app.py**：启动加载配置 + 关闭保存（窗口/Tab/封面/书名作者）

### 持久化覆盖范围

| 配置项 | 写入时机 | 读取时机 |
|--------|---------|---------|
| window_geometry | 关闭时 | 启动时 |
| last_tab_index | 关闭时 | 启动时 |
| cover_choice | 关闭时 | EpubTab 初始化 |
| last_title/last_author | 关闭时 | 供未来自动填充 |
| recent_files | 文件选择时 | 供未来下拉菜单 |
| recent_dirs | 批量转换时 | 供未来下拉菜单 |
| default_output_dir | 设置对话框保存 | 供 epub.py 使用 |
| custom_chapter_patterns | 设置对话框操作 | 供 chapter.py 使用 |

---

## 六、阶段 5：sv-ttk 主题迁移

### 改动内容

#### `gui/theme.py` 重写（186 行）

**主题策略（三级适配）**：
```
sv-ttk Sun Valley (Tk 8.6+)
       ↓ 失败回退
clam 主题 + Accent.TButton 手写蓝色样式 (Tk 8.5+)
       ↓ 失败回退
系统默认主题
```

- 优先用 `sv_ttk.set_theme("light")` 加载 Sun Valley 主题
- 运行时失败（Tk 版本不够）自动回退到 clam + 手写样式
- 保留 COLORS 字典，新增 `log_bg`/`log_fg` 键

#### 样式迁移

- `Primary.TButton` → `Accent.TButton`（sv-ttk 原生样式名）
- 5 个文件全局替换：convert_tab/batch_tab/epub_tab/catalog_tab/settings_dialog
- 回退模式中手动定义 `Accent.TButton`（蓝色强调按钮）

#### `gui/app.py` 修改

日志区颜色从硬编码改为使用 COLORS 字典：
```python
bg=self.colors['log_bg'], fg=self.colors['log_fg'],
```

### 当前环境状态

| 项 | 状态 |
|---|---|
| sv-ttk 安装 | ✓ 2.6.1 已安装 |
| 系统 Tk 版本 | 8.5.9（不满足 sv-ttk 需要的 8.6+） |
| 实际生效主题 | clam（自动回退） |
| 升级路径 | `brew install python-tk` 后自动启用 Sun Valley |

---

## 七、新增依赖

| 依赖 | 版本 | 用途 | 必需性 |
|------|------|------|--------|
| sv-ttk | 2.6.1 | Sun Valley 主题 | 可选（自动回退） |
| ebooklib | — | EPUB 生成 | 可选 |
| Pillow | 11.3.0 | 封面缩略图/尺寸检测 | 可选（有回退） |
| requests | — | 封面下载 | 可选 |

安装命令：
```bash
pip3 install sv-ttk ebooklib pillow requests
```

---

## 八、文件变更清单

### 新增文件（15 个）

| 文件 | 行数 | 说明 |
|------|------|------|
| `cover_picker_dialog.py` | 273 | 封面候选选择对话框 |
| `config.py` | 160 | 配置持久化管理 |
| `gui/__init__.py` | 34 | 包入口 |
| `gui/app.py` | ~480 | 主窗口（从 gui.py 提取） |
| `gui/constants.py` | 16 | 全局常量 |
| `gui/theme.py` | 186 | 主题样式（sv-ttk + 回退） |
| `gui/log_panel.py` | 24 | 日志重定向 |
| `gui/task_runner.py` | 126 | 任务执行器（partial 机制） |
| `gui/settings_dialog.py` | 208 | 设置对话框 |
| `gui/tabs/__init__.py` | 1 | Tab 子包 |
| `gui/tabs/base_tab.py` | 95 | Tab 基类 |
| `gui/tabs/convert_tab.py` | ~140 | 单文件转换 Tab |
| `gui/tabs/batch_tab.py` | ~130 | 批量转换 Tab |
| `gui/tabs/epub_tab.py` | ~450 | EPUB 生成 Tab |
| `gui/tabs/catalog_tab.py` | ~540 | 章节编辑 Tab |

### 修改文件（5 个）

| 文件 | 变更说明 |
|------|---------|
| `cover.py` | 完全重写（217→792 行），多候选架构 |
| `gui.py` | 2069 行 → 27 行兼容入口 |
| `gui/tabs/epub_tab.py` | 新增封面候选流程（5 个方法） |
| `gui/tabs/catalog_tab.py` | config 集成 |
| `gui/app.py` | TaskRunner + config + sv-ttk 集成 |

---

## 九、验证结果

所有阶段均通过以下验证：

- ✅ 语法检查（py_compile）全部通过
- ✅ GUI 实例化 + 启动 + 关闭无运行时错误
- ✅ 封面搜索：3 本中文小说全部精准命中
- ✅ TaskRunner：正常任务回调 + 异常任务回调（except 块变量安全）
- ✅ 配置持久化：读写/最近路径/正则规则全部正常
- ✅ 主题迁移：sv-ttk 回退模式正常，Accent.TButton 样式生效
- ✅ 4 个 Tab 功能完整，按钮样式统一为 Accent.TButton
