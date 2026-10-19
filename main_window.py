"""QCY H3 耳机控制台 —— 主窗口（中文界面）。"""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ble_worker import BleWorker
from h3_device import (
    ANCMode,
    EQ_BAND_LABELS,
    EQ_PRESET_IDS,
    EQ_PRESET_NAMES,
    EQ_PRESET_OFFSETS,
)

MODE_LABELS = [
    "关闭降噪",
    "通透模式",
    "降噪 低",
    "降噪 中",
    "降噪 高",
    "自适应",
]
MODE_BYTES = ANCMode.ALL

HINT_TEXT = (
    "使用前请先关闭手机上的 QCY App，并关闭手机蓝牙。"
    "耳机同一时间只允许一个 BLE 控制连接，手机占着时电脑会连不上。"
)


# -----------------------------------------------------------------------
# 扫描/选择设备对话框
# -----------------------------------------------------------------------

class ScanDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择耳机")
        self.setMinimumWidth(460)
        self.setMinimumHeight(320)
        self._selected: tuple | None = None

        tip = QLabel("正在扫描附近的蓝牙设备，请稍候…")
        tip.setWordWrap(True)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _item: self.accept())

        self._status = QLabel("扫描大约需要 5 秒。")
        self._status.setWordWrap(True)
        self._status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("连接")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(tip)
        lay.addWidget(self._list, 1)
        lay.addWidget(self._status)
        lay.addWidget(btns)

    def populate(self, devices: list):
        self._list.clear()

        # 把 QCY / H3 排在前面，其余按信号强度排在后面
        def sort_key(item):
            addr, name, rssi = item
            name_l = (name or "").lower()
            is_qcy = 0 if ("qcy" in name_l or "h3" in name_l) else 1
            return (is_qcy, -(rssi if rssi is not None else -999))

        devices = sorted(devices, key=sort_key)

        if not devices:
            self._status.setText(
                "没有找到任何蓝牙设备。请确认耳机已开机，并关闭手机 App 和手机蓝牙后重试。"
            )
            return

        qcy_count = 0
        for addr, name, rssi in devices:
            label = f"{name or '(未命名设备)'}    [{addr}]    {rssi} dBm"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, (addr, name))
            name_l = (name or "").lower()
            if "qcy" in name_l or "h3" in name_l:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                qcy_count += 1
            self._list.addItem(item)

        if qcy_count:
            self._status.setText(f"找到 {len(devices)} 个设备，其中 {qcy_count} 个可能是 QCY 耳机（已加粗）。")
        else:
            self._status.setText(
                f"找到 {len(devices)} 个设备，但没有看到 QCY。"
                "请关闭手机 App 和手机蓝牙，或把耳机重启后再扫描。"
            )

        # 默认选中第一个 QCY 设备，方便直接回车
        for i in range(self._list.count()):
            text = self._list.item(i).text().lower()
            if "qcy" in text or "h3" in text:
                self._list.setCurrentRow(i)
                break

    def accept(self):
        if self.selected_device() is None:
            self._status.setText("请先在列表里选中一个设备，再点“连接”。")
            return
        super().accept()

    def selected_device(self) -> tuple | None:
        item = self._list.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None


# -----------------------------------------------------------------------
# 单个 EQ 频段控件（垂直滑块 + 数值 + 频率）
# -----------------------------------------------------------------------

