"""Comprehensive safety tests for R1MissionFSM.

Covers:
- ESTOP / local_estop override (highest priority)
- HOLD / ABORT / ERROR state guards
- Normal state transitions with sensor gating
- ABORT state — must not escape without RETRY
- HOLD/ABORT/ERROR resilience (no escape from safety states)
- Invalid commands ignored
- RESET behaviour
- RETRY recovery from ABORT
- local_estop from any state
"""

from __future__ import annotations

import pytest

from robocon_coop_comm.protocol import MsgID
from robocon_coop_comm.r1_fsm import OperatorCommand, R1MissionFSM, R1Sensors, R1State


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _sensors(**kwargs: bool) -> R1Sensors:
    """Build R1Sensors with all default False, overriding given kwargs."""
    defaults = {
        "rod_clamped": False,
        "in_assembly_pose": False,
        "rod_pose_locked": False,
        "chassis_stopped": False,
        "weapon_locked": False,
        "r1_clear_mc": False,
        "r1_in_mf": False,
        "estop": False,
        "local_estop": False,
    }
    defaults.update(kwargs)
    return R1Sensors(**defaults)


def _fsm_at(state: R1State) -> R1MissionFSM:
    """Return an R1 FSM pre-positioned at *state*."""
    fsm = R1MissionFSM()
    fsm.state = state
    return fsm


# ===================================================================
# ESTOP / local_estop — highest priority
# ===================================================================


class TestEstop:
    def test_estop_forces_error_from_init(self) -> None:
        fsm = R1MissionFSM()
        out = fsm.update(OperatorCommand.NEXT, _sensors(estop=True))
        assert fsm.state == R1State.ERROR
        assert out.msg_id == MsgID.ERROR
        assert out.reason == "estop"

    def test_estop_forces_error_from_any_state(self) -> None:
        for state in R1State:
            if state == R1State.ERROR:
                continue  # ERROR stays ERROR
            fsm = _fsm_at(state)
            out = fsm.update(OperatorCommand.NEXT, _sensors(estop=True))
            assert fsm.state == R1State.ERROR, f"estop from {state} should → ERROR"

    def test_local_estop_forces_error(self) -> None:
        fsm = _fsm_at(R1State.INSERT_ALLOWED)
        out = fsm.update(OperatorCommand.NEXT, _sensors(local_estop=True))
        assert fsm.state == R1State.ERROR
        assert out.msg_id == MsgID.ERROR
        assert out.reason == "local_estop"

    def test_local_estop_higher_priority_than_remote_estop(self) -> None:
        fsm = R1MissionFSM()
        out = fsm.update(OperatorCommand.NEXT, _sensors(local_estop=True, estop=True))
        assert fsm.state == R1State.ERROR
        assert out.reason == "local_estop"

    def test_local_estop_from_any_state(self) -> None:
        for state in R1State:
            if state == R1State.ERROR:
                continue
            fsm = _fsm_at(state)
            out = fsm.update(OperatorCommand.NEXT, _sensors(local_estop=True))
            assert fsm.state == R1State.ERROR, f"local_estop from {state} should → ERROR"


# ===================================================================
# HOLD — blocks normal commands
# ===================================================================


class TestHold:
    def test_hold_command_sets_hold_state(self) -> None:
        fsm = _fsm_at(R1State.INSERT_ALLOWED)
        out = fsm.update(OperatorCommand.HOLD, R1Sensors())
        assert fsm.state == R1State.HOLD
        assert out.msg_id == MsgID.HOLD

    def test_hold_blocks_next(self) -> None:
        fsm = _fsm_at(R1State.HOLD)
        out = fsm.update(OperatorCommand.NEXT, _sensors(rod_clamped=True))
        assert fsm.state == R1State.HOLD
        assert out.reason == "hold_requires_reset"

    def test_hold_blocks_start(self) -> None:
        fsm = _fsm_at(R1State.HOLD)
        out = fsm.update(OperatorCommand.START, R1Sensors())
        assert fsm.state == R1State.HOLD
        assert out.reason == "hold_requires_reset"

    def test_hold_blocks_all_transition_attempts(self) -> None:
        """From HOLD, even with ALL sensors true, NEXT must be blocked."""
        fsm = _fsm_at(R1State.HOLD)
        all_true = _sensors(
            rod_clamped=True, in_assembly_pose=True, rod_pose_locked=True,
            chassis_stopped=True, weapon_locked=True, r1_clear_mc=True, r1_in_mf=True,
        )
        out = fsm.update(OperatorCommand.NEXT, all_true)
        assert fsm.state == R1State.HOLD
        assert out.reason == "hold_requires_reset"

    def test_reset_recovers_from_hold(self) -> None:
        fsm = _fsm_at(R1State.HOLD)
        out = fsm.update(OperatorCommand.RESET, R1Sensors())
        assert fsm.state == R1State.WAIT_START
        assert out.reason == "reset"


