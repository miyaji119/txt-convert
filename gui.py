#!/usr/bin/env python3
"""TXT转EPUB优化工具 - 图形化界面（GUI）兼容入口

本文件保留向后兼容性。实际代码已拆分到 gui/ 包中：
    gui/__init__.py     - 包入口，导出 main()
    gui/app.py          - TxtToEpubGUI 主窗口类
    gui/theme.py        - 主题与样式
    gui/constants.py    - 全局常量
    gui/log_panel.py    - 日志重定向
    gui/tabs/           - 各标签页模块

使用方法（任选其一）：
    python3 gui.py
    python3 -m gui
"""

import os
import sys

# 确保能导入同目录下的 gui 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui import main

if __name__ == '__main__':
    main()
