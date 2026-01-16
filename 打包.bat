@echo off
chcp 65001

REM =============================
REM 工程根目录（bat 所在目录）
REM =============================
set PROJECT_ROOT=%~dp0
cd /d %PROJECT_ROOT%

REM =============================
REM 清理旧构建
REM =============================
rmdir /s /q build
rmdir /s /q dist

REM =============================
REM PyInstaller 打包（onedir）
REM =============================
pyinstaller ^
  --name "FGO因陀罗桌宠" ^
  --noconsole ^
  --onedir ^
  --icon assets\images\icon.ico ^
  ^
  --add-data "assets;assets" ^
  --add-data "config;config" ^
  --add-data "manual_images;manual_images" ^
  --add-data "multilingual-e5-small;multilingual-e5-small" ^
  --add-data "screenshots;screenshots" ^
  --add-data "src;src" ^
  ^
  --add-data "用户手册.html;." ^
  --add-data "requirements.txt;." ^
  ^
  src\main.py

REM =============================
REM 完成提示
REM =============================
echo.
echo =============================
echo 打包完成！
echo 输出目录：dist\FGO因陀罗桌宠
echo =============================
pause