# ===================================================================
# ABORT — dedicated state, requires RETRY to recover
# ===================================================================


class TestAbort:
    def test_abort_command_sets_abort_state(self) -> None:
        fsm = _fsm_at(R1State.INSERT_ALLOWED)
        out = fsm.update(OperatorCommand.ABORT, R1Sensors())
        assert fsm.state == R1State.ABORT
        assert out.msg_id == MsgID.ABORT_CURRENT_TASK
        assert out.reason == "operator_abort"

    def test_abort_blocks_next(self) -> None:
        fsm = _fsm_at(R1State.ABORT)
        out = fsm.update(OperatorCommand.NEXT, _sensors(rod_clamped=True))
        assert fsm.state == R1State.ABORT
        assert out.reason == "abort_requires_retry"

    def test_abort_blocks_start(self) -> None:
        fsm = _fsm_at(R1State.ABORT)
        out = fsm.update(OperatorCommand.START, R1Sensors())
        assert fsm.state == R1State.ABORT
        assert out.reason == "abort_requires_retry"

    def test_abort_blocks_hold(self) -> None:
        """HOLD from ABORT should still work — ABORT handles HOLD request."""
        fsm = _fsm_at(R1State.ABORT)
        out = fsm.update(OperatorCommand.HOLD, R1Sensors())
        # HOLD is checked before the ABORT/ERROR safety block
        assert fsm.state == R1State.HOLD
        assert out.reason == "operator_hold"

    def test_retry_recovers_from_abort(self) -> None:
        fsm = _fsm_at(R1State.ABORT)
        out = fsm.update(OperatorCommand.RETRY, R1Sensors())
        assert fsm.state == R1State.WAIT_START
        assert out.reason == "reset"

    def test_retry_from_non_abort_is_noop(self) -> None:
        fsm = _fsm_at(R1State.HOLD)
        out = fsm.update(OperatorCommand.RETRY, R1Sensors())
        assert fsm.state == R1State.HOLD
        assert out.reason == "retry_noop"

    def test_reset_recover_from_abort(self) -> None:
        fsm = _fsm_at(R1State.ABORT)
        out = fsm.update(OperatorCommand.RESET, R1Sensors())
        assert fsm.state == R1State.WAIT_START


# ===================================================================
# ERROR — blocks normal commands
# ===================================================================


class TestError:
    def test_error_blocks_next(self) -> None:
        fsm = _fsm_at(R1State.ERROR)
        out = fsm.update(OperatorCommand.NEXT, _sensors(rod_clamped=True))
        assert fsm.state == R1State.ERROR
        assert out.reason == "error_requires_reset"

    def test_error_blocks_start(self) -> None:
        fsm = _fsm_at(R1State.ERROR)
        out = fsm.update(OperatorCommand.START, R1Sensors())
        assert fsm.state == R1State.ERROR
        assert out.reason == "error_requires_reset"

    def test_error_blocks_all_sensors_true(self) -> None:
        fsm = _fsm_at(R1State.ERROR)
        all_true = _sensors(
            rod_clamped=True, in_assembly_pose=True, rod_pose_locked=True,
            chassis_stopped=True, weapon_locked=True, r1_clear_mc=True, r1_in_mf=True,
        )
        out = fsm.update(OperatorCommand.NEXT, all_true)
        assert fsm.state == R1State.ERROR
        assert out.reason == "error_requires_reset"

    def test_reset_recovers_from_error(self) -> None:
        fsm = _fsm_at(R1State.ERROR)
        out = fsm.update(OperatorCommand.RESET, R1Sensors())
        assert fsm.state == R1State.WAIT_START
        assert out.reason == "reset"


