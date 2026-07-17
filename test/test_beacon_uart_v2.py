from __future__ import annotations

import pytest

from robocon_coop_comm.beacon_uart_v2 import (
    ACK_HEADER,
    FRAME_HEADER,
    VERSION,
    AckStatus,
    build_ack,
    build_command,
    crc8,
    parse_ack,
    parse_command,
)


def test_command_golden_vector() -> None:
    frame = build_command(4, 0x2A, 200)
    assert frame[:5] == bytes((FRAME_HEADER, VERSION, 4, 0x2A, 200))
    assert frame[5] == crc8(frame[:5])
    assert parse_command(frame).state_id == 4


def test_ack_round_trip() -> None:
    frame = build_ack(15, 255, AckStatus.OK)
    assert frame[0] == ACK_HEADER
    ack = parse_ack(frame)
    assert (ack.state_id, ack.counter, ack.status) == (15, 255, AckStatus.OK)


def test_crc_corruption_is_rejected() -> None:
    frame = bytearray(build_command(7, 3))
    frame[2] ^= 1
    with pytest.raises(ValueError, match="bad_crc"):
        parse_command(bytes(frame))


def test_invalid_state_is_not_encoded() -> None:
    with pytest.raises(ValueError, match="0..15"):
        build_command(16, 0)
