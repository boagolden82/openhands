"""PyInstaller / 直接运行入口。

打包后资源位于 sys._MEIPASS，数据写入 exe 同级的 data/ 目录。
"""
from __future__ import annotations

import multiprocessing
import sys

from app.__main__ import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
