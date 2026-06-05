"""MCU serial frame protocol for R1 main controller -> LED MCU communication.

Frame format:
    AA 55 msg_id seq brightness checksum

Fields:
    - 0xAA 0x55: frame header
    - msg_id: 0~31, matching protocol.MsgID values
    - seq: 0 or 1
    - brightness: 0~255
    - checksum: msg_id ^ seq ^ brightness

This module does NOT depend on pyserial or any real UART driver.
It only provides encode/decode logic for the frame protocol.
"""

from __future__ import annotations

from dataclasses import dataclass

FRAME_HEADER = bytes([0xAA, 0x55])
FRAME_LEN = 6  # header(2) + msg_id(1) + seq(1) + brightness(1) + checksum(1)


@dataclass(frozen=True)
class SerialFrame:
    msg_id: int
    seq: int
    brightness: int


def encode_frame(msg_id: int, seq: int, brightness: int = 200) -> bytes:
    """Encode a serial frame.

    Args:
        msg_id: 0~31.
        seq: 0 or 1.
        brightness: 0~255.

    Returns:
        6-byte frame: AA 55 msg_id seq brightness checksum.
    """
    if not 0 <= msg_id <= 31:
        raise ValueError(f"msg_id must be 0~31, got {msg_id}")
    if seq not in (0, 1):
        raise ValueError(f"seq must be 0 or 1, got {seq}")
    if not 0 <= brightness <= 255:
        raise ValueError(f"brightness must be 0~255, got {brightness}")

    checksum = msg_id ^ seq ^ brightness
    return bytes([0xAA, 0x55, msg_id, seq, brightness, checksum])


def decode_frame(frame: bytes) -> SerialFrame:
    """Decode a serial frame.

    Args:
        frame: raw bytes, must be exactly 6 bytes.

    Returns:
        SerialFrame with decoded fields.

    Raises:
        ValueError: on any validation failure.
    """
    if not isinstance(frame, (bytes, bytearray)):
        raise ValueError(f"frame must be bytes, got {type(frame).__name__}")
    if len(frame) != FRAME_LEN:
        raise ValueError(f"frame length must be {FRAME_LEN}, got {len(frame)}")
    if frame[0] != 0xAA or frame[1] != 0x55:
        raise ValueError(
            f"frame header must be AA 55, got {frame[0]:02X} {frame[1]:02X}"
        )

    msg_id = frame[2]
    seq = frame[3]
    brightness = frame[4]
    checksum = frame[5]

    if not 0 <= msg_id <= 31:
        raise ValueError(f"msg_id must be 0~31, got {msg_id}")
    if seq not in (0, 1):
        raise ValueError(f"seq must be 0 or 1, got {seq}")
    if not 0 <= brightness <= 255:
        raise ValueError(f"brightness must be 0~255, got {brightness}")

    expected = msg_id ^ seq ^ brightness
    if checksum != expected:
        raise ValueError(
            f"checksum mismatch: expected {expected}, got {checksum}"
        )

    return SerialFrame(msg_id=msg_id, seq=seq, brightness=brightness)
