"""LED MCU client: sends encoded frames to the LED beacon MCU via a serial transport.

This is the R1 main controller -> R1 LED MCU internal wired link.
It is NOT R1/R2 communication.
"""

from __future__ import annotations

from . import serial_frame
from .serial_transport import SerialTransport


class LedMcuClient:
    """High-level client for sending beacon frames to the LED MCU.

    Args:
        transport: a SerialTransport instance (MemorySerialTransport, PySerialTransport, etc.)
        default_brightness: brightness used when send() is called without an explicit value.
    """

    def __init__(
        self, transport: SerialTransport, default_brightness: int = 200
    ) -> None:
        self.transport = transport
        self.default_brightness = default_brightness

    def send(
        self, msg_id: int, seq: int, brightness: int | None = None
    ) -> bytes:
        """Encode a beacon frame and write it to the transport.

        Args:
            msg_id: 0~31.
            seq: 0 or 1.
            brightness: 0~255, defaults to self.default_brightness.

        Returns:
            The 6-byte frame that was sent.

        Raises:
            ValueError: on invalid msg_id / seq / brightness.
            IOError: if transport.write() writes fewer bytes than expected.
        """
        bri = self.default_brightness if brightness is None else brightness
        frame = serial_frame.encode_frame(msg_id, seq, bri)
        written = self.transport.write(frame)
        if written != len(frame):
            raise IOError(
                f"short write: expected {len(frame)} bytes, wrote {written}"
            )
        return frame
