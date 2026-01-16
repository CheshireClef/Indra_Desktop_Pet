@echo off
:: 先切换活动代码页为UTF-8（解决中文乱码核心），并延迟生效
chcp 65001 > nul 2>&1
:: 关闭命令回显的同时，设置控制台字体/编码适配（可选，增强兼容性）
setlocal enabledelayedexpansion
title FGO因陀罗桌宠 - 自动打包脚本

:: ===================== 1. 检查必要文件/文件夹是否存在 =====================
echo [1/3] 检查必要文件/文件夹...
set "required_dirs=assets config manual_images multilingual-e5-small src screenshots"
set "required_files=requirements.txt 用户手册.html src\main.py"
set "missing_flag=0"

:: 检查文件夹（替换特殊符号为文字描述，避免乱码）
for %%d in (!required_dirs!) do (
    if not exist "%%d" (
        echo [错误] 缺失必要文件夹：%%d
        set "missing_flag=1"
    ) else (
        echo [成功] 文件夹存在：%%d
    )
)

:: 检查文件（替换特殊符号为文字描述，避免乱码）
for %%f in (!required_files!) do (
    if not exist "%%f" (
        echo [错误] 缺失必要文件：%%f
        set "missing_flag=1"
    ) else (
        echo [成功] 文件存在：%%f
    )
)

:: 若缺失文件，终止打包
if !missing_flag! equ 1 (
    echo.
    echo [失败] 打包失败：缺失必要文件/文件夹，请检查！
    pause
    exit /b 1
)

:: ===================== 2. 执行打包命令 =====================
echo.
echo [2/3] 开始打包...
pyinstaller -D ^
--name "FGO因陀罗桌宠" ^
--add-data "assets;assets" ^
--add-data "config;config" ^
--add-data "manual_images;manual_images" ^
--add-data "multilingual-e5-small;multilingual-e5-small" ^
--add-data "screenshots;screenshots" ^
--add-data "src;src" ^
--add-data "用户手册.html;." ^
--add-data "requirements.txt;." ^
--icon "assets\images\icon.ico" ^
--console ^
src/main.py

:: ===================== 3. 打包结果提示 =====================
echo.
if exist "dist\FGO因陀罗桌宠" (
    echo [成功] 打包成功！
    echo [路径] 打包文件路径：%cd%\dist\FGO因陀罗桌宠
    echo [说明] .gitattributes/.gitignore未打包（非必要文件）
) else (
    echo [失败] 打包失败！请检查PyInstaller是否安装、命令是否正确。
)

echo.
echo 按任意键退出...
pause > nul
endlocal