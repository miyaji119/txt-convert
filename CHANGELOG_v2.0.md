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
