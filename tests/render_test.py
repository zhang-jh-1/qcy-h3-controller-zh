import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

"""在真实 Windows 平台插件下渲染一次，确认中文字体正常。"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "windows"

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from app import APP_STYLE, _light_palette
from main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(_light_palette())
    app.setStyleSheet(APP_STYLE)
    font = QFont("Microsoft YaHei UI")
    font.setPointSizeF(9.5)
    app.setFont(font)
    families = QFontDatabase.families()
    has_yahei = [f for f in families if "YaHei" in f or "雅黑" in f]

    win = MainWindow()
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.show()
    for _ in range(30):
        app.processEvents()

    win.grab().save("ui_preview_win.png")
    with open("ui_check.txt", "w", encoding="utf-8") as f:
        f.write(f"font families: {len(families)}\n")
        f.write(f"yahei: {has_yahei}\n")
        f.write(f"title: {win.windowTitle()}\n")
        f.write(f"presets: {[b.text() for b in win._eq_preset_buttons]}\n")
        f.write(f"modes: {[b.text() for b in win._mode_buttons]}\n")
    print("RENDER OK")
    win.close()
    app.processEvents()


if __name__ == "__main__":
    main()
