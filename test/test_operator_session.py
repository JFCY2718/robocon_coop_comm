"""Tests for operator session."""

from __future__ import annotations

from robocon_coop_comm.operator_command import OperatorRequest
from robocon_coop_comm.operator_session import OperatorSession


class TestOperatorSession:
    def test_target_next_cycles_1_to_9(self) -> None:
        s = OperatorSession()
        for expected in range(1, 10):
            cmd = s.handle_key("]")
            assert s.target_grid == expected
            assert cmd.request == OperatorRequest.TARGET_NEXT

    def test_target_next_wraps_9_to_1(self) -> None:
        s = OperatorSession()
        for _ in range(9):
            s.handle_key("]")
        assert s.target_grid == 9
        s.handle_key("]")
        assert s.target_grid == 1

    def test_target_prev_cycles_9_to_1(self) -> None:
        s = OperatorSession()
        for expected in [9, 8, 7, 6, 5, 4, 3, 2, 1]:
            cmd = s.handle_key("[")
            assert s.target_grid == expected
            assert cmd.request == OperatorRequest.TARGET_PREV

    def test_target_prev_wraps_1_to_9(self) -> None:
        s = OperatorSession()
        s.handle_key("]")  # set to 1
        assert s.target_grid == 1
        s.handle_key("[")
        assert s.target_grid == 9

    def test_arm_enable(self) -> None:
        s = OperatorSession()
        cmd = s.handle_key("e")
        assert s.arm_enabled is True
        assert cmd.arm_enabled is True
        assert cmd.request == OperatorRequest.ARM_ENABLE

    def test_arm_disable(self) -> None:
        s = OperatorSession()
        s.handle_key("e")
        assert s.arm_enabled is True
        cmd = s.handle_key("d")
        assert s.arm_enabled is False
        assert cmd.arm_enabled is False

    def test_hold_disables_arm(self) -> None:
        s = OperatorSession()
        s.handle_key("e")
        assert s.arm_enabled is True
        s.handle_key("h")
        assert s.arm_enabled is False

    def test_abort_disables_arm(self) -> None:
        s = OperatorSession()
        s.handle_key("e")
        s.handle_key("a")
        assert s.arm_enabled is False

    def test_reset_disables_arm(self) -> None:
        s = OperatorSession()
        s.handle_key("e")
        s.handle_key("r")
        assert s.arm_enabled is False

    def test_handle_key_no_msg_id(self) -> None:
        """OperatorCommand from handle_key must NOT contain msg_id."""
        s = OperatorSession()
        cmd = s.handle_key("n")
        assert not hasattr(cmd, "msg_id")

    def test_handle_key_no_led_bits(self) -> None:
        """OperatorCommand from handle_key must NOT contain led_bits."""
        s = OperatorSession()
        cmd = s.handle_key("n")
        assert not hasattr(cmd, "led_bits")
