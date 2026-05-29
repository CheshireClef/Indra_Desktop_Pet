@echo off
chcp 65001 >nul

REM =============================
REM 工程根目录（bat 所在目录）
REM =============================
set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

set "PYTHON=%PROJECT_ROOT%venv\Scripts\python.exe"
set "PYINSTALLER=%PROJECT_ROOT%venv\Scripts\pyinstaller.exe"

if not exist "%PYTHON%" (
    echo [错误] 未找到虚拟环境：%PYTHON%
    echo 请先创建 venv 并安装 requirements.txt
    pause
    exit /b 1
)

REM =============================
REM 打包前资源检查
REM =============================
echo [1/4] 检查嵌入模型与向量库…
"%PYTHON%" scripts\verify_pack_inputs.py
if errorlevel 1 (
    pause
    exit /b 1
)

REM =============================
REM 清理旧构建
REM =============================
echo [2/4] 清理 build / dist…
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM =============================
REM PyInstaller 打包（onedir）
REM =============================
echo [3/4] PyInstaller 打包中（体积较大，请耐心等待）…
"%PYINSTALLER%" FGO因陀罗桌宠.spec
if errorlevel 1 (
    echo [错误] PyInstaller 打包失败
    pause
    exit /b 1
)

REM =============================
REM 打包后路径验证
REM =============================
echo [4/4] 验证 dist 资源…
"%PYTHON%" scripts\verify_pack_output.py
if errorlevel 1 (
    pause
    exit /b 1
)

echo.
echo =============================
echo 打包完成！
echo 输出目录：dist\FGO因陀罗桌宠
echo.
echo 分发给测试用户时请打包整个文件夹（含 _internal）。
echo 用户配置与记忆库将写入 exe 旁 config\，勿只复制 exe。
echo =============================
pause
