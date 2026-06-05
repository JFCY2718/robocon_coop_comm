"""Tests for MCU serial frame encode/decode."""

from __future__ import annotations

import pytest

from robocon_coop_comm.serial_frame import SerialFrame, decode_frame, encode_frame


class TestEncodeFrame:
    def test_basic(self) -> None:
        frame = encode_frame(4, 1, 200)
        assert frame == bytes([0xAA, 0x55, 4, 1, 200, 4 ^ 1 ^ 200])

    def test_msg_id_zero(self) -> None:
        frame = encode_frame(0, 0, 100)
        assert frame[2] == 0
        assert frame[5] == 0 ^ 0 ^ 100

    def test_msg_id_31(self) -> None:
        frame = encode_frame(31, 1, 255)
        assert frame[2] == 31
        assert frame[5] == 31 ^ 1 ^ 255

    def test_seq_zero(self) -> None:
        frame = encode_frame(10, 0, 128)
        assert frame[3] == 0

    def test_seq_one(self) -> None:
        frame = encode_frame(10, 1, 128)
        assert frame[3] == 1

    def test_brightness_zero(self) -> None:
        frame = encode_frame(5, 0, 0)
        assert frame[4] == 0
        assert frame[5] == 5 ^ 0 ^ 0

    def test_brightness_255(self) -> None:
        frame = encode_frame(5, 1, 255)
        assert frame[4] == 255
        assert frame[5] == 5 ^ 1 ^ 255

    def test_default_brightness(self) -> None:
        frame = encode_frame(1, 0)
        assert frame[4] == 200

    def test_invalid_msg_id_negative(self) -> None:
        with pytest.raises(ValueError, match="msg_id"):
            encode_frame(-1, 0, 200)

    def test_invalid_msg_id_too_large(self) -> None:
        with pytest.raises(ValueError, match="msg_id"):
            encode_frame(32, 0, 200)

    def test_invalid_seq(self) -> None:
        with pytest.raises(ValueError, match="seq"):
            encode_frame(0, 2, 200)

    def test_invalid_brightness_negative(self) -> None:
        with pytest.raises(ValueError, match="brightness"):
            encode_frame(0, 0, -1)

    def test_invalid_brightness_too_large(self) -> None:
        with pytest.raises(ValueError, match="brightness"):
            encode_frame(0, 0, 256)


class TestDecodeFrame:
    def test_basic(self) -> None:
        raw = bytes([0xAA, 0x55, 4, 1, 200, 4 ^ 1 ^ 200])
        f = decode_frame(raw)
        assert f == SerialFrame(msg_id=4, seq=1, brightness=200)

    def test_msg_id_zero(self) -> None:
        raw = encode_frame(0, 0, 100)
        f = decode_frame(raw)
        assert f.msg_id == 0
        assert f.seq == 0
        assert f.brightness == 100

    def test_msg_id_31(self) -> None:
        raw = encode_frame(31, 1, 255)
        f = decode_frame(raw)
        assert f.msg_id == 31
        assert f.seq == 1
        assert f.brightness == 255

    def test_seq_zero(self) -> None:
        raw = encode_frame(10, 0, 50)
        f = decode_frame(raw)
        assert f.seq == 0

    def test_seq_one(self) -> None:
        raw = encode_frame(10, 1, 50)
        f = decode_frame(raw)
        assert f.seq == 1

    def test_brightness_zero(self) -> None:
        raw = encode_frame(5, 0, 0)
        f = decode_frame(raw)
        assert f.brightness == 0

    def test_brightness_255(self) -> None:
        raw = encode_frame(5, 1, 255)
        f = decode_frame(raw)
        assert f.brightness == 255

    def test_roundtrip(self) -> None:
        for mid in (0, 1, 15, 31):
            for seq in (0, 1):
                for bri in (0, 128, 255):
                    f = decode_frame(encode_frame(mid, seq, bri))
                    assert f.msg_id == mid
                    assert f.seq == seq
                    assert f.brightness == bri

    def test_invalid_header_first_byte(self) -> None:
        with pytest.raises(ValueError, match="header"):
            decode_frame(bytes([0xAB, 0x55, 0, 0, 0, 0]))

    def test_invalid_header_second_byte(self) -> None:
        with pytest.raises(ValueError, match="header"):
            decode_frame(bytes([0xAA, 0x56, 0, 0, 0, 0]))

    def test_invalid_length_too_short(self) -> None:
        with pytest.raises(ValueError, match="length"):
            decode_frame(bytes([0xAA, 0x55, 0, 0, 0]))

    def test_invalid_length_too_long(self) -> None:
        with pytest.raises(ValueError, match="length"):
            decode_frame(bytes([0xAA, 0x55, 0, 0, 0, 0, 0]))

    def test_invalid_msg_id_in_frame(self) -> None:
        # header ok, msg_id=32 (invalid), seq=0, brightness=0, checksum=32
        with pytest.raises(ValueError, match="msg_id"):
            decode_frame(bytes([0xAA, 0x55, 32, 0, 0, 32]))

    def test_invalid_seq_in_frame(self) -> None:
        # header ok, msg_id=0, seq=2 (invalid), brightness=0, checksum=2
        with pytest.raises(ValueError, match="seq"):
            decode_frame(bytes([0xAA, 0x55, 0, 2, 0, 2]))

    def test_invalid_checksum(self) -> None:
        # msg_id=4, seq=1, brightness=200, correct checksum=4^1^200=205, use 0 instead
        with pytest.raises(ValueError, match="checksum"):
            decode_frame(bytes([0xAA, 0x55, 4, 1, 200, 0]))

    def test_invalid_type(self) -> None:
        with pytest.raises(ValueError, match="bytes"):
            decode_frame("not bytes")  # type: ignore[arg-type]
