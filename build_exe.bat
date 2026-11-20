@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title RDE-Onto 打包为 Windows 可执行文件

cd /d "%~dp0"
echo ============================================================
echo   RDE-Onto  Windows 打包脚本
echo ============================================================
echo.

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [错误] 未检测到 Python。请安装 Python 3.9+ 并勾选 Add Python to PATH。
    pause
    exit /b 1
)

echo [1/4] 检查 PyInstaller ...
%PY% -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo      未安装，正在安装 PyInstaller ...
    %PY% -m pip install --upgrade pip >nul 2>&1
    %PY% -m pip install pyinstaller
    if errorlevel 1 (
        echo [错误] PyInstaller 安装失败，请检查网络或使用国内镜像：
        echo        %PY% -m pip install pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple
        pause
        exit /b 1
    )
)

echo [2/4] 清理旧产物 ...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/4] 执行 PyInstaller 打包（单文件，内嵌本体与前端资源）...
%PY% -m PyInstaller --noconfirm --clean rde_onto.spec
if errorlevel 1 (
    echo [错误] 打包失败，请查看上方日志。
    pause
    exit /b 1
)

echo [4/4] 组装发布包 ...
if not exist dist\RDE-Onto-win64 mkdir dist\RDE-Onto-win64
copy /y dist\RDE-Onto.exe dist\RDE-Onto-win64\RDE-Onto.exe >nul
copy /y start.bat dist\RDE-Onto-win64\start.bat >nul
if exist README.md copy /y README.md dist\RDE-Onto-win64\README.md >nul
if exist docs rmdir /s /q dist\RDE-Onto-win64\docs
if exist docs xcopy /e /i /q docs dist\RDE-Onto-win64\docs >nul

echo.
echo ============================================================
echo   打包完成
echo   可执行文件： dist\RDE-Onto.exe
echo   发布目录  ： dist\RDE-Onto-win64\
echo   使用方法  ： 双击 RDE-Onto.exe 或 start.bat
echo ============================================================
pause
