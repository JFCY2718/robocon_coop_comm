"""Tests for BeaconStabilizer."""

from __future__ import annotations

import pytest

from robocon_coop_comm.beacon_stabilizer import BeaconStabilizer
from robocon_coop_comm.beacon_types import DecodedBeacon


def _make_beacon(msg_id: int, seq: int, valid: bool = True) -> DecodedBeacon:
    return DecodedBeacon(
        msg_id=msg_id,
        msg_name=f"MSG_{msg_id}",
        seq=seq,
        valid=valid,
        confidence=0.9,
        source="test",
    )


class TestBeaconStabilizer:
    def test_three_frames_stable(self) -> None:
        s = BeaconStabilizer(min_stable_frames=3)
        r1 = s.update(_make_beacon(4, 1))
        r2 = s.update(_make_beacon(4, 1))
        r3 = s.update(_make_beacon(4, 1))

        assert r1.valid is False
        assert r2.valid is False
        assert r3.valid is True
        assert r3.reason == "stable"

    def test_first_two_frames_not_stable(self) -> None:
        s = BeaconStabilizer(min_stable_frames=3)
        r1 = s.update(_make_beacon(2, 0))
        r2 = s.update(_make_beacon(2, 0))

        assert r1.valid is False
        assert "waiting_for_stability" in r1.reason
        assert r2.valid is False
        assert "waiting_for_stability" in r2.reason

    def test_msg_id_change_resets_count(self) -> None:
        s = BeaconStabilizer(min_stable_frames=3)
        s.update(_make_beacon(4, 1))
        s.update(_make_beacon(4, 1))
        # Change msg_id
        s.update(_make_beacon(5, 1))
        s.update(_make_beacon(5, 1))
        r = s.update(_make_beacon(5, 1))

        assert r.valid is True
        assert r.msg_id == 5

    def test_seq_change_resets_count(self) -> None:
        s = BeaconStabilizer(min_stable_frames=3)
        s.update(_make_beacon(4, 0))
        s.update(_make_beacon(4, 0))
        # Change seq
        s.update(_make_beacon(4, 1))
        s.update(_make_beacon(4, 1))
        r = s.update(_make_beacon(4, 1))

        assert r.valid is True
        assert r.seq == 1

    def test_invalid_input_does_not_stabilize(self) -> None:
        s = BeaconStabilizer(min_stable_frames=3)
        for _ in range(5):
            r = s.update(_make_beacon(4, 1, valid=False))
            assert r.valid is False
            assert r.reason == "invalid_input"

    def test_min_stable_frames_1(self) -> None:
        s = BeaconStabilizer(min_stable_frames=1)
        r = s.update(_make_beacon(4, 1))
        assert r.valid is True
        assert r.reason == "stable"

    def test_invalid_min_stable_frames(self) -> None:
        with pytest.raises(ValueError, match="min_stable_frames"):
            BeaconStabilizer(min_stable_frames=0)
