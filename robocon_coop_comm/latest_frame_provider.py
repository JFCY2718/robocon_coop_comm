"""Single-slot asynchronous frame provider for low-latency vision loops."""

from __future__ import annotations

import threading
import time

from .beacon_types import BeaconFrame


class LatestFrameProvider:
    """Continuously grab frames and expose only the newest unconsumed frame.

    Camera acquisition runs in a daemon thread.  When processing falls behind,
    the pending frame is replaced instead of building an old-frame queue.
    """

    def __init__(self, source, *, wait_timeout_s: float = 0.5) -> None:
        if wait_timeout_s <= 0:
            raise ValueError("wait_timeout_s must be positive")
        self.source = source
        self.wait_timeout_s = float(wait_timeout_s)
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest: BeaconFrame | None = None
        self._has_unconsumed = False
        self._error: BaseException | None = None
        self.dropped_frames = 0

    def open(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        if hasattr(self.source, "open"):
            self.source.open()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._grab_loop,
            name="latest-frame-grabber",
            daemon=True,
        )
        self._thread.start()

    def get_frame(self) -> BeaconFrame | None:
        if self._thread is None:
            self.open()
        deadline = time.monotonic() + self.wait_timeout_s
        with self._condition:
            while not self._has_unconsumed and not self._stop.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)
            if self._error is not None:
                raise RuntimeError("background frame grab failed") from self._error
            if not self._has_unconsumed:
                return None
            frame = self._latest
            self._has_unconsumed = False
            return frame

    def close(self) -> None:
        self._stop.set()
        if hasattr(self.source, "close"):
            self.source.close()
        with self._condition:
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=max(0.2, self.wait_timeout_s + 0.1))
        self._thread = None

    def _grab_loop(self) -> None:
        try:
            while not self._stop.is_set():
                frame = self.source.get_frame()
                if frame is None:
                    continue
                with self._condition:
                    if self._has_unconsumed:
                        self.dropped_frames += 1
                    self._latest = frame
                    self._has_unconsumed = True
                    self._condition.notify()
        except BaseException as exc:
            with self._condition:
                self._error = exc
                self._stop.set()
                self._condition.notify_all()
