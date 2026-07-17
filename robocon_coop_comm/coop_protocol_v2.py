"""Four-data-light optical protocol shared by R1 and R2.

Physical bit order: D0, D1, D2, D3, REF, PAR.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Mapping


class CoopMessage(IntEnum):
    IDLE = 0
    HOLD = 1
    R1_ROD_CLAMPED = 2
    R1_AT_ASSEMBLY_POSE = 3
    INSERT_ALLOWED = 4
    WEAPON_LOCKED = 5
    R1_CLEAR_MC = 6
    R1_IN_MF = 7
    ABORT_CURRENT_TASK = 8
    RETRY_RESET = 9
    R1_ATTACK_READY = 10
    R1_WAIT_R2 = 11
    LIFT_DOCK_READY = 12
    TOP_RELEASE_ALLOWED = 13
    ERROR = 14
    PROTOCOL_TEST = 15


LED_ORDER = ("D0", "D1", "D2", "D3", "REF", "PAR")
MESSAGE_MASK = 0x0F
REF_MASK = 0x10
PAR_MASK = 0x20


@dataclass(frozen=True)
class CoopDecode:
    message: CoopMessage | None
    mask: int
    valid: bool
    reason: str
    bits: dict[str, int]


def parity(message: int) -> int:
    value = int(message) & MESSAGE_MASK
    return ((value >> 0) ^ (value >> 1) ^ (value >> 2) ^ (value >> 3)) & 1


def encode_message(message: int | CoopMessage) -> int:
    value = int(message)
    if not 0 <= value <= 15:
        raise ValueError(f"message must be in 0..15, got {value}")
    return value | REF_MASK | (parity(value) << 5)


def mask_to_bits(mask: int) -> dict[str, int]:
    value = int(mask) & 0x3F
    return {name: (value >> index) & 1 for index, name in enumerate(LED_ORDER)}


def bits_to_mask(bits: Mapping[str, int]) -> int:
    value = 0
    for index, name in enumerate(LED_ORDER):
        if name not in bits:
            raise ValueError(f"missing LED bit: {name}")
        bit = int(bits[name])
        if bit not in (0, 1):
            raise ValueError(f"LED bit {name} must be 0 or 1, got {bit}")
        value |= bit << index
    return value


def decode_mask(mask: int) -> CoopDecode:
    value = int(mask) & 0x3F
    bits = mask_to_bits(value)
    if bits["REF"] != 1:
        return CoopDecode(None, value, False, "reference_off", bits)
    message_value = value & MESSAGE_MASK
    if bits["PAR"] != parity(message_value):
        return CoopDecode(None, value, False, "parity_error", bits)
    return CoopDecode(CoopMessage(message_value), value, True, "ok", bits)
