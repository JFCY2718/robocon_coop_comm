"""Tests for beacon type definitions."""

from __future__ import annotations

from robocon_coop_comm.beacon_types import DecodedBeacon, msg_name_from_id


class TestMsgNameFromId:
    def test_known_id_0(self) -> None:
        assert msg_name_from_id(0) == "IDLE"

    def test_known_id_4(self) -> None:
        assert msg_name_from_id(4) == "INSERT_ALLOWED"

    def test_known_id_31(self) -> None:
        assert msg_name_from_id(31) == "TEST"

    def test_unknown_id(self) -> None:
        assert msg_name_from_id(99) == "UNKNOWN_99"


class TestDecodedBeacon:
    def test_default_source(self) -> None:
        b = DecodedBeacon(
            msg_id=0, msg_name="IDLE", seq=0, valid=True, confidence=1.0
        )
        assert b.source == "unknown"
        assert b.reason == ""
        assert b.raw_bits is None

    def test_fields(self) -> None:
        b = DecodedBeacon(
            msg_id=4,
            msg_name="INSERT_ALLOWED",
            seq=1,
            valid=True,
            confidence=0.95,
            source="virtual_beacon",
            reason="stable",
            raw_bits={"REF": 1, "D0": 0, "D1": 0, "D2": 1, "D3": 0, "D4": 0, "SEQ": 1, "PAR": 0},
        )
        assert b.msg_id == 4
        assert b.msg_name == "INSERT_ALLOWED"
        assert b.seq == 1
        assert b.valid is True
        assert b.confidence == 0.95
        assert b.raw_bits is not None
        assert b.raw_bits["D2"] == 1
