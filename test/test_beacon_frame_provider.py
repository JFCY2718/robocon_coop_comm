"""Tests for VirtualBeaconFrameProvider."""

from __future__ import annotations

import pytest

from robocon_coop_comm.beacon_frame_provider import VirtualBeaconFrameProvider

# Skip if OpenCV not available
cv2 = pytest.importorskip("cv2")


class TestVirtualBeaconFrameProvider:
    def test_generates_frame(self) -> None:
        p = VirtualBeaconFrameProvider(msg_id=4, seq=1)
        frame = p.get_frame()
        assert frame.source == "virtual_beacon"
        assert frame.image is not None

    def test_frame_id_increments(self) -> None:
        p = VirtualBeaconFrameProvider()
        f1 = p.get_frame()
        f2 = p.get_frame()
        assert f2.frame_id == f1.frame_id + 1

    def test_update_changes_output(self) -> None:
        p = VirtualBeaconFrameProvider(msg_id=0, seq=0)
        f1 = p.get_frame()
        p.update(msg_id=4, seq=1)
        f2 = p.get_frame()
        # Frame IDs should be different
        assert f2.frame_id != f1.frame_id
