"""Versioned R1-to-Beacon-MCU UART frames for the four-light protocol."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


FRAME_HEADER = 0xBD
ACK_HEADER = 0xBE
VERSION = 0x02
FRAME_LENGTH = 6


class AckStatus(IntEnum):
    OK = 0
    BAD_VERSION = 1
    BAD_STATE = 2
    BAD_CRC = 3


@dataclass(frozen=True)
class BeaconCommand:
    state_id: int
    counter: int
    brightness: int


@dataclass(frozen=True)
class BeaconAck:
    state_id: int
    counter: int
    status: AckStatus


def crc8(data: bytes) -> int:
    """CRC-8/ATM (poly 0x07, init 0x00) over *data*."""
    crc = 0
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def build_command(state_id: int, counter: int, brightness: int = 255) -> bytes:
    if not 0 <= int(state_id) <= 15:
        raise ValueError("state_id must be in 0..15")
    prefix = bytes((FRAME_HEADER, VERSION, state_id, counter & 0xFF, brightness & 0xFF))
    return prefix + bytes((crc8(prefix),))


def parse_command(frame: bytes) -> BeaconCommand:
    _validate_frame(frame, FRAME_HEADER)
    if frame[1] != VERSION:
        raise ValueError("bad_version")
    if frame[2] > 15:
        raise ValueError("bad_state")
    return BeaconCommand(frame[2], frame[3], frame[4])


def build_ack(state_id: int, counter: int, status: int | AckStatus = AckStatus.OK) -> bytes:
    prefix = bytes((ACK_HEADER, VERSION, state_id & 0xFF, counter & 0xFF, int(status) & 0xFF))
    return prefix + bytes((crc8(prefix),))


def parse_ack(frame: bytes) -> BeaconAck:
    _validate_frame(frame, ACK_HEADER)
    if frame[1] != VERSION:
        raise ValueError("bad_version")
    try:
        status = AckStatus(frame[4])
    except ValueError as exc:
        raise ValueError("bad_status") from exc
    return BeaconAck(frame[2], frame[3], status)


def _validate_frame(frame: bytes, header: int) -> None:
    if len(frame) != FRAME_LENGTH:
        raise ValueError("bad_length")
    if frame[0] != header:
        raise ValueError("bad_header")
    if frame[5] != crc8(frame[:5]):
        raise ValueError("bad_crc")
