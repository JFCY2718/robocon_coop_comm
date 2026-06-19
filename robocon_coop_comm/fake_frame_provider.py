"""Fake frame provider for testing without hardware.

Provides FakeFrameProvider: generates synthetic grayscale frames with
simulated 3-LED blobs at configurable positions.  Useful for unit tests
and CI where no Hikrobot SDK or real camera is available.
"""

from __future__ import annotations

from .beacon_types import BeaconFrame
from .beacon_frame_provider import BeaconFrameProvider


def _require_np():
    import numpy as np  # type: ignore

    return np


class FakeFrameProvider(BeaconFrameProvider):
    """Generates fake grayscale frames with synthetic LED blobs.

    Each "LED" is rendered as a bright or dark circle at a known position.
    The three ROI positions returned by ``roi_points`` match exactly where
    the blobs are drawn, so ``ThreeLedRoiDecoder`` can decode them.

    Usage::

        provider = FakeFrameProvider(msg_id=4, seq=1)
        frame = provider.get_frame()
        # frame.image is a (height, width) numpy uint8 array
        # provider.roi_points gives [(x0,y0), (x1,y1), (x2,y2)]
    """

    def __init__(
        self,
        msg_id: int = 0,
        seq: int = 0,
        width: int = 640,
        height: int = 480,
        led_radius: int = 12,
        led_on_val: int = 220,
        led_off_val: int = 25,
        noise_std: float = 3.0,
    ) -> None:
        self._msg_id = msg_id
        self._seq = seq
        self._width = width
        self._height = height
        self._led_radius = led_radius
        self._led_on_val = led_on_val
        self._led_off_val = led_off_val
        self._noise_std = noise_std
        self._frame_id = 0

        # Fixed ROI positions: three LEDs horizontally spaced.
        cx = width // 2
        cy = height // 2
        gap = led_radius * 5
        self.roi_points: list[tuple[int, int]] = [
            (cx - gap, cy),  # D0
            (cx, cy),        # D1
            (cx + gap, cy),  # D2
        ]

    # ------------------------------------------------------------------
    # state control
    # ------------------------------------------------------------------

    def update(self, msg_id: int, seq: int) -> None:
        self._msg_id = msg_id
        self._seq = seq

    # ------------------------------------------------------------------
    # BeaconFrameProvider interface
    # ------------------------------------------------------------------

    def get_frame(self) -> BeaconFrame:
        np = _require_np()
        img = np.full(
            (self._height, self._width), 10, dtype=np.uint8
        )

        # LED bits from msg_id
        d0 = (self._msg_id >> 0) & 1
        d1 = (self._msg_id >> 1) & 1
        d2 = (self._msg_id >> 2) & 1
        bit_values = [d0, d1, d2]

        rr = self._led_radius
        for (cx, cy), bit in zip(self.roi_points, bit_values):
            val = self._led_on_val if bit else self._led_off_val
            y_grid, x_grid = np.ogrid[: self._height, : self._width]
            mask = (x_grid - cx) ** 2 + (y_grid - cy) ** 2 <= rr**2
            img[mask] = val

        # Add Gaussian noise
        noise = np.random.default_rng(42 + self._frame_id).normal(
            0, self._noise_std, (self._height, self._width)
        )
        img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)

        frame = BeaconFrame(
            image=img,
            source="fake_camera",
            frame_id=self._frame_id,
        )
        self._frame_id += 1
        return frame
