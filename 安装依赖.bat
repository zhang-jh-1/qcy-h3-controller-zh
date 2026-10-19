@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo 未找到 Python。请先安装 Python 3.10 或更高版本，
  echo 安装时务必勾选 "Add python.exe to PATH"。
  echo 下载地址: https://www.python.org/downloads/
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo 正在创建虚拟环境...
  py -3 -m venv .venv
  if errorlevel 1 goto :fail
)

echo 正在安装依赖，首次安装需要下载约 200 MB，请耐心等待...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo 安装完成。现在可以双击 "启动.bat" 运行。
pause
exit /b 0

:fail
echo.
echo 安装失败，请检查网络，或把上面的错误内容发给我。
pause
exit /b 1