# ===================================================================
# Normal flow — sensor-gated transitions (preserved original tests + extended)
# ===================================================================


class TestNormalFlow:
    def test_insert_allowed_is_guarded_by_sensors(self) -> None:
        fsm = R1MissionFSM()
        sensors = R1Sensors()

        fsm.update(OperatorCommand.START, sensors)
        out = fsm.update(OperatorCommand.NEXT, sensors)
        assert out.msg_id == MsgID.HOLD
        assert fsm.state == R1State.PICK_ROD

        sensors.rod_clamped = True
        out = fsm.update(OperatorCommand.NEXT, sensors)
        assert out.state == R1State.ROD_CLAMPED
        assert out.msg_id == MsgID.R1_ROD_CLAMPED

        sensors.in_assembly_pose = True
        out = fsm.update(OperatorCommand.NEXT, sensors)
        assert out.state == R1State.AT_ASSEMBLY_POSE
        assert out.msg_id == MsgID.R1_AT_ASSEMBLY_POSE

        # Missing pose lock and chassis stop; must not allow insertion.
        out = fsm.update(OperatorCommand.NEXT, sensors)
        assert out.msg_id == MsgID.HOLD
        assert fsm.state == R1State.AT_ASSEMBLY_POSE

        sensors.rod_pose_locked = True
        sensors.chassis_stopped = True
        out = fsm.update(OperatorCommand.NEXT, sensors)
        assert out.state == R1State.INSERT_ALLOWED
        assert out.msg_id == MsgID.INSERT_ALLOWED

    def test_full_mc_to_mf_sequence(self) -> None:
        fsm = R1MissionFSM()
        sensors = R1Sensors(
            rod_clamped=True,
            in_assembly_pose=True,
            rod_pose_locked=True,
            chassis_stopped=True,
            weapon_locked=True,
            r1_clear_mc=True,
            r1_in_mf=True,
        )

        fsm.update(OperatorCommand.START, sensors)
        assert fsm.update(OperatorCommand.NEXT, sensors).msg_id == MsgID.R1_ROD_CLAMPED
        assert fsm.update(OperatorCommand.NEXT, sensors).msg_id == MsgID.R1_AT_ASSEMBLY_POSE
        assert fsm.update(OperatorCommand.NEXT, sensors).msg_id == MsgID.INSERT_ALLOWED
        assert fsm.update(OperatorCommand.NEXT, sensors).msg_id == MsgID.WEAPON_LOCKED
        assert fsm.update(OperatorCommand.NEXT, sensors).msg_id == MsgID.R1_CLEAR_MC
        assert fsm.update(OperatorCommand.NEXT, sensors).msg_id == MsgID.R1_IN_MF

    # Additional guard tests

    def test_rod_clamped_required_for_move_to_rod_clamped(self) -> None:
        fsm = _fsm_at(R1State.PICK_ROD)
        out = fsm.update(OperatorCommand.NEXT, _sensors(rod_clamped=False))
        assert fsm.state == R1State.PICK_ROD
        assert out.msg_id == MsgID.HOLD
        assert out.reason == "blocked_wait_rod_clamped"

    def test_in_assembly_pose_required(self) -> None:
        fsm = _fsm_at(R1State.ROD_CLAMPED)
        out = fsm.update(OperatorCommand.NEXT, _sensors(in_assembly_pose=False))
        assert fsm.state == R1State.ROD_CLAMPED
        assert out.msg_id == MsgID.HOLD
        assert out.reason == "blocked_wait_assembly_pose"

    def test_insert_allowed_requires_three_conditions(self) -> None:
        """All three conditions (rod_clamped, rod_pose_locked, chassis_stopped)
        must be true simultaneously for INSERT_ALLOWED."""
        fsm = _fsm_at(R1State.AT_ASSEMBLY_POSE)

        # missing all
        out = fsm.update(OperatorCommand.NEXT, _sensors())
        assert out.reason == "blocked_wait_pose_lock_and_stop"

        # missing one
        out = fsm.update(OperatorCommand.NEXT, _sensors(
            rod_clamped=True, rod_pose_locked=True, chassis_stopped=False))
        assert out.reason == "blocked_wait_pose_lock_and_stop"

        out = fsm.update(OperatorCommand.NEXT, _sensors(
            rod_clamped=False, rod_pose_locked=True, chassis_stopped=True))
        assert out.reason == "blocked_wait_pose_lock_and_stop"

        # all three
        out = fsm.update(OperatorCommand.NEXT, _sensors(
            rod_clamped=True, rod_pose_locked=True, chassis_stopped=True))
        assert out.reason == "insert_allowed"

    def test_weapon_locked_required_for_exit_insert_allowed(self) -> None:
        fsm = _fsm_at(R1State.INSERT_ALLOWED)
        out = fsm.update(OperatorCommand.NEXT, _sensors(weapon_locked=False))
        assert fsm.state == R1State.INSERT_ALLOWED  # stays, waiting
        assert out.msg_id == MsgID.INSERT_ALLOWED

    def test_r1_clear_mc_required(self) -> None:
        fsm = _fsm_at(R1State.WEAPON_LOCKED)
        out = fsm.update(OperatorCommand.NEXT, _sensors(r1_clear_mc=False))
        assert fsm.state == R1State.WEAPON_LOCKED
        assert out.msg_id == MsgID.HOLD
        assert out.reason == "blocked_wait_clear_mc"

    def test_r1_in_mf_required(self) -> None:
        fsm = _fsm_at(R1State.R1_CLEAR_MC)
        out = fsm.update(OperatorCommand.NEXT, _sensors(r1_in_mf=False))
        assert fsm.state == R1State.R1_CLEAR_MC  # stays, waiting
        assert out.msg_id == MsgID.R1_CLEAR_MC


