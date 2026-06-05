"""Tests for operator command abstraction."""

from __future__ import annotations

import pytest

from robocon_coop_comm.operator_command import (
    OperatorCommand,
    OperatorMode,
    OperatorRequest,
    request_to_r1_command,
    validate_operator_command,
)


class TestOperatorCommandFields:
    def test_no_msg_id_field(self) -> None:
        """OperatorCommand must NOT have a msg_id field."""
        cmd = OperatorCommand(
            mode=OperatorMode.IDLE,
            request=OperatorRequest.START,
        )
        assert not hasattr(cmd, "msg_id")
        assert "msg_id" not in dir(cmd)

    def test_no_led_bits_field(self) -> None:
        """OperatorCommand must NOT have led_bits."""
        cmd = OperatorCommand(
            mode=OperatorMode.IDLE,
            request=OperatorRequest.START,
        )
        assert not hasattr(cmd, "led_bits")


class TestValidateOperatorCommand:
    def test_valid_target_grid_1(self) -> None:
        cmd = OperatorCommand(OperatorMode.MC_ASSEMBLY, OperatorRequest.NEXT, target_grid=1)
        validate_operator_command(cmd)  # no error

    def test_valid_target_grid_9(self) -> None:
        cmd = OperatorCommand(OperatorMode.MC_ASSEMBLY, OperatorRequest.NEXT, target_grid=9)
        validate_operator_command(cmd)

    def test_invalid_target_grid_zero(self) -> None:
        cmd = OperatorCommand(OperatorMode.MC_ASSEMBLY, OperatorRequest.NEXT, target_grid=0)
        with pytest.raises(ValueError, match="target_grid"):
            validate_operator_command(cmd)

    def test_invalid_target_grid_ten(self) -> None:
        cmd = OperatorCommand(OperatorMode.MC_ASSEMBLY, OperatorRequest.NEXT, target_grid=10)
        with pytest.raises(ValueError, match="target_grid"):
            validate_operator_command(cmd)

    def test_confirm_attack_zone_requires_arm(self) -> None:
        cmd = OperatorCommand(
            OperatorMode.ATTACK_ZONE, OperatorRequest.CONFIRM, arm_enabled=False
        )
        with pytest.raises(ValueError, match="arm_enabled"):
            validate_operator_command(cmd)

    def test_confirm_attack_zone_with_arm(self) -> None:
        cmd = OperatorCommand(
            OperatorMode.ATTACK_ZONE, OperatorRequest.CONFIRM, arm_enabled=True
        )
        validate_operator_command(cmd)  # no error


class TestRequestToR1Command:
    def test_start(self) -> None:
        cmd = OperatorCommand(OperatorMode.IDLE, OperatorRequest.START)
        assert request_to_r1_command(cmd) == "start"

    def test_next(self) -> None:
        cmd = OperatorCommand(OperatorMode.IDLE, OperatorRequest.NEXT)
        assert request_to_r1_command(cmd) == "next"

    def test_hold(self) -> None:
        cmd = OperatorCommand(OperatorMode.IDLE, OperatorRequest.HOLD)
        assert request_to_r1_command(cmd) == "hold"

    def test_reset(self) -> None:
        cmd = OperatorCommand(OperatorMode.IDLE, OperatorRequest.RESET)
        assert request_to_r1_command(cmd) == "reset"

    def test_abort(self) -> None:
        cmd = OperatorCommand(OperatorMode.IDLE, OperatorRequest.ABORT)
        assert request_to_r1_command(cmd) == "abort"

    def test_confirm_maps_to_none(self) -> None:
        """CONFIRM does not map to any R1 FSM command directly."""
        cmd = OperatorCommand(OperatorMode.IDLE, OperatorRequest.CONFIRM, arm_enabled=True)
        assert request_to_r1_command(cmd) == "none"

    def test_none_maps_to_none(self) -> None:
        cmd = OperatorCommand(OperatorMode.IDLE, OperatorRequest.NONE)
        assert request_to_r1_command(cmd) == "none"
