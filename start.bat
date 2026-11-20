@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title RDE-Onto 研发效能指标体系

echo ============================================================
echo   RDE-Onto  基于本体论的研发提效指标体系
echo ============================================================
echo.

cd /d "%~dp0"

set "RDE_PORT=8765"
set "RDE_NO_BROWSER="

rem ---------- 优先使用打包好的可执行文件 ----------
if exist "%~dp0RDE-Onto.exe" (
    echo [启动] 使用内置可执行文件 RDE-Onto.exe
    echo [地址] http://127.0.0.1:%RDE_PORT%
    echo [退出] 关闭本窗口即可停止服务
    echo.
    "%~dp0RDE-Onto.exe" %*
    goto :end
)

rem ---------- 否则使用 Python 源码运行 ----------
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [错误] 未检测到 Python，且当前目录没有 RDE-Onto.exe。
    echo.
    echo   方案一：直接下载发布包中的 RDE-Onto.exe，与本脚本放在同一目录后双击本脚本。
    echo   方案二：安装 Python 3.9 及以上版本 https://www.python.org/downloads/windows/
    echo           安装时请勾选 "Add Python to PATH"，然后重新运行本脚本。
    echo.
    pause
    goto :end
)

echo [环境] 使用 %PY%
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [错误] Python 版本过低，需要 3.9 及以上。
    pause
    goto :end
)

echo [启动] python -m app
echo [地址] http://127.0.0.1:%RDE_PORT%
echo [退出] 按 Ctrl+C 或关闭本窗口
echo.
%PY% -m app %*

:end
echo.
echo 服务已停止。
pause
