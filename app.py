"""QCY H3 耳机控制台（中文版）——程序入口。"""
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from main_window import MainWindow


def _light_palette() -> QPalette:
    """固定使用浅色配色，避免 Windows 深色模式下自定义颜色看不清。"""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor("#f4f6f8"))
    p.setColor(QPalette.ColorRole.WindowText, QColor("#1f2328"))
    p.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor("#f0f2f5"))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor("#1f2328"))
    p.setColor(QPalette.ColorRole.Text, QColor("#1f2328"))
    p.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.ButtonText, QColor("#1f2328"))
    p.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.Highlight, QColor("#2d7ff9"))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#9aa0a6"))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#9aa0a6"))
    return p


APP_STYLE = """
QGroupBox {
    border: 1px solid #d8dde3;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QGroupBox QLabel, QGroupBox QPushButton {
    font-weight: normal;
}
QPushButton {
    padding: 5px 12px;
    border: 1px solid #c9ced6;
    border-radius: 4px;
    background: #ffffff;
}
QPushButton:hover {
    background: #eef4ff;
}
QPushButton:checked {
    background: #2d7ff9;
    color: #ffffff;
    border-color: #2d7ff9;
}
QPushButton:disabled {
    color: #a0a6ad;
    background: #f2f3f5;
    border-color: #e1e4e8;
}
"""


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("QCY H3 耳机控制台")
    app.setApplicationDisplayName("QCY H3 耳机控制台（中文版）")
    app.setStyle("Fusion")
    app.setPalette(_light_palette())
    app.setStyleSheet(APP_STYLE)

    font = QFont("Microsoft YaHei UI")
    font.setPointSizeF(9.5)
    app.setFont(font)

    win = MainWindow()
    win.show()

    # 打包后的自检：带 --smoke-test 参数时，截图并写标记文件后自动退出。
    if "--smoke-test" in sys.argv:
        def finish():
            try:
                win.grab().save("smoke_exe.png")
                with open("smoke_exe.txt", "w", encoding="utf-8") as f:
                    f.write(win.windowTitle() + "\n")
                    f.write(f"presets={[b.text() for b in win._eq_preset_buttons]}\n")
                print("SMOKE OK")
            finally:
                app.quit()

        QTimer.singleShot(1500, finish)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
