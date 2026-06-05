"""LED MCU simulator: Python model of the Arduino LED beacon MCU firmware.

Parses a byte stream the same way the Arduino firmware does:
    - Scans for frame header 0xAA 0x55
    - Reads 4 more bytes (msg_id, seq, brightness, checksum)
    - Validates and decodes using serial_frame.decode_frame()
    - Generates LED bits matching protocol.py rules

This is a simulation of R1 internal wired communication (main controller -> LED MCU).
It is NOT R1/R2 communication.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import protocol, serial_frame


@dataclass(frozen=True)
class LedMcuUpdate:
    """Result of successfully decoding one frame."""

    msg_id: int
    seq: int
    brightness: int
    led_bits: dict[str, int]
    ack: str = "OK"


@dataclass(frozen=True)
class LedMcuError:
    """Result of a failed frame decode."""

    reason: str
    raw: bytes | None = None


def _make_led_bits(msg_id: int, seq: int) -> dict[str, int]:
    """Generate LED bits matching protocol.encode_led_bits logic."""
    encoded = protocol.encode_led_bits(msg_id, seq)
    return encoded.bits


class LedMcuSimulator:
    """Simulates the Arduino LED beacon MCU firmware in Python.

    Usage::

        sim = LedMcuSimulator()
        results = sim.feed(frame_bytes)
        for r in results:
            if isinstance(r, LedMcuUpdate):
                print(r.led_bits)
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[LedMcuUpdate | LedMcuError]:
        """Feed raw bytes into the simulator.

        Returns a list of results (LedMcuUpdate for valid frames,
        LedMcuError for invalid ones).  Partial frames are buffered
        until enough bytes arrive.
        """
        self._buf.extend(data)
        results: list[LedMcuUpdate | LedMcuError] = []

        while True:
            result = self._try_parse_one()
            if result is None:
                break
            results.append(result)

        return results

    def _try_parse_one(self) -> LedMcuUpdate | LedMcuError | None:
        """Try to parse one frame from the buffer.

        Returns None if not enough data yet.
        """
        # Scan for header byte 0xAA
        while len(self._buf) >= 2 and self._buf[0] != 0xAA:
            self._buf.pop(0)

        if len(self._buf) < serial_frame.FRAME_LEN:
            return None

        # Check second header byte
        if self._buf[1] != 0x55:
            # Not a valid header - discard first byte and resync
            self._buf.pop(0)
            return self._try_parse_one()

        # We have at least FRAME_LEN bytes starting with AA 55
        raw = bytes(self._buf[: serial_frame.FRAME_LEN])
        self._buf = self._buf[serial_frame.FRAME_LEN :]

        try:
            frame = serial_frame.decode_frame(raw)
        except ValueError as e:
            return LedMcuError(reason=str(e), raw=raw)

        led_bits = _make_led_bits(frame.msg_id, frame.seq)
        return LedMcuUpdate(
            msg_id=frame.msg_id,
            seq=frame.seq,
            brightness=frame.brightness,
            led_bits=led_bits,
        )
