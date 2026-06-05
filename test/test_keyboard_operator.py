"""Tests for keyboard operator input parser."""

from __future__ import annotations

from robocon_coop_comm.keyboard_operator import parse_key_to_operator_command
from robocon_coop_comm.operator_command import OperatorMode, OperatorRequest


def _parse(key: str) -> OperatorRequest:
    return parse_key_to_operator_command(
        key, OperatorMode.IDLE, False, None
    ).request


class TestKeyMapping:
    def test_s_is_start(self) -> None:
        assert _parse("s") == OperatorRequest.START

    def test_n_is_next(self) -> None:
        assert _parse("n") == OperatorRequest.NEXT

    def test_h_is_hold(self) -> None:
        assert _parse("h") == OperatorRequest.HOLD

    def test_a_is_abort(self) -> None:
        assert _parse("a") == OperatorRequest.ABORT

    def test_r_is_reset(self) -> None:
        assert _parse("r") == OperatorRequest.RESET

    def test_e_is_arm_enable(self) -> None:
        assert _parse("e") == OperatorRequest.ARM_ENABLE

    def test_d_is_arm_disable(self) -> None:
        assert _parse("d") == OperatorRequest.ARM_DISABLE

    def test_open_bracket_is_target_prev(self) -> None:
        assert _parse("[") == OperatorRequest.TARGET_PREV

    def test_close_bracket_is_target_next(self) -> None:
        assert _parse("]") == OperatorRequest.TARGET_NEXT

    def test_unknown_key_is_none(self) -> None:
        assert _parse("z") == OperatorRequest.NONE
        assert _parse("x") == OperatorRequest.NONE
        assert _parse("1") == OperatorRequest.NONE

    def test_preserves_mode(self) -> None:
        cmd = parse_key_to_operator_command(
            "n", OperatorMode.MC_ASSEMBLY, False, None
        )
        assert cmd.mode == OperatorMode.MC_ASSEMBLY

    def test_preserves_arm_state(self) -> None:
        cmd = parse_key_to_operator_command(
            "n", OperatorMode.IDLE, True, 5
        )
        assert cmd.arm_enabled is True
        assert cmd.target_grid == 5
