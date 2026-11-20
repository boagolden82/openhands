"""运行配置：路径解析、端口、数据目录。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "RDE-Onto"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def resource_root() -> Path:
    """只读资源根目录（源码目录或 PyInstaller 解包目录）。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def data_root() -> Path:
    """可写数据根目录，打包后与 exe 同级，源码运行时为仓库 data/。"""
    override = os.environ.get("RDE_DATA_DIR")
    if override:
        path = Path(override).expanduser()
    elif is_frozen():
        path = Path(sys.executable).resolve().parent / "data"
    else:
        path = resource_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return Path(os.environ.get("RDE_DB", data_root() / "rde.db"))


def ontology_path() -> Path:
    return Path(os.environ.get("RDE_ONTOLOGY", resource_root() / "ontology" / "ontology.json"))


def web_root() -> Path:
    return resource_root() / "app" / "web"


def host() -> str:
    return os.environ.get("RDE_HOST", "127.0.0.1")


def port() -> int:
    return int(os.environ.get("RDE_PORT", "8765"))


def open_browser() -> bool:
    return os.environ.get("RDE_NO_BROWSER", "") not in {"1", "true", "yes"}
