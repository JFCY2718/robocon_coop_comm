from __future__ import annotations

import json
from pathlib import Path

import pytest

from robocon_coop_comm.coop_protocol_v2 import (
    LED_ORDER,
    bits_to_mask,
    decode_mask,
    encode_message,
    mask_to_bits,
)


VECTORS = json.loads(
    (Path(__file__).parents[1] / "docs" / "four_light_protocol_vectors.json").read_text(
        encoding="utf-8"
    )
)


def test_all_golden_vectors_round_trip() -> None:
    assert LED_ORDER == ("D0", "D1", "D2", "D3", "REF", "PAR")
    for vector in VECTORS:
        mask = encode_message(vector["state_id"])
        assert mask == vector["mask"]
        decoded = decode_mask(mask)
        assert decoded.valid
        assert decoded.message is not None
        assert int(decoded.message) == vector["state_id"]
        assert decoded.message.name == vector["name"]
        assert bits_to_mask(mask_to_bits(mask)) == mask


@pytest.mark.parametrize("state_id", range(16))
def test_single_data_or_parity_bit_error_is_rejected(state_id: int) -> None:
    mask = encode_message(state_id)
    for bit in (0, 1, 2, 3, 5):
        assert not decode_mask(mask ^ (1 << bit)).valid


def test_reference_off_is_rejected() -> None:
    assert decode_mask(encode_message(4) & ~0x10).reason == "reference_off"
