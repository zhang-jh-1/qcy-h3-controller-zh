@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" app.py
  exit /b 0
)

where pythonw >nul 2>nul
if errorlevel 1 (
  echo 未找到 Python 环境，请先双击 "安装依赖.bat"。
  pause
  exit /b 1
)

start "" pythonw app.py
