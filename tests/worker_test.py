import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

"""测试 BLE 后台线程和 Qt 信号是否能正常收发（不连接耳机）。"""
import sys

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from ble_worker import BleWorker


def main():
    app = QApplication(sys.argv)
    worker = BleWorker()
    worker.start()
    result = {"devices": None, "error": None}

    def on_scan(devices):
        result["devices"] = devices
        loop.quit()

    def on_error(msg):
        result["error"] = msg
        loop.quit()

    worker.scan_result.connect(on_scan)
    worker.error.connect(on_error)

    loop = QEventLoop()
    QTimer.singleShot(12000, loop.quit)
    worker.scan(timeout=4.0)
    loop.exec()

    worker.stop()
    app.processEvents()

    print("error:", result["error"])
    if result["devices"] is None:
        print("NO RESULT")
        sys.exit(2)
    print("devices:", len(result["devices"]))
    for item in result["devices"][:10]:
        print(item)
    print("WORKER OK")


if __name__ == "__main__":
    main()
