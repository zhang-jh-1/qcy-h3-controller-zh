"""
RCSP (Remote Control Service Protocol) - JieLi BLE protocol.

Packet format:
    [FE DC BA] header (3B)
    [flag]     1B: bit7 = type (0=response, 1=command), bit6 = hasResponse
    [opCode]   1B
    [paramLen] 2B big-endian
    [status]   1B - present ONLY if type=0 (response)
    [opCodeSn] 1B - sequence number
    [xmOpCode] 1B - present ONLY if opCode==1
    [params]   N bytes
    [EF]       footer (1B)
"""
from dataclasses import dataclass, field

HEADER = bytes([0xFE, 0xDC, 0xBA])
FOOTER = 0xEF

TYPE_RESPONSE = 0
TYPE_COMMAND = 1


@dataclass
class Packet:
    op_code: int
    type: int = TYPE_COMMAND
    has_response: int = 1
    status: int = 0
    sn: int = 0
    xm_op_code: int | None = None
    params: bytes = b""

    def encode(self) -> bytes:
        flag = ((self.type & 1) << 7) | ((self.has_response & 1) << 6)
        body = bytearray()

        if self.type == TYPE_RESPONSE:
            body.append(self.status & 0xFF)
        body.append(self.sn & 0xFF)
        if self.op_code == 1 and self.xm_op_code is not None:
            body.append(self.xm_op_code & 0xFF)
        body += self.params

        param_len = len(body)
        out = bytearray(HEADER)
        out.append(flag)
        out.append(self.op_code & 0xFF)
        out.append((param_len >> 8) & 0xFF)
        out.append(param_len & 0xFF)
        out += body
        out.append(FOOTER)
        return bytes(out)

    @classmethod
    def decode(cls, data: bytes) -> "Packet | None":
        if len(data) < 8:
            return None
        idx = data.find(HEADER)
        if idx < 0:
            return None
        d = data[idx:]
        if len(d) < 8:
            return None

        flag = d[3]
        op_code = d[4]
        param_len = (d[5] << 8) | d[6]
        total = 7 + param_len + 1
        if len(d) < total:
            return None
        if d[total - 1] != FOOTER:
            return None

        ptype = (flag >> 7) & 1
        has_resp = (flag >> 6) & 1

        i = 7
        status = 0
        if ptype == TYPE_RESPONSE:
            status = d[i]
            i += 1
        sn = d[i]
        i += 1
        xm = None
        if op_code == 1:
            xm = d[i]
            i += 1
        params = bytes(d[i : total - 1])

        return cls(
            op_code=op_code,
            type=ptype,
            has_response=has_resp,
            status=status,
            sn=sn,
            xm_op_code=xm,
            params=params,
        )


class OpCode:
    DATA = 1
    GET_TARGET_FEATURE_MAP = 2
    GET_TARGET_INFO = 3
    START_SPEECH = 4
    STOP_SPEECH = 5
    DISCONNECT_CLASSIC_BT = 6
    GET_SYS_INFO = 7
    SET_SYS_INFO = 8
    UPDATE_SYS_INFO = 9
    PHONE_CALL_REQUEST = 10
    NOTIFY_COMMUNICATION_WAY = 11
    FUNCTION = 14
    BATCH = 38
    SET_ADV_INFO = 192
    GET_ADV_INFO = 193
    NOTIFY_ADV_INFO = 194
    SETTINGS_MTU = 209
    REBOOT_DEVICE = 231
    CUSTOM_BASE = 240
    CUSTOM = 255


class AdvType:
    BATTERY_QUANTITY = 0
    DEVICE_NAME = 1
    KEY_SETTINGS = 2
    LED_SETTINGS = 3
    MIC_CHANNEL_SETTINGS = 4
    WORK_MODE = 5
    PRODUCT_MESSAGE = 6
    CONNECTED_TIME = 7
    IN_EAR_CHECK = 8
    LANGUAGE = 9
    ANC_MODE_LIST = 10
    CURRENT_NOISE_MODE = 11


class SysFunc:
    PUBLIC = 0xFF
    BT = 0
    MUSIC = 1
    RTC = 2
    AUX = 3
    FM = 4
    LIGHT = 5
    EQ = 7
    LOW_POWER = 22


class SysAttr:
    BATTERY = 0
    VOLUME = 1
    EQ = 4
    HIGH_AND_BASS = 11
    EQ_PRESET_VALUE = 12
    CURRENT_NOISE_MODE = 13
    ALL_NOISE_MODE = 14
    PHONE_STATUS = 15


def hex_str(data: bytes) -> str:
    return "-".join(f"{b:02X}" for b in data)


def parse_tlv(data: bytes) -> list[tuple[int, bytes]]:
    """Parse a sequence of [L:1B][T:1B][V:L-1 bytes] entries.
    Returns list of (type, value) tuples."""
    out = []
    i = 0
    n = len(data)
    while i < n:
        if i + 1 >= n:
            break
        length = data[i]
        if length < 1 or i + 1 + length > n:
            break
        type_byte = data[i + 1]
        value = bytes(data[i + 2 : i + 1 + length])
        out.append((type_byte, value))
        i += 1 + length
    return out


ADV_TYPE_NAMES = {
    0: "BATTERY_QUANTITY",
    1: "DEVICE_NAME",
    2: "KEY_SETTINGS",
    3: "LED_SETTINGS",
    4: "MIC_CHANNEL_SETTINGS",
    5: "WORK_MODE",
    6: "PRODUCT_MESSAGE",
    7: "CONNECTED_TIME",
    8: "IN_EAR_CHECK",
    9: "LANGUAGE",
    10: "ANC_MODE_LIST",
    11: "CURRENT_NOISE_MODE",
    12: "VOLUME_BALANCE_OR_UNK",
}
