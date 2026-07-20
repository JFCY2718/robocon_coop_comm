"""Tests for the newest-frame-only acquisition wrapper."""

from __future__ import annotations

from collections import deque
import threading
import time

import numpy as np

from robocon_coop_comm.beacon_types import BeaconFrame
from robocon_coop_comm.latest_frame_provider import LatestFrameProvider


class _QueuedProvider:
    def __init__(self) -> None:
        self.frames: deque[BeaconFrame] = deque()
        self.condition = threading.Condition()
        self.closed = False
        self.opened = False

    def open(self) -> None:
        self.opened = True

    def push(self, frame_id: int) -> None:
        with self.condition:
            self.frames.append(
                BeaconFrame(np.zeros((2, 2), dtype=np.uint8), "test", frame_id)
            )
            self.condition.notify()

    def get_frame(self) -> BeaconFrame | None:
        with self.condition:
            self.condition.wait_for(lambda: self.frames or self.closed, timeout=0.2)
            if self.frames:
                return self.frames.popleft()
            return None

    def close(self) -> None:
        with self.condition:
            self.closed = True
            self.condition.notify_all()


def test_returns_a_newly_published_frame() -> None:
    source = _QueuedProvider()
    latest = LatestFrameProvider(source, wait_timeout_s=0.2)
    latest.open()
    source.push(7)
    frame = latest.get_frame()
    latest.close()
    assert source.opened
    assert frame is not None and frame.frame_id == 7


def test_replaces_unconsumed_frames_with_newest() -> None:
    source = _QueuedProvider()
    latest = LatestFrameProvider(source, wait_timeout_s=0.3)
    latest.open()
    source.push(1)
    source.push(2)
    source.push(3)
    deadline = time.monotonic() + 0.3
    while latest.dropped_frames < 2 and time.monotonic() < deadline:
        time.sleep(0.001)
    frame = latest.get_frame()
    latest.close()
    assert frame is not None and frame.frame_id == 3
    assert latest.dropped_frames >= 2


def test_timeout_returns_none() -> None:
    latest = LatestFrameProvider(_QueuedProvider(), wait_timeout_s=0.02)
    latest.open()
    assert latest.get_frame() is None
    latest.close()
