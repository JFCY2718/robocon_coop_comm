"""Tests for LedMcuClient."""

from __future__ import annotations

import pytest

from robocon_coop_comm.led_mcu_client import LedMcuClient
from robocon_coop_comm.serial_frame import encode_frame
from robocon_coop_comm.serial_transport import MemorySerialTransport


class _ShortWriteTransport(MemorySerialTransport):
    """A transport that always writes fewer bytes than requested."""

    def write(self, data: bytes) -> int:
        # Write only 1 byte regardless of input length
        super().write(data[:1])
        return 1


class TestLedMcuClient:
    def test_send_basic(self) -> None:
        t = MemorySerialTransport()
        client = LedMcuClient(t)
        frame = client.send(4, 1, 200)
        assert frame == encode_frame(4, 1, 200)
        assert t.get_written_data() == frame

    def test_default_brightness(self) -> None:
        t = MemorySerialTransport()
        client = LedMcuClient(t, default_brightness=128)
        frame = client.send(2, 0)
        assert frame == encode_frame(2, 0, 128)

    def test_brightness_override(self) -> None:
        t = MemorySerialTransport()
        client = LedMcuClient(t, default_brightness=128)
        frame = client.send(2, 0, brightness=255)
        assert frame == encode_frame(2, 0, 255)

    def test_invalid_msg_id_raises(self) -> None:
        t = MemorySerialTransport()
        client = LedMcuClient(t)
        with pytest.raises(ValueError, match="msg_id"):
            client.send(32, 0)

    def test_invalid_seq_raises(self) -> None:
        t = MemorySerialTransport()
        client = LedMcuClient(t)
        with pytest.raises(ValueError, match="seq"):
            client.send(0, 2)

    def test_invalid_brightness_raises(self) -> None:
        t = MemorySerialTransport()
        client = LedMcuClient(t)
        with pytest.raises(ValueError, match="brightness"):
            client.send(0, 0, brightness=256)

    def test_short_write_raises_ioerror(self) -> None:
        t = _ShortWriteTransport()
        client = LedMcuClient(t)
        with pytest.raises(IOError, match="short write"):
            client.send(4, 1, 200)
