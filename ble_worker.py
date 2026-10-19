"""BLE 后台工作线程。

在一个独立线程里运行 asyncio 事件循环，所有蓝牙操作都提交到这个循环；
结果通过 Qt 信号回到界面线程，避免界面卡死。
"""
import asyncio
import sys
import threading

from PySide6.QtCore import QObject, Signal

from h3_device import H3Device, scan
from rcsp import AdvType, parse_tlv


class BleWorker(QObject):
    scan_result = Signal(list)          # [(地址, 名称, 信号强度), ...]
    connected = Signal(str)             # 设备地址
    disconnected = Signal()
    error = Signal(str)
    battery_updated = Signal(int)       # 0-100
    mode_updated = Signal(int)          # 0-5
    eq_updated = Signal(list)           # 10 个整数，单位 1/100 dB
    game_mode_updated = Signal(bool)    # True = 游戏模式开
    eq_applied = Signal()               # 耳机确认写入 EQ

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._device: H3Device | None = None
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # 线程生命周期
    # ------------------------------------------------------------------

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, name="BleThread", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5.0)

    def stop(self):
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def _run_loop(self):
        # Windows 下直接使用 Selector 事件循环：bleak 的 WinRT 后端在
        # Selector 循环里工作最稳定，也避免 Python 3.14 的事件循环策略弃用警告。
        if sys.platform == "win32":
            self._loop = asyncio.SelectorEventLoop()
        else:
            self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        try:
            self._loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self._loop.close()

    def _submit(self, coro):
        if self._loop is None or not self._loop.is_running():
            coro.close()
            self.error.emit("蓝牙后台线程尚未就绪，请稍后重试。")
            return None
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    # ------------------------------------------------------------------
    # 界面线程可调用的接口
    # ------------------------------------------------------------------

    def scan(self, timeout: float = 5.0):
        self._submit(self._do_scan(timeout))

    def connect_device(self, address: str):
        self._submit(self._do_connect(address))

    def disconnect_device(self):
        self._submit(self._do_disconnect())

    def set_mode(self, mode_bytes: bytes):
        self._submit(self._do_set_mode(mode_bytes))

    def set_eq(self, db_offsets: list[int], preset_id: int = 0x00):
        self._submit(self._do_set_eq(db_offsets, preset_id))

    def set_game_mode(self, enabled: bool):
        self._submit(self._do_set_game_mode(enabled))

    def refresh_status(self):
        self._submit(self._do_refresh())

    def refresh_battery(self):
        self._submit(self._do_refresh_battery())

    # ------------------------------------------------------------------
    # 协程（在蓝牙线程里执行）
    # ------------------------------------------------------------------

    async def _do_scan(self, timeout: float):
        try:
            devices = await scan(timeout=timeout)
            self.scan_result.emit(devices)
        except Exception as e:
            self.error.emit(f"扫描失败：{e}")

    async def _do_connect(self, address: str):
        if self._device is not None:
            try:
                await self._device.disconnect()
            except Exception:
                pass
            self._device = None

        device = H3Device(address)
        try:
            await device.connect()
            await device.notify_communication_way(way=0, reconnect=0)
            await asyncio.sleep(0.2)
        except Exception as e:
            try:
                await device.disconnect()
            except Exception:
                pass
            self._device = None
            self.error.emit(f"连接失败：{e}")
            return

        self._device = device
        self.connected.emit(address)
        await self._do_refresh()

    async def _do_disconnect(self):
        if self._device is not None:
            try:
                await self._device.disconnect()
            except Exception:
                pass
            self._device = None
        self.disconnected.emit()

    async def _read_battery(self, dev: H3Device):
        pkt = await dev.get_battery()
        if pkt and pkt.params:
            for t, v in parse_tlv(pkt.params):
                if t == AdvType.BATTERY_QUANTITY and len(v) >= 1:
                    self.battery_updated.emit(int(v[0]))
                    return

    async def _do_refresh_battery(self):
        dev = self._device
        if dev is None:
            return
        try:
            await self._read_battery(dev)
        except Exception:
            pass

    async def _do_refresh(self):
        dev = self._device
        if dev is None:
            return

        try:
            await self._read_battery(dev)
        except Exception:
            pass

        try:
            mode = await dev.get_mode()
            if mode is not None:
                self.mode_updated.emit(mode)
        except Exception:
            pass

        try:
            offsets = await dev.get_eq()
            if offsets is not None:
                self.eq_updated.emit(offsets)
        except Exception:
            pass

        try:
            game = await dev.get_work_mode()
            if game is not None:
                self.game_mode_updated.emit(game)
        except Exception:
            pass

    def _require_device(self) -> H3Device | None:
        if self._device is None or not self._device.is_connected:
            self.error.emit("尚未连接耳机，请先扫描并连接。")
            return None
        return self._device

    async def _do_set_mode(self, mode_bytes: bytes):
        dev = self._require_device()
        if dev is None:
            return
        try:
            resp = await dev.set_mode(mode_bytes)
            if resp is None:
                self.error.emit("耳机没有响应，降噪模式可能未生效。请重试。")
        except Exception as e:
            self.error.emit(f"切换降噪模式失败：{e}")

    async def _do_set_eq(self, db_offsets: list[int], preset_id: int = 0x00):
        dev = self._require_device()
        if dev is None:
            return
        try:
            resp = await dev.set_eq(db_offsets, preset_id)
            if resp is None:
                self.error.emit("耳机没有响应，均衡器可能未写入。请重试。")
            else:
                self.eq_applied.emit()
        except Exception as e:
            self.error.emit(f"应用均衡器失败：{e}")

    async def _do_set_game_mode(self, enabled: bool):
        dev = self._require_device()
        if dev is None:
            return
        try:
            resp = await dev.set_game_mode(enabled)
            if resp is None:
                self.error.emit("耳机没有响应，游戏模式可能未生效。请重试。")
        except Exception as e:
            self.error.emit(f"切换游戏模式失败：{e}")

    @property
    def is_connected(self) -> bool:
        return self._device is not None and self._device.is_connected
