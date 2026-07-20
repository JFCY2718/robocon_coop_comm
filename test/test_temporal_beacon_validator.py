"""Tests for the competition temporal validation gate."""

from __future__ import annotations

import pytest

from robocon_coop_comm.beacon_types import DecodedBeacon
from robocon_coop_comm.coop_protocol_v2 import CoopMessage
from robocon_coop_comm.temporal_beacon_validator import TemporalBeaconValidator


def _beacon(msg_id: int, *, valid: bool = True, confidence: float = 0.9) -> DecodedBeacon:
    return DecodedBeacon(
        msg_id=msg_id,
        msg_name=CoopMessage(msg_id).name,
        seq=0,
        valid=valid,
        confidence=confidence,
        source="test",
    )


def test_ordinary_message_uses_three_of_five_vote() -> None:
    gate = TemporalBeaconValidator()
    outputs = [gate.update(_beacon(int(CoopMessage.HOLD)), now=10.0) for _ in range(3)]
    assert [item.valid for item in outputs] == [False, False, True]
    assert "temporal_vote" in outputs[-1].reason


def test_vote_tolerates_one_invalid_frame() -> None:
    gate = TemporalBeaconValidator()
    target = _beacon(int(CoopMessage.R1_ROD_CLAMPED))
    assert not gate.update(target, now=10.00).valid
    assert not gate.update(_beacon(0, valid=False), now=10.01).valid
    assert not gate.update(target, now=10.02).valid
    assert gate.update(target, now=10.03).valid


@pytest.mark.parametrize(
    "message",
    [CoopMessage.INSERT_ALLOWED, CoopMessage.TOP_RELEASE_ALLOWED],
)
def test_dangerous_message_requires_five_consecutive_frames(message: CoopMessage) -> None:
    gate = TemporalBeaconValidator()
    for index in range(4):
        assert not gate.update(_beacon(int(message)), now=10.0 + index * 0.01).valid
    assert gate.update(_beacon(int(message)), now=10.05).valid


def test_invalid_frame_breaks_dangerous_consecutive_run() -> None:
    gate = TemporalBeaconValidator()
    danger = _beacon(int(CoopMessage.INSERT_ALLOWED))
    for index in range(4):
        gate.update(danger, now=10.0 + index * 0.01)
    gate.update(_beacon(0, valid=False), now=10.04)
    assert not gate.update(danger, now=10.05).valid


def test_low_confidence_and_stale_inputs_are_rejected() -> None:
    gate = TemporalBeaconValidator(max_age_s=0.3)
    low = gate.update(_beacon(1, confidence=0.69), now=10.0)
    stale = gate.update(_beacon(1), timestamp=9.0, now=10.0)
    assert not low.valid and low.reason == "low_confidence"
    assert not stale.valid and stale.reason == "stale_input"


def test_old_votes_expire() -> None:
    gate = TemporalBeaconValidator(max_age_s=0.3)
    target = _beacon(1)
    gate.update(target, now=10.0)
    gate.update(target, now=10.1)
    result = gate.update(target, now=10.5)
    assert not result.valid
    assert "1/3" in result.reason


def test_constructor_rejects_invalid_parameters() -> None:
    with pytest.raises(ValueError):
        TemporalBeaconValidator(window_size=0)
    with pytest.raises(ValueError):
        TemporalBeaconValidator(window_size=3, min_matches=4)
