@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo 请先双击 "安装依赖.bat"。
  pause
  exit /b 1
)

echo 正在打包，首次需要下载 PyInstaller，请稍候...
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 goto :fail

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --onedir ^
  --name "QCY_H3_中文版" ^
  --hidden-import bleak.backends.winrt ^
  --collect-all bleak ^
  app.py
if errorlevel 1 goto :fail

echo.
echo 打包完成：dist\QCY_H3_中文版\QCY_H3_中文版.exe
echo 整个 dist\QCY_H3_中文版 文件夹就是发布包。
pause
exit /b 0

:fail
echo.
echo 打包失败，请把上面的错误内容发给我。
pause
exit /b 1
