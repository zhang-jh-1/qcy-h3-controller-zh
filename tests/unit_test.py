import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

"""不依赖耳机的协议单元测试。"""
import asyncio

from h3_device import (
    ANCMode,
    EQ_BANDS_FREQS,
    EQ_PRESET_IDS,
    EQ_PRESET_NAMES,
    H3Device,
)
from rcsp import FOOTER, HEADER, AdvType, OpCode, Packet, parse_tlv


def test_packet_roundtrip():
    pkt = Packet(op_code=OpCode.CUSTOM, params=bytes([0xFE, 0x01, 0x22]))
    raw = pkt.encode()
    assert raw[:3] == HEADER
    assert raw[-1] == FOOTER
    # 长度字段 = sn(1) + 参数(3)
    assert raw[5:7] == b"\x00\x04"
    decoded = Packet.decode(raw)
    assert decoded is not None
    assert decoded.op_code == OpCode.CUSTOM
    assert decoded.type == 1
    assert decoded.params == bytes([0xFE, 0x01, 0x22])


def test_response_decode():
    # 设备响应：flag=0x00（bit7=0 表示响应）, opCode=0xFF,
    # 长度=5（status 1 + sn 1 + 参数 3）, status=0, sn=7, 参数 22 01 00
    raw = HEADER + bytes([0x00, 0xFF, 0x00, 0x05, 0x00, 0x07, 0x22, 0x01, 0x00, FOOTER])
    pkt = Packet.decode(raw)
    assert pkt is not None
    assert pkt.type == 0
    assert pkt.status == 0
    assert pkt.sn == 7
    assert pkt.params == bytes([0x22, 0x01, 0x00])


def test_tlv():
    data = bytes([0x02, AdvType.BATTERY_QUANTITY, 87, 0x02, AdvType.WORK_MODE, 0x02])
    out = parse_tlv(data)
    assert out[0] == (AdvType.BATTERY_QUANTITY, b"\x57")
    assert out[1] == (AdvType.WORK_MODE, b"\x02")


def test_anc_decode():
    assert ANCMode.from_params(bytes([0x17, 0x03, 0x02, 0x00, 0x00])) == 0
    assert ANCMode.from_params(bytes([0x17, 0x03, 0x03, 0x01, 0x04])) == 1
    assert ANCMode.from_params(bytes([0x17, 0x03, 0x01, 0x01, 0x00])) == 2
    assert ANCMode.from_params(bytes([0x17, 0x03, 0x01, 0x01, 0x02])) == 4
    assert ANCMode.from_params(bytes([0x17, 0x03, 0x01, 0x05, 0x00])) == 5


class CaptureDevice(H3Device):
    def __init__(self):
        super().__init__("00:00:00:00:00:00")
        self.last = None

    async def send(self, pkt, timeout=2.0):
        self.last = pkt
        return Packet(op_code=pkt.op_code, type=0, sn=pkt.sn, params=b"\x00")


def test_eq_payload():
    dev = CaptureDevice()
    offsets = [0, 150, 150, 100, 0, 100, 200, 200, 150, 100]
    asyncio.run(dev.set_eq(offsets, preset_id=0x02))
    params = dev.last.params
    assert params[0] == 0x22
    assert params[1] == 73  # 3 字节头 + 10×7 字节
    assert params[2] == 0x02
    assert params[3] == 0x70
    assert params[4] == 0xFE
    bands = params[5:]
    assert len(bands) == 70
    for i, freq in enumerate(EQ_BANDS_FREQS):
        base = i * 7
        got_freq = int.from_bytes(bands[base:base + 2], "little")
        got_gain = int.from_bytes(bands[base + 2:base + 4], "little", signed=True)
        assert got_freq == freq
        assert got_gain == offsets[i]


def test_eq_parse():
    dev = CaptureDevice()
    bands = bytearray()
    for i, freq in enumerate(EQ_BANDS_FREQS):
        bands += freq.to_bytes(2, "little")
        bands += (i * 50).to_bytes(2, "little", signed=True)
        bands += (120).to_bytes(2, "little")
        bands += bytes([2])
    data = bytes([0x00, 0x70, 0xFE]) + bytes(bands)
    params = bytes([0x22, len(data)]) + data

    async def fake_send(pkt, timeout=2.0):
        return Packet(op_code=pkt.op_code, type=0, sn=1, params=params)

    dev.send = fake_send
    offsets = asyncio.run(dev.get_eq())
    assert offsets == [i * 50 for i in range(10)]


def test_presets_chinese():
    assert EQ_PRESET_NAMES == ["自定义", "默认", "流行", "重低音", "摇滚", "柔和", "古典"]
    assert EQ_PRESET_IDS == [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06]


if __name__ == "__main__":
    test_packet_roundtrip()
    test_response_decode()
    test_tlv()
    test_anc_decode()
    test_eq_payload()
    test_eq_parse()
    test_presets_chinese()
    print("ALL UNIT TESTS PASSED")
