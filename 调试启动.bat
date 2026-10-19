@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo 请先双击 "安装依赖.bat"。
  pause
  exit /b 1
)

echo 调试模式：保留控制台窗口，出错时会显示错误信息。
".venv\Scripts\python.exe" app.py
pause
