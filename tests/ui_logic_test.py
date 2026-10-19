import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

"""界面逻辑测试：预设、滑块联动、扫描列表排序。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

from main_window import MainWindow, ScanDialog


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    win = MainWindow()
    win.show()
    app.processEvents()

    # 读取 EQ 后滑块应同步
    win._on_eq_updated([0, 150, -150, 100, 0, 0, 200, -200, 50, -50])
    assert win._eq_bands[1].value_hundredths() == 150
    assert win._eq_bands[2].value_hundredths() == -150

    # 选中“摇滚”预设，滑块应填入预设曲线
    win._on_preset_btn(4)
    assert win._eq_preset_buttons[4].isChecked()
    assert win._eq_bands[0].value_hundredths() == 400
    assert win._eq_bands[3].value_hundredths() == -200

    # 手动拖动滑块后应自动切回“自定义”
    band = win._eq_bands[0]
    band.set_value_hundredths(250)
    band._on_value_changed(band._slider.value())
    assert win._eq_preset_buttons[0].isChecked()
    assert not win._eq_preset_buttons[4].isChecked()

    # 未连接时点“应用均衡器”不应崩溃
    win._apply_eq()

    # 扫描列表：QCY 排在最前并默认选中
    dlg = ScanDialog(win)
    dlg.populate([
        ("AA:BB:CC:DD:EE:01", "Other Device", -30),
        ("AA:BB:CC:DD:EE:02", "QCY H3-APP", -70),
        ("AA:BB:CC:DD:EE:03", "", -50),
    ])
    assert dlg._list.count() == 3
    assert "QCY H3-APP" in dlg._list.item(0).text()
    assert dlg.selected_device()[1] == "QCY H3-APP"

    # 没选中设备时点“连接”不应关闭对话框
    dlg._list.clearSelection()
    dlg._list.setCurrentRow(-1)
    dlg.accept()
    assert dlg.result() != QDialog.DialogCode.Accepted

    win.close()
    app.processEvents()
    print("UI LOGIC OK")


if __name__ == "__main__":
    main()
