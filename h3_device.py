"""QCY H3 BLE device controller."""
import asyncio
from typing import Callable

from bleak import BleakClient, BleakScanner

from rcsp import AdvType, HEADER, OpCode, Packet, TYPE_COMMAND, hex_str

# ANC/mode command bytes (Custom opCode 255)
class ANCMode:
    TRANSPARENCY    = bytes([0x17, 0x03, 0x02, 0x00, 0x00])  # ANC desligado
    NORMAL          = bytes([0x17, 0x03, 0x03, 0x01, 0x04])  # Transparência (ambiente)

    NOISY_LOW       = bytes([0x17, 0x03, 0x01, 0x01, 0x00])  # Ruidoso baixo
    NOISY_MED       = bytes([0x17, 0x03, 0x01, 0x01, 0x01])  # Ruidoso médio
    NOISY_HIGH      = bytes([0x17, 0x03, 0x01, 0x01, 0x02])  # Ruidoso alto

    COMMUTING_LOW   = bytes([0x17, 0x03, 0x01, 0x02, 0x00])  # Transporte baixo
    COMMUTING_MED   = bytes([0x17, 0x03, 0x01, 0x02, 0x01])  # Transporte médio
    COMMUTING_HIGH  = bytes([0x17, 0x03, 0x01, 0x02, 0x02])  # Transporte alto

    INDOOR_LOW      = bytes([0x17, 0x03, 0x01, 0x03, 0x00])  # Interior baixo
    INDOOR_MED      = bytes([0x17, 0x03, 0x01, 0x03, 0x01])  # Interior médio
    INDOOR_HIGH     = bytes([0x17, 0x03, 0x01, 0x03, 0x02])  # Interior alto

    ANTIWIND        = bytes([0x17, 0x03, 0x01, 0x04, 0x00])  # Anti-vento
    ADAPTIVE        = bytes([0x17, 0x03, 0x01, 0x05, 0x00])  # Adaptativo

    ALL = [
        TRANSPARENCY,
        NORMAL,
        NOISY_LOW, NOISY_MED, NOISY_HIGH,
        ADAPTIVE,
    ]

    @staticmethod
    def from_params(params: bytes) -> int | None:
        """Decode mode index (0-5) from GET 0x17 response params."""
        if len(params) < 5:
            return None
        sub   = params[2]
        group = params[3]
        level = params[4]
        if sub == 0x02:
            return 0   # ANC Desligado
        if sub == 0x03:
            return 1   # Transparência
        if sub == 0x01:
            if group == 0x01:
                return 2 + level   # ANC Low/Med/High → 2,3,4
            if group == 0x05:
                return 5           # Adaptativo
        return None


# EQ band configuration (10 bands matching QCY app)
EQ_BANDS_FREQS = [0x0037, 0x00DC, 0x01F4, 0x03E8, 0x0708, 0x0AF0, 0x1194, 0x1D4C, 0x2710, 0x55F0]
EQ_BAND_LABELS = ["55 Hz", "220 Hz", "500 Hz", "1 kHz", "1.8 kHz", "2.8 kHz", "4.5 kHz", "7.5 kHz", "10 kHz", "22 kHz"]
# (ref_gain, Q) per frequency - sourced from device GET response & HCI capture
EQ_BAND_DEFAULTS = {
    0x0037: (40,  2),   # 55 Hz
    0x00DC: (120, 2),   # 220 Hz
    0x01F4: (150, 2),   # 500 Hz
    0x03E8: (150, 2),   # 1 kHz
    0x0708: (120, 2),   # 1.8 kHz
    0x0AF0: (80,  2),   # 2.8 kHz
    0x1194: (130, 2),   # 4.5 kHz  (Q=2 entry from GET)
    0x1D4C: (120, 2),   # 7.5 kHz
    0x2710: (120, 2),   # 10 kHz
    0x55F0: (80,  2),   # 22 kHz   (extrapolated)
}
# EQ 预设 ID：0x00 = 自定义（用滑块自己调），0x01-0x06 = 内置预设
EQ_PRESETS = [
    ("自定义",   0x00),
    ("默认",     0x01),
    ("流行",     0x02),
    ("重低音",   0x03),
    ("摇滚",     0x04),
    ("柔和",     0x05),
    ("古典",     0x06),
]
EQ_PRESET_NAMES = [name for name, _ in EQ_PRESETS]
EQ_PRESET_IDS   = [pid  for _, pid  in EQ_PRESETS]

