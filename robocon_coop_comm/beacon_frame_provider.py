"""Frame provider abstraction for beacon image sources.

VirtualBeaconFrameProvider generates virtual LED beacon images using the
existing beacon_image module.  Real hardware replaces this with a camera-based provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .beacon_types import BeaconFrame


class BeaconFrameProvider(ABC):
    """Abstract base class for beacon frame sources."""

    @abstractmethod
    def get_frame(self) -> BeaconFrame:
        """Return the current frame."""


class VirtualBeaconFrameProvider(BeaconFrameProvider):
    """Generates virtual beacon images via beacon_image.draw_virtual_beacon."""

    def __init__(self, msg_id: int = 0, seq: int = 0) -> None:
        self._msg_id = msg_id
        self._seq = seq
        self._frame_id = 0

    def update(self, msg_id: int, seq: int) -> None:
        """Update the beacon state for subsequent frames."""
        self._msg_id = msg_id
        self._seq = seq

    def get_frame(self) -> BeaconFrame:
        """Generate and return a virtual beacon frame."""
        # Import here to allow module-level import without requiring cv2
        from .beacon_image import draw_virtual_beacon

        img = draw_virtual_beacon(self._msg_id, self._seq)
        frame = BeaconFrame(
            image=img,
            source="virtual_beacon",
            frame_id=self._frame_id,
        )
        self._frame_id += 1
        return frame
