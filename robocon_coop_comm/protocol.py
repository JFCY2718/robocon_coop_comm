"""LED optical beacon protocol for R1/R2 cooperation.

Protocol layout:
    REF D0 D1 D2 D3 D4 SEQ PAR

- REF: always on, used as a brightness reference.
- D0-D4: 5-bit message id, D0 is LSB.
- SEQ: toggles when a new event is emitted.
- PAR: even parity bit. The XOR of D0-D4, SEQ and PAR must be 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Mapping

LED_NAMES: tuple[str, ...] = ("REF", "D0", "D1", "D2", "D3", "D4", "SEQ", "PAR")
DATA_LED_NAMES: tuple[str, ...] = ("D0", "D1", "D2", "D3", "D4")


class MsgID(IntEnum):
    """R1 -> R2 event messages.

    Keep IDs in the 0~31 range because the first hardware version uses 5 data LEDs.
    """

    IDLE = 0
    HOLD = 1
    R1_ROD_CLAMPED = 2
    R1_AT_ASSEMBLY_POSE = 3
    INSERT_ALLOWED = 4
    WEAPON_LOCKED = 5
    R1_CLEAR_MC = 6
    R1_IN_MF = 7

    R1_ATTACK_READY = 8
    R1_WAIT_R2 = 9
    LIFT_DOCK_READY = 10
    R2_ON_LIFT_DETECTED = 11
    TOP_RELEASE_ALLOWED = 12
    DESCEND_ALLOWED = 13
    ABORT_CURRENT_TASK = 14
    RETRY_RESET = 15

    GRID_TARGET_1 = 20
    GRID_TARGET_2 = 21
    GRID_TARGET_3 = 22
    GRID_TARGET_4 = 23
    GRID_TARGET_5 = 24
    GRID_TARGET_6 = 25
    GRID_TARGET_7 = 26
    GRID_TARGET_8 = 27
    GRID_TARGET_9 = 28

    DEBUG = 29
    ERROR = 30
    TEST = 31


@dataclass(frozen=True)
class EncodedBeacon:
    """Encoded LED beacon frame."""

    msg_id: int
    seq: int
    bits: dict[str, int]


@dataclass(frozen=True)
class DecodedBeacon:
    """Decoded beacon message."""

    msg_id: int
    seq: int
    valid: bool
    bits: dict[str, int]

    @property
    def msg_name(self) -> str:
        try:
            return MsgID(self.msg_id).name
        except ValueError:
            return f"UNKNOWN_{self.msg_id}"


def _bit(value: int) -> int:
    return 1 if value else 0


def validate_msg_id(msg_id: int) -> None:
    if not 0 <= int(msg_id) <= 31:
        raise ValueError(f"msg_id must be in 0~31, got {msg_id}")


def validate_seq(seq: int) -> None:
    if int(seq) not in (0, 1):
        raise ValueError(f"seq must be 0 or 1, got {seq}")


def even_parity(*bits: int) -> int:
    """Return parity bit so that XOR(all input bits, parity) == 0."""

    acc = 0
    for b in bits:
        acc ^= _bit(b)
    return acc


def encode_led_bits(msg_id: int | MsgID, seq: int) -> EncodedBeacon:
    """Encode a message into LED bit states.

    Args:
        msg_id: 0~31 event id.
        seq: 0/1 sequence bit. It should toggle when R1 emits a new event.

    Returns:
        EncodedBeacon with all 8 LED states.
    """

    raw_msg_id = int(msg_id)
    validate_msg_id(raw_msg_id)
    validate_seq(seq)
    seq = int(seq)

    data_bits = [(raw_msg_id >> i) & 1 for i in range(5)]
    par = even_parity(*data_bits, seq)

    bits = {
        "REF": 1,
        "D0": data_bits[0],
        "D1": data_bits[1],
        "D2": data_bits[2],
        "D3": data_bits[3],
        "D4": data_bits[4],
        "SEQ": seq,
        "PAR": par,
    }
    return EncodedBeacon(msg_id=raw_msg_id, seq=seq, bits=bits)


def decode_led_bits(bits: Mapping[str, int]) -> DecodedBeacon:
    """Decode LED bit states into msg_id and sequence.

    Missing keys and non-binary values raise ValueError. REF is not part of the parity check.
    """

    normalized: dict[str, int] = {}
    for name in LED_NAMES:
        if name not in bits:
            raise ValueError(f"missing LED bit: {name}")
        value = int(bits[name])
        if value not in (0, 1):
            raise ValueError(f"LED bit {name} must be 0 or 1, got {value}")
        normalized[name] = value

    msg_id = 0
    for i, name in enumerate(DATA_LED_NAMES):
        msg_id |= normalized[name] << i

    seq = normalized["SEQ"]
    parity_ok = (
        normalized["D0"]
        ^ normalized["D1"]
        ^ normalized["D2"]
        ^ normalized["D3"]
        ^ normalized["D4"]
        ^ seq
        ^ normalized["PAR"]
    ) == 0

    # REF should normally be on. Treat REF off as invalid, because thresholding is unreliable.
    ref_ok = normalized["REF"] == 1
    return DecodedBeacon(msg_id=msg_id, seq=seq, valid=parity_ok and ref_ok, bits=normalized)


def msg_id_to_name(msg_id: int) -> str:
    try:
        return MsgID(msg_id).name
    except ValueError:
        return f"UNKNOWN_{msg_id}"
