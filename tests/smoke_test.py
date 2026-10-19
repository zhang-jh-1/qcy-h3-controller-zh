import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

"""无耳机环境下的界面冒烟测试：检查中文界面能正常创建并截图。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    for _ in range(20):
        app.processEvents()

    assert "QCY H3" in win.windowTitle()
    assert win._scan_btn.text() == "扫描耳机"
    assert win._disconnect_btn.text() == "断开连接"
    assert win._refresh_btn.text() == "刷新状态"
    assert win._game_mode_btn.text() == "游戏模式"
    assert len(win._mode_buttons) == 6
    assert [b.text() for b in win._mode_buttons][0] == "关闭降噪"
    assert len(win._eq_bands) == 10
    assert len(win._eq_preset_buttons) == 7
    assert win._eq_preset_buttons[0].text() == "自定义"
    assert win._eq_preset_buttons[3].text() == "重低音"

    win.grab().save("ui_preview.png")
    print("window title:", win.windowTitle())
    print("presets:", [b.text() for b in win._eq_preset_buttons])
    print("modes:", [b.text() for b in win._mode_buttons])
    print("screenshot: ui_preview.png")

    win.close()
    app.processEvents()
    print("SMOKE OK")


if __name__ == "__main__":
    main()
