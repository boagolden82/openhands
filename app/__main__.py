"""启动入口：python -m app  /  rde_onto.exe"""
from __future__ import annotations

import os
import sys

from . import config
from .server import serve_forever


def main() -> int:
    if "--version" in sys.argv:
        from . import __version__
        print(f"{config.APP_NAME} {__version__}")
        return 0
    if "--help" in sys.argv or "-h" in sys.argv:
        print(f"""{config.APP_NAME} - 基于本体论的研发提效指标体系

用法：
  python -m app [选项]

选项：
  --port <n>      监听端口（默认 {config.port()}，也可用环境变量 RDE_PORT）
  --host <addr>   监听地址（默认 {config.host()}）
  --no-browser    启动后不自动打开浏览器
  --reseed        启动前重建演示数据
  --version       显示版本
""")
        return 0

    args = sys.argv[1:]
    for flag, env in (("--port", "RDE_PORT"), ("--host", "RDE_HOST")):
        if flag in args:
            idx = args.index(flag)
            if idx + 1 < len(args):

                os.environ[env] = args[idx + 1]
    if "--no-browser" in args:

        os.environ["RDE_NO_BROWSER"] = "1"
    if "--reseed" in args:
        from .seed import seed
        from .server import context
        ctx = context()
        print("  重建演示数据：", seed(ctx.onto, ctx.store))

    try:
        serve_forever()
    except OSError as exc:
        print(f"  启动失败：{exc}\n  端口可能已被占用，请用 --port 指定其他端口。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
