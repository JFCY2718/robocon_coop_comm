"""Tests for BeaconDecoder."""

from __future__ import annotations

import pytest

from robocon_coop_comm.beacon_decoder import BeaconDecoder
from robocon_coop_comm.beacon_frame_provider import VirtualBeaconFrameProvider

cv2 = pytest.importorskip("cv2")


class TestBeaconDecoder:
    def test_decode_msg_id_4(self) -> None:
        provider = VirtualBeaconFrameProvider(msg_id=4, seq=1)
        decoder = BeaconDecoder()
        frame = provider.get_frame()
        result = decoder.decode(frame)

        assert result.valid is True
        assert result.msg_id == 4
        assert result.msg_name == "INSERT_ALLOWED"
        assert result.seq == 1
        assert result.confidence > 0

    def test_decode_msg_id_2(self) -> None:
        provider = VirtualBeaconFrameProvider(msg_id=2, seq=1)
        decoder = BeaconDecoder()
        frame = provider.get_frame()
        result = decoder.decode(frame)

        assert result.valid is True
        assert result.msg_id == 2
        assert result.msg_name == "R1_ROD_CLAMPED"

    def test_raw_bits_present(self) -> None:
        provider = VirtualBeaconFrameProvider(msg_id=4, seq=1)
        decoder = BeaconDecoder()
        frame = provider.get_frame()
        result = decoder.decode(frame)

        assert result.raw_bits is not None
        assert "REF" in result.raw_bits
        assert "D0" in result.raw_bits
        assert "D1" in result.raw_bits
        assert "D2" in result.raw_bits
        assert "D3" in result.raw_bits
        assert "D4" in result.raw_bits
        assert "SEQ" in result.raw_bits
        assert "PAR" in result.raw_bits

    def test_msg_name_correct(self) -> None:
        provider = VirtualBeaconFrameProvider(msg_id=7, seq=0)
        decoder = BeaconDecoder()
        frame = provider.get_frame()
        result = decoder.decode(frame)

        assert result.msg_name == "R1_IN_MF"

    def test_decode_zero(self) -> None:
        provider = VirtualBeaconFrameProvider(msg_id=0, seq=0)
        decoder = BeaconDecoder()
        frame = provider.get_frame()
        result = decoder.decode(frame)

        assert result.valid is True
        assert result.msg_id == 0
        assert result.msg_name == "IDLE"