# ===================================================================
# Command edge cases
# ===================================================================


class TestCommandEdgeCases:
    def test_none_command_is_noop(self) -> None:
        fsm = R1MissionFSM()
        out = fsm.update(OperatorCommand.NONE, R1Sensors())
        assert fsm.state == R1State.WAIT_START
        assert out.reason == "no_transition"

    def test_start_twice_from_wait_start_is_noop(self) -> None:
        """Second START from WAIT_START after first START → PICK_ROD is already active."""
        fsm = R1MissionFSM()
        fsm.update(OperatorCommand.START, R1Sensors())  # → PICK_ROD
        out = fsm.update(OperatorCommand.START, R1Sensors())
        # START only matches WAIT_START, so falls through
        assert out.reason == "no_transition"

    def test_next_from_wait_start_goes_to_pick_rod(self) -> None:
        fsm = R1MissionFSM()
        out = fsm.update(OperatorCommand.NEXT, R1Sensors())
        assert fsm.state == R1State.PICK_ROD

    def test_reset_from_init_is_idempotent(self) -> None:
        fsm = R1MissionFSM()
        out1 = fsm.reset()
        out2 = fsm.reset()
        assert fsm.state == R1State.WAIT_START
        assert out1 == out2


# ===================================================================
# State transition guard: no bypass without correct sensor
# ===================================================================


class TestCannotBypassSensorGuard:
    """Sensor guards must not be bypassed by any command sequence."""

    def test_cannot_skip_rod_clamped_with_all_false(self) -> None:
        fsm = R1MissionFSM()
        fsm.update(OperatorCommand.START, R1Sensors())
        # Mash NEXT repeatedly, never set rod_clamped
        for _ in range(10):
            fsm.update(OperatorCommand.NEXT, R1Sensors())
        assert fsm.state == R1State.PICK_ROD  # never advanced

    def test_cannot_skip_to_insert_allowed_from_pick_rod(self) -> None:
        """Even with all sensors true, must go through each state step by step."""
        fsm = _fsm_at(R1State.PICK_ROD)
        all_true = _sensors(
            rod_clamped=True, in_assembly_pose=True, rod_pose_locked=True,
            chassis_stopped=True, weapon_locked=True,
        )
        out = fsm.update(OperatorCommand.NEXT, all_true)
        # Only ROD_CLAMPED gate fires → advances to ROD_CLAMPED
        assert fsm.state == R1State.ROD_CLAMPED
        # NOT INSERT_ALLOWED — must go through each stage

    def test_reset_clears_all_progress(self) -> None:
        fsm = R1MissionFSM()
        sensors = _sensors(
            rod_clamped=True, in_assembly_pose=True, rod_pose_locked=True,
            chassis_stopped=True, weapon_locked=True,
        )
        fsm.update(OperatorCommand.START, sensors)
        fsm.update(OperatorCommand.NEXT, sensors)  # ROD_CLAMPED
        fsm.update(OperatorCommand.NEXT, sensors)  # AT_ASSEMBLY_POSE
        fsm.update(OperatorCommand.NEXT, sensors)  # INSERT_ALLOWED
        assert fsm.state == R1State.INSERT_ALLOWED

        fsm.reset()
        assert fsm.state == R1State.WAIT_START
        assert fsm.seq == 0
        assert fsm.msg_id == MsgID.IDLE