class EqBand(QWidget):
    edited = Signal()  # 用户手动拖动滑块

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._suppress_edited = False

        self._slider = QSlider(Qt.Orientation.Vertical)
        self._slider.setRange(-24, 24)  # ×50 = -1200 .. +1200（单位 1/100 dB）
        self._slider.setValue(0)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBothSides)
        self._slider.setTickInterval(4)  # 每格 2 dB
        self._slider.setFixedHeight(150)
        self._slider.valueChanged.connect(self._on_value_changed)

        self._db_label = QLabel("0.0 dB")
        self._db_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._db_label.setFixedWidth(58)

        freq_label = QLabel(label)
        freq_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        freq_label.setFixedWidth(58)
        font = freq_label.font()
        font.setPointSize(8)
        freq_label.setFont(font)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self._db_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self._slider, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(freq_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.setSpacing(4)
        lay.setContentsMargins(2, 2, 2, 2)

    def _on_value_changed(self, val: int):
        db = val * 50 / 100.0
        self._db_label.setText(f"{db:+.1f} dB" if db != 0 else "0.0 dB")
        if not self._suppress_edited:
            self.edited.emit()

    def value_hundredths(self) -> int:
        return self._slider.value() * 50

    def set_value_hundredths(self, v: int):
        self._suppress_edited = True
        try:
            self._slider.setValue(round(v / 50))
        finally:
            self._suppress_edited = False

    def reset(self):
        self.set_value_hundredths(0)


# -----------------------------------------------------------------------
# 主窗口
# -----------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QCY H3 耳机控制台（中文版）")
        self.setMinimumSize(840, 640)

        self._worker = BleWorker(self)
        self._worker.start()
        self._worker.scan_result.connect(self._on_scan_result)
        self._worker.connected.connect(self._on_connected)
        self._worker.disconnected.connect(self._on_disconnected)
        self._worker.error.connect(self._on_error)
        self._worker.battery_updated.connect(self._on_battery)
        self._worker.mode_updated.connect(self._on_mode_updated)
        self._worker.eq_updated.connect(self._on_eq_updated)
        self._worker.game_mode_updated.connect(self._on_game_mode_updated)
        self._worker.eq_applied.connect(self._on_eq_applied)

        self._scan_dialog: ScanDialog | None = None
        self._mode_buttons: list[QPushButton] = []
        self._eq_bands: list[EqBand] = []
        self._eq_preset_buttons: list[QPushButton] = []
        self._active_preset_idx: int = 0  # 默认“自定义”
        self._dirty_eq: bool = False
        self._loading_eq: bool = False

        # 连接后每 60 秒只刷新电量，避免覆盖用户正在编辑的 EQ
        self._battery_timer = QTimer(self)
        self._battery_timer.setInterval(60_000)
        self._battery_timer.timeout.connect(lambda: self._worker.refresh_battery())

        self._build_ui()
        self._set_connected(False)

    # ------------------------------------------------------------------
    # 界面搭建
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(10)
        root.setContentsMargins(14, 14, 14, 14)

        # ---- 顶部标题栏 ----
        header = QHBoxLayout()
        title = QLabel("QCY H3 耳机控制台")
        title.setFont(QFont("Microsoft YaHei UI", 15, QFont.Weight.Bold))
        subtitle = QLabel("中文版")
        subtitle.setStyleSheet("color: #666;")
        self._battery_label = QLabel("🔋 —")
        self._battery_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._battery_label.setMinimumWidth(80)
        self._game_mode_btn = QPushButton("游戏模式")
        self._game_mode_btn.setCheckable(True)
        self._game_mode_btn.setEnabled(False)
        self._game_mode_btn.setToolTip("低延迟模式，适合游戏；开启后音质可能略有下降")
        self._game_mode_btn.clicked.connect(self._on_game_mode_clicked)

        header.addWidget(title)
        header.addWidget(subtitle)
        header.addStretch()
        header.addWidget(self._game_mode_btn)
        header.addSpacing(8)
        header.addWidget(self._battery_label)
        root.addLayout(header)

        # ---- 提示 ----
        hint = QLabel(HINT_TEXT)
        hint.setWordWrap(True)
        hint.setStyleSheet(
            "color: #8a5a00; background: #fff8e1; padding: 6px 8px; border-radius: 4px;"
        )
        root.addWidget(hint)

        # ---- 连接栏 ----
        conn = QHBoxLayout()
        self._scan_btn = QPushButton("扫描耳机")
        self._scan_btn.clicked.connect(self._on_scan_clicked)
        self._disconnect_btn = QPushButton("断开连接")
        self._disconnect_btn.clicked.connect(lambda: self._worker.disconnect_device())
        self._refresh_btn = QPushButton("刷新状态")
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        self._device_label = QLabel("未连接")
        self._device_label.setStyleSheet("color: #666;")
        conn.addWidget(self._scan_btn)
        conn.addWidget(self._disconnect_btn)
        conn.addWidget(self._refresh_btn)
        conn.addSpacing(8)
        conn.addWidget(self._device_label)
        conn.addStretch()
        root.addLayout(conn)

        # ---- 降噪模式 ----
        mode_group = QGroupBox("降噪模式")
        mode_lay = QHBoxLayout(mode_group)
        mode_lay.setSpacing(6)
        for i, label in enumerate(MODE_LABELS):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setEnabled(False)
            btn.clicked.connect(lambda _, idx=i: self._on_mode_changed(idx))
            mode_lay.addWidget(btn)
            self._mode_buttons.append(btn)
        root.addWidget(mode_group)

        # ---- 均衡器 ----
        eq_group = QGroupBox("均衡器（10 段）")
        eq_root = QVBoxLayout(eq_group)
        eq_root.setSpacing(8)

        preset_lay = QHBoxLayout()
        preset_lay.setSpacing(4)
        preset_lay.addWidget(QLabel("预设："))
        for i, name in enumerate(EQ_PRESET_NAMES):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setEnabled(False)
            btn.clicked.connect(lambda _, idx=i: self._on_preset_btn(idx))
            preset_lay.addWidget(btn)
            self._eq_preset_buttons.append(btn)
        preset_lay.addStretch()
        eq_root.addLayout(preset_lay)
        self._eq_preset_buttons[0].setChecked(True)

        sliders_lay = QHBoxLayout()
        sliders_lay.setSpacing(2)
        for label in EQ_BAND_LABELS:
            band = EqBand(label)
            band.edited.connect(self._on_band_edited)
            sliders_lay.addWidget(band)
            self._eq_bands.append(band)
        eq_root.addLayout(sliders_lay)

        eq_btns = QHBoxLayout()
        self._eq_state_label = QLabel(
            "提示：选中预设会立即写入；自己拖动滑块后请点“应用均衡器”。"
        )
        self._eq_state_label.setStyleSheet("color: #666;")
        eq_btns.addWidget(self._eq_state_label)
        eq_btns.addStretch()
        reset_btn = QPushButton("重置滑块")
        reset_btn.clicked.connect(self._reset_eq)
        apply_btn = QPushButton("应用均衡器")
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._apply_eq)
        eq_btns.addWidget(reset_btn)
        eq_btns.addWidget(apply_btn)
        eq_root.addLayout(eq_btns)

        root.addWidget(eq_group, 1)

        footer = QLabel(
            "非官方工具，基于杰理 RCSP 协议。只修改耳机内的 EQ/降噪设置，不涉及固件升级。"
        )
        footer.setStyleSheet("color: #999; font-size: 11px;")
        footer.setWordWrap(True)
        root.addWidget(footer)

        # ---- 状态栏 ----
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪。请先关闭手机 App 和手机蓝牙，再点“扫描耳机”。")

    # ------------------------------------------------------------------
    # 状态切换
    # ------------------------------------------------------------------

    def _set_connected(self, connected: bool):
        self._scan_btn.setEnabled(not connected)
        self._disconnect_btn.setEnabled(connected)
        self._refresh_btn.setEnabled(connected)
        self._game_mode_btn.setEnabled(connected)
        for btn in self._mode_buttons:
            btn.setEnabled(connected)
        for band in self._eq_bands:
            band.setEnabled(connected)
        for btn in self._eq_preset_buttons:
            btn.setEnabled(connected)
        if not connected:
            self._device_label.setText("未连接")
            self._battery_label.setText("🔋 —")
            self._battery_timer.stop()
            for btn in self._mode_buttons:
                btn.setChecked(False)
            self._game_mode_btn.setChecked(False)

    def _set_mode_active(self, idx: int):
        for i, btn in enumerate(self._mode_buttons):
            btn.setChecked(i == idx)

    def _select_preset_button(self, idx: int):
        for i, btn in enumerate(self._eq_preset_buttons):
            btn.setChecked(i == idx)

    def _load_preset_values(self, idx: int):
        """把预设曲线填到滑块上，但不触发“已切到自定义”。"""
        preset_id = EQ_PRESET_IDS[idx]
        if preset_id == 0x00:
            return
        offsets = EQ_PRESET_OFFSETS.get(preset_id, [0] * 10)
        self._loading_eq = True
        try:
            for i, band in enumerate(self._eq_bands):
                band.set_value_hundredths(offsets[i] if i < len(offsets) else 0)
        finally:
            self._loading_eq = False

    # ------------------------------------------------------------------
    # 信号处理
    # ------------------------------------------------------------------

    def _on_scan_clicked(self):
        self._scan_dialog = ScanDialog(self)
        self._worker.scan(timeout=5.0)
        self.statusBar().showMessage("正在扫描附近的蓝牙设备…")
        result = self._scan_dialog.exec()
        if result == QDialog.DialogCode.Accepted and self._scan_dialog.selected_device():
            addr, name = self._scan_dialog.selected_device()
            self._device_label.setText(f"正在连接：{name or addr} …")
            self.statusBar().showMessage("正在连接耳机…")
            self._worker.connect_device(addr)
        self._scan_dialog = None

    def _on_scan_result(self, devices: list):
        if self._scan_dialog is not None:
            self._scan_dialog.populate(devices)
        self.statusBar().showMessage(f"扫描完成：找到 {len(devices)} 个设备。")

    def _on_connected(self, address: str):
        self._device_label.setText(f"已连接：{address}")
        self.statusBar().showMessage("已连接，正在读取耳机当前状态…")
        self._set_connected(True)
        self._battery_timer.start()

    def _on_disconnected(self):
        self._set_connected(False)
        self.statusBar().showMessage("已断开连接。")

    def _on_error(self, msg: str):
        self.statusBar().showMessage(f"错误：{msg}")
        QMessageBox.warning(self, "出错了", msg)

    def _on_battery(self, pct: int):
        self._battery_label.setText(f"🔋 {pct}%")

    def _on_mode_updated(self, idx: int):
        if 0 <= idx < len(self._mode_buttons):
            self._set_mode_active(idx)

    def _on_eq_updated(self, offsets: list):
        self._loading_eq = True
        try:
            for i, band in enumerate(self._eq_bands):
                if i < len(offsets):
                    band.set_value_hundredths(offsets[i])
        finally:
            self._loading_eq = False
        self._dirty_eq = False
        self._eq_state_label.setText("已读取耳机当前 EQ。")

    def _on_game_mode_updated(self, enabled: bool):
        self._game_mode_btn.setChecked(enabled)

    def _on_eq_applied(self):
        self._dirty_eq = False
        self.statusBar().showMessage("均衡器已写入耳机。")
        self._eq_state_label.setText("均衡器已写入耳机，手机上也会同步生效。")

    def _on_refresh_clicked(self):
        self._dirty_eq = False
        self.statusBar().showMessage("正在刷新耳机状态…")
        self._worker.refresh_status()

    # ------------------------------------------------------------------
    # 用户操作
    # ------------------------------------------------------------------

    def _on_mode_changed(self, idx: int):
        self._set_mode_active(idx)
        self._worker.set_mode(MODE_BYTES[idx])
        self.statusBar().showMessage(f"正在切换到：{MODE_LABELS[idx]} …")

    def _on_preset_btn(self, idx: int):
        self._active_preset_idx = idx
        self._select_preset_button(idx)
        self._load_preset_values(idx)
        self._dirty_eq = False
        self._apply_eq()

    def _on_band_edited(self):
        if self._loading_eq:
            return
        self._dirty_eq = True
        if self._active_preset_idx != 0:
            self._active_preset_idx = 0
            self._select_preset_button(0)
            self._eq_state_label.setText(
                "已切换到「自定义」。调好后点“应用均衡器”才会写入耳机。"
            )
        else:
            self._eq_state_label.setText("已修改，点“应用均衡器”写入耳机。")

    def _on_game_mode_clicked(self):
        enabled = self._game_mode_btn.isChecked()
        self._worker.set_game_mode(enabled)
        self.statusBar().showMessage(f"正在{'开启' if enabled else '关闭'}游戏模式…")

    def _reset_eq(self):
        self._loading_eq = True
        try:
            for band in self._eq_bands:
                band.reset()
        finally:
            self._loading_eq = False
        self._dirty_eq = True
        self._active_preset_idx = 0
        self._select_preset_button(0)
        self._eq_state_label.setText("滑块已归零。点“应用均衡器”写入耳机。")

    def _apply_eq(self):
        if not self._worker.is_connected:
            self.statusBar().showMessage("尚未连接耳机。")
            return
        offsets = [b.value_hundredths() for b in self._eq_bands]
        preset_id = EQ_PRESET_IDS[self._active_preset_idx]
        self._worker.set_eq(offsets, preset_id)
        self.statusBar().showMessage(
            f"正在写入均衡器（{EQ_PRESET_NAMES[self._active_preset_idx]}）…"
        )
        self._eq_state_label.setText("正在写入耳机…")

    # ------------------------------------------------------------------
    # 关闭窗口
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._battery_timer.stop()
        self._worker.stop()
        super().closeEvent(event)