# Default band values per preset in 1/100-dB units (10 bands)
# Custom starts flat so user can adjust from scratch
EQ_PRESET_OFFSETS: dict[int, list[int]] = {
    0x00: [0,   0,   0,    0,    0,    0,    0,    0,    0,   0],   # Custom
    0x01: [0,   0,   0,    0,    0,    0,    0,    0,    0,   0],   # Default
    0x02: [0,   150, 150,  100,  0,    100,  200,  200,  150, 100], # Pop
    0x03: [500, 400, 200,  0,   -100,  0,    0,    100,  200, 100], # Heavy Bass
    0x04: [400, 300, 0,   -200, -100,  0,    200,  300,  400, 200], # Rock
    0x05: [100, 100, 100,  100,  100,  100,  100,  100,  100, 100], # Soft
    0x06: [0,   0,   100,  300,  300,  300,  200,  100,  100, 0],   # Classic
}

SERVICE_UUID = "0000a002-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "00000001-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "00000002-0000-1000-8000-00805f9b34fb"


class H3Device:
    def __init__(self, address: str):
        self.address = address
        self._client: BleakClient | None = None
        self._sn = 0
        self._pending: dict[int, asyncio.Future[Packet]] = {}
        self._rx_buffer = bytearray()
        self.on_notification: Callable[[Packet], None] | None = None
        self.on_raw: Callable[[bytes], None] | None = None

    async def connect(self) -> None:
        self._client = BleakClient(self.address, timeout=15.0)
        await self._client.connect()
        await self._client.start_notify(NOTIFY_UUID, self._handle_notify)

    async def disconnect(self) -> None:
        if self._client and self._client.is_connected:
            try:
                await self._client.stop_notify(NOTIFY_UUID)
            except Exception:
                pass
            await self._client.disconnect()

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    def _next_sn(self) -> int:
        self._sn = (self._sn + 1) & 0xFF
        if self._sn == 0:
            self._sn = 1
        return self._sn

    def _handle_notify(self, _sender, data: bytearray) -> None:
        if self.on_raw:
            self.on_raw(bytes(data))
        self._rx_buffer.extend(data)
        while True:
            idx = self._rx_buffer.find(HEADER)
            if idx < 0:
                self._rx_buffer.clear()
                return
            if idx > 0:
                del self._rx_buffer[:idx]
            if len(self._rx_buffer) < 8:
                return
            param_len = (self._rx_buffer[5] << 8) | self._rx_buffer[6]
            total = 7 + param_len + 1
            if len(self._rx_buffer) < total:
                return
            pkt_bytes = bytes(self._rx_buffer[:total])
            del self._rx_buffer[:total]
            pkt = Packet.decode(pkt_bytes)
            if pkt is None:
                continue
            fut = self._pending.pop(pkt.sn, None)
            if fut and not fut.done():
                fut.set_result(pkt)
            elif self.on_notification:
                self.on_notification(pkt)

    async def send(self, pkt: Packet, timeout: float = 2.0) -> Packet | None:
        if not self._client or not self._client.is_connected:
            raise RuntimeError("Not connected")
        if pkt.sn == 0:
            pkt.sn = self._next_sn()
        data = pkt.encode()
        fut: asyncio.Future[Packet] | None = None
        if pkt.has_response:
            fut = asyncio.get_running_loop().create_future()
            self._pending[pkt.sn] = fut
        await self._client.write_gatt_char(WRITE_UUID, data, response=False)
        if fut is None:
            return None
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(pkt.sn, None)
            return None

    async def notify_communication_way(self, way: int = 0, reconnect: int = 0) -> Packet | None:
        """Tell device we're on BLE (way=0) vs SPP (way=1). Required after BLE connect."""
        return await self.send(
            Packet(op_code=OpCode.NOTIFY_COMMUNICATION_WAY, params=bytes([way, reconnect]))
        )

    async def get_target_info(self) -> Packet | None:
        return await self.send(Packet(op_code=OpCode.GET_TARGET_INFO, params=b""))

    async def get_target_feature_map(self) -> Packet | None:
        return await self.send(Packet(op_code=OpCode.GET_TARGET_FEATURE_MAP, params=b""))

    async def set_anc_mode(self, mode: int) -> Packet | None:
        """Set ANC level. mode=0 (low), 1 (medium), 2 (high)."""
        return await self.send(
            Packet(op_code=OpCode.CUSTOM, params=bytes([0x17, 0x03, 0x01, 0x01, mode & 0xFF]))
        )

    async def set_mode(self, mode_bytes: bytes) -> Packet | None:
        """Set noise mode using raw 5-byte ANCMode constant."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=mode_bytes))

    async def get_mode(self) -> int | None:
        """Get current mode. Returns mode index 0-4 (NORMAL/TRANSP/ANC_LOW/MED/HIGH) or None."""
        resp = await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x17])))
        if resp is None or len(resp.params) < 5:
            return None
        return ANCMode.from_params(resp.params)

    async def get_anc_state(self) -> Packet | None:
        """Get current ANC state raw packet."""
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x17])))

    async def get_eq(self) -> list[int] | None:
        """Get current EQ. Returns 10 db_offset values in 1/100-dB units, or None.
        For duplicate frequencies (e.g. 4500 Hz appears twice in device response),
        the last entry wins — which is the user-adjustable Q=2 copy."""
        resp = await self.send(Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x22])))
        if resp is None or len(resp.params) < 2 or resp.params[0] != 0x22:
            return None
        ll = resp.params[1]
        data = resp.params[2:2 + ll]
        if len(data) < 3 + 7 * 7:
            return None
        bands: dict[int, int] = {}
        num_entries = (len(data) - 3) // 7
        for i in range(num_entries):
            base = 3 + i * 7
            b = data[base:base + 7]
            freq = int.from_bytes(b[0:2], "little")
            db_off = int.from_bytes(b[2:4], "little", signed=True)
            if freq in EQ_BANDS_FREQS:
                bands[freq] = db_off  # last entry wins for duplicates
        if not bands:
            return None
        return [bands.get(f, 0) for f in EQ_BANDS_FREQS]

    async def set_eq(self, db_offsets: list[int], preset_id: int = 0x00) -> Packet | None:
        """Set EQ. db_offsets: 10 values in 1/100-dB (-1200..+1200).
        preset_id: 0x00=custom, 0x01=Default, 0x02=Pop ... 0x06=Classic."""
        band_bytes = bytearray()
        for i, freq in enumerate(EQ_BANDS_FREQS):
            ref_gain, q = EQ_BAND_DEFAULTS[freq]
            db_off = db_offsets[i] if i < len(db_offsets) else 0
            band_bytes += freq.to_bytes(2, "little")
            band_bytes += db_off.to_bytes(2, "little", signed=True)
            band_bytes += ref_gain.to_bytes(2, "little")
            band_bytes += bytes([q])
        header = bytes([preset_id & 0xFF, 0x70, 0xFE])
        data_len = len(header) + len(band_bytes)  # 3 + 10*7 = 73
        payload = bytes([0x22, data_len & 0xFF]) + header + bytes(band_bytes)
        return await self.send(Packet(op_code=OpCode.CUSTOM, params=payload))

    async def get_work_mode(self) -> bool | None:
        """Get current work mode. Returns True=game mode, False=normal, None=unknown."""
        pkt = await self.get_adv_info(1 << AdvType.WORK_MODE)
        if pkt is None or not pkt.params:
            return None
        from rcsp import parse_tlv
        for t, v in parse_tlv(pkt.params):
            if t == AdvType.WORK_MODE and len(v) >= 1:
                return v[0] == 0x02
        return None

    async def set_game_mode(self, enabled: bool) -> Packet | None:
        """Enable or disable game mode (low-latency audio)."""
        val = 0x02 if enabled else 0x01
        return await self.send(
            Packet(op_code=OpCode.SET_ADV_INFO, params=bytes([0x02, AdvType.WORK_MODE, val]))
        )

    async def get_sys_info(self, function: int, mask: int) -> Packet | None:
        """GetSysInfo with function (BT=0, PUBLIC=0xFF, etc.) and 32-bit attr mask."""
        params = bytes([function & 0xFF]) + mask.to_bytes(4, "big")
        return await self.send(Packet(op_code=OpCode.GET_SYS_INFO, params=params))

    async def get_adv_info(self, mask: int) -> Packet | None:
        """Get ADV info. mask is a 32-bit bitfield: bit N = AdvType N.
        Examples: 0x0001 = battery only, 0xFFFFFFFF = all."""
        return await self.send(
            Packet(
                op_code=OpCode.GET_ADV_INFO,
                params=mask.to_bytes(4, "big"),
            )
        )

    async def get_battery(self) -> Packet | None:
        return await self.get_adv_info(1 << AdvType.BATTERY_QUANTITY)


async def scan(timeout: float = 6.0) -> list:
    result = await BleakScanner.discover(timeout=timeout, return_adv=True)
    items = []
    for dev, adv in result.values():
        name = dev.name or adv.local_name or ""
        items.append((dev.address, name, adv.rssi))
    items.sort(key=lambda x: x[2] or -999, reverse=True)
    return items