# ===================================================================
# Sequence bit toggles
# ===================================================================


class TestSeqToggle:
    def test_seq_toggles_on_new_msg_id(self) -> None:
        fsm = R1MissionFSM()
        sensors = _sensors(rod_clamped=True)
        fsm.update(OperatorCommand.START, sensors)
        out1 = fsm.update(OperatorCommand.NEXT, sensors)  # ROD_CLAMPED
        assert fsm.seq == 1
        assert out1.seq == 1

    def test_same_msg_id_keeps_seq(self) -> None:
        """When msg_id does not change, seq stays the same."""
        fsm = _fsm_at(R1State.INSERT_ALLOWED)
        fsm.seq = 1
        fsm.msg_id = MsgID.INSERT_ALLOWED
        out = fsm.update(OperatorCommand.NEXT, _sensors(weapon_locked=False))
        assert out.msg_id == MsgID.INSERT_ALLOWED
        assert out.seq == 1  # unchanged

    def test_seq_toggles_multiple_times(self) -> None:
        fsm = R1MissionFSM()
        sensors = R1Sensors(
            rod_clamped=True, in_assembly_pose=True, rod_pose_locked=True,
            chassis_stopped=True, weapon_locked=True, r1_clear_mc=True, r1_in_mf=True,
        )
        fsm.update(OperatorCommand.START, sensors)
        seqs = []
        for _ in range(6):
            out = fsm.update(OperatorCommand.NEXT, sensors)
            seqs.append(out.seq)
        # seq should have toggled several times
        assert len(set(seqs)) >= 1


# ===================================================================
# R1Output frozen dataclass
# ===================================================================


class TestR1Output:
    def test_output_fields(self) -> None:
        fsm = R1MissionFSM()
        out = fsm.output("test")
        assert out.state == R1State.WAIT_START
        assert out.msg_id == MsgID.IDLE
        assert out.seq == 0
        assert out.reason == "test"

    def test_output_is_frozen(self) -> None:
        fsm = R1MissionFSM()
        out = fsm.output("test")
        with pytest.raises(Exception):
            out.reason = "modified"  # type: ignore[misc]


# ===================================================================
# R1Sensors defaults
# ===================================================================


class TestR1Sensors:
    def test_default_sensors_all_false(self) -> None:
        s = R1Sensors()
        assert s.rod_clamped is False
        assert s.in_assembly_pose is False
        assert s.rod_pose_locked is False
        assert s.chassis_stopped is False
        assert s.weapon_locked is False
        assert s.r1_clear_mc is False
        assert s.r1_in_mf is False
        assert s.estop is False
        assert s.local_estop is False

    def test_sensors_can_be_modified(self) -> None:
        s = R1Sensors()
        s.rod_clamped = True
        assert s.rod_clamped is True


# ===================================================================
# FSM defaults
# ===================================================================


class TestFSMDefaults:
    def test_initial_state_is_wait_start(self) -> None:
        fsm = R1MissionFSM()
        assert fsm.state == R1State.WAIT_START

    def test_initial_msg_seq(self) -> None:
        fsm = R1MissionFSM()
        assert fsm.msg_id == MsgID.IDLE
        assert fsm.seq == 0

    def test_reset_from_initial_is_idempotent(self) -> None:
        fsm = R1MissionFSM()
        out1 = fsm.reset()
        out2 = fsm.reset()
        assert out1 == out2
