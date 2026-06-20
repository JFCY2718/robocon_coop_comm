"""Comprehensive tests for R2MissionFSM.

Covers:
- ESTOP override (highest priority)
- Invalid/unknown beacon rejection
- HOLD / ERROR / ABORT message handling
- WAIT_R1 entry transitions
- INSERT_ALLOWED local sensor gating (safety-critical)
- INSERT_ALLOWED duplicate seq debounce
- WEAPON_LOCKED timing variants
- R1_CLEAR_MC sequence gating
- R1_IN_MF sequence gating
- R1_AT_ASSEMBLY_POSE head_grabbed gating
- Full happy-path sequence
- Reset behaviour
- HOLD state resilience (no unexpected escape from HOLD)
- ERROR state resilience (no unexpected escape from ERROR)
- Vision messages must NEVER bypass local safety conditions
- RETRY_RESET handling
- All MsgID coverage from key states
- Duplicate seq debounce for all handled message types
- Sensor-driven state auto-advance
"""

from __future__ import annotations

from robocon_coop_comm.protocol import MsgID, decode_led_bits, encode_led_bits
from robocon_coop_comm.r2_fsm import R2MissionFSM, R2Sensors, R2State


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _beacon(msg_id: int, seq: int = 0):
    """Build a valid protocol DecodedBeacon from msg_id and seq."""
    return decode_led_bits(encode_led_bits(msg_id, seq).bits)


def _invalid_beacon() -> object:
    """A DecodedBeacon with valid=False (simulate decode failure)."""
    return decode_led_bits({"REF": 0, "D0": 0, "D1": 0, "D2": 0, "D3": 0, "D4": 0, "SEQ": 0, "PAR": 0})


def _fsm_at(state: R2State, last_msg_id: int | None = None, last_seq: int | None = None) -> R2MissionFSM:
    """Return an FSM pre-positioned at *state* with optional seq tracking."""
    fsm = R2MissionFSM()
    fsm.state = state
    fsm.last_msg_id = last_msg_id
    fsm.last_seq = last_seq
    return fsm


# ===================================================================
# ESTOP — highest priority, must override everything
# ===================================================================


class TestEstop:
    def test_estop_from_wait_r1_stops_immediately(self) -> None:
        fsm = R2MissionFSM()
        sensors = R2Sensors(estop=True)
        out = fsm.update(_beacon(MsgID.R1_ROD_CLAMPED, 0), sensors)
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "stop_all"
        assert out.reason == "estop"

    def test_estop_from_inserting_stops_immediately(self) -> None:
        """ESTOP must override even an active insertion — safety-critical."""
        sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        fsm = _fsm_at(R2State.INSERTING, last_msg_id=MsgID.INSERT_ALLOWED, last_seq=1)
        sensors.estop = True
        out = fsm.update(_beacon(MsgID.WEAPON_LOCKED, 0), sensors)
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "stop_all"

    def test_estop_overrides_even_valid_beacon(self) -> None:
        """If estop is active, beacon content must be completely ignored."""
        fsm = R2MissionFSM()
        sensors = R2Sensors(estop=True, head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        out = fsm.update(_beacon(MsgID.INSERT_ALLOWED, 0), sensors)
        assert fsm.state == R2State.ERROR
        # INSERT_ALLOWED with all sensors ready would normally trigger insertion,
        # but estop must prevent it.
        assert out.action_hint != "insert_head"


# ===================================================================
# Invalid / unknown beacon — must not affect state
# ===================================================================


class TestInvalidBeacon:
    def test_invalid_beacon_ignored_from_any_state(self) -> None:
        fsm = _fsm_at(R2State.INSERTING)
        out = fsm.update(_invalid_beacon(), R2Sensors())
        assert fsm.state == R2State.INSERTING  # unchanged
        assert out.action_hint == "ignore"
        assert "invalid" in out.reason.lower()

    def test_unknown_msg_id_ignored(self) -> None:
        """MsgID values not in the enum must not crash or change state."""
        # decode_led_bits can validate bits for any 5-bit msg_id up to 31,
        # but MsgID(99) raises ValueError → "unknown_msg"
        fsm = R2MissionFSM()
        # Craft a DecodedBeacon manually with an out-of-range msg_id
        from robocon_coop_comm.protocol import DecodedBeacon as ProtoBeacon

        unknown = ProtoBeacon(msg_id=99, seq=0, valid=True, bits={})
        out = fsm.update(unknown, R2Sensors())
        assert fsm.state == R2State.WAIT_R1
        assert out.action_hint == "ignore"
        assert "unknown" in out.reason.lower()

    def test_valid_beacon_required_for_transition(self) -> None:
        """An invalid beacon must never trigger any state transition."""
        fsm = R2MissionFSM()
        sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        # Send invalid version of INSERT_ALLOWED
        out = fsm.update(_invalid_beacon(), sensors)
        assert fsm.state == R2State.WAIT_R1  # must NOT become INSERTING
        assert out.action_hint == "ignore"


# ===================================================================
# HOLD / ERROR / ABORT — global override messages
# ===================================================================


class TestHoldErrorAbort:
    def test_hold_msg_forces_hold_from_wait_r1(self) -> None:
        fsm = R2MissionFSM()
        out = fsm.update(_beacon(MsgID.HOLD, 0), R2Sensors())
        assert fsm.state == R2State.HOLD
        assert out.action_hint == "hold"

    def test_hold_msg_forces_hold_from_inserting(self) -> None:
        """HOLD must take priority over an active insertion."""
        fsm = _fsm_at(R2State.INSERTING)
        out = fsm.update(_beacon(MsgID.HOLD, 1), R2Sensors())
        assert fsm.state == R2State.HOLD
        assert out.action_hint == "hold"

    def test_error_msg_enters_error_state(self) -> None:
        fsm = R2MissionFSM()
        out = fsm.update(_beacon(MsgID.ERROR, 0), R2Sensors())
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "hold"

    def test_abort_msg_enters_hold_state(self) -> None:
        fsm = _fsm_at(R2State.INSERTING)
        out = fsm.update(_beacon(MsgID.ABORT_CURRENT_TASK, 0), R2Sensors())
        assert fsm.state == R2State.HOLD
        assert out.action_hint == "hold"


# ===================================================================
# WAIT_R1 — entry gate
# ===================================================================


class TestWaitR1:
    def test_rod_clamped_from_wait_r1_triggers_grab_head(self) -> None:
        fsm = R2MissionFSM()
        out = fsm.update(_beacon(MsgID.R1_ROD_CLAMPED, 0), R2Sensors())
        assert fsm.state == R2State.PREPARE_HEAD
        assert out.action_hint == "grab_head"

    def test_rod_clamped_from_non_wait_r1_is_noop(self) -> None:
        """R1_ROD_CLAMPED must only be consumed from WAIT_R1."""
        fsm = _fsm_at(R2State.INSERTING)
        out = fsm.update(_beacon(MsgID.R1_ROD_CLAMPED, 0), R2Sensors())
        assert fsm.state == R2State.INSERTING  # unchanged
        assert out.action_hint == "wait"

    def test_irrelevant_msg_in_wait_r1_no_transition(self) -> None:
        """A message with no matching rule must return 'wait' and not crash."""
        fsm = R2MissionFSM()
        # DEBUG has no dedicated handler in the FSM — falls through to default.
        out = fsm.update(_beacon(MsgID.DEBUG, 0), R2Sensors())
        assert fsm.state == R2State.WAIT_R1
        assert out.action_hint == "wait"
        assert out.reason == "no_matching_transition"


# ===================================================================
# INSERT_ALLOWED — local sensor gating (safety-critical)
# ===================================================================


class TestInsertAllowedGating:
    """INSERT_ALLOWED must NOT trigger insertion unless ALL local sensors are ready."""

    def test_rejected_when_head_not_grabbed(self) -> None:
        fsm = _fsm_at(R2State.SEARCH_R1_TAG)
        sensors = R2Sensors(head_grabbed=False, r1_tag_visible=True, pre_insert_pose_ok=True)
        out = fsm.update(_beacon(MsgID.INSERT_ALLOWED, 0), sensors)
        assert fsm.state != R2State.INSERTING
        assert out.action_hint == "wait_local_ready"

    def test_rejected_when_tag_not_visible(self) -> None:
        fsm = _fsm_at(R2State.SEARCH_R1_TAG)
        sensors = R2Sensors(head_grabbed=True, r1_tag_visible=False, pre_insert_pose_ok=True)
        out = fsm.update(_beacon(MsgID.INSERT_ALLOWED, 0), sensors)
        assert fsm.state != R2State.INSERTING
        assert out.action_hint == "wait_local_ready"

    def test_rejected_when_pre_insert_pose_not_ok(self) -> None:
        fsm = _fsm_at(R2State.SEARCH_R1_TAG)
        sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=False)
        out = fsm.update(_beacon(MsgID.INSERT_ALLOWED, 0), sensors)
        assert fsm.state != R2State.INSERTING
        assert out.action_hint == "wait_local_ready"

    def test_accepted_when_all_sensors_ready(self) -> None:
        fsm = _fsm_at(R2State.SEARCH_R1_TAG)
        sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        out = fsm.update(_beacon(MsgID.INSERT_ALLOWED, 0), sensors)
        assert fsm.state == R2State.INSERTING
        assert out.action_hint == "insert_head"
        assert out.reason == "insert_allowed_and_local_ready"

    def test_from_wait_r1_still_requires_all_sensors(self) -> None:
        """Even from WAIT_R1, local conditions gate INSERT_ALLOWED."""
        fsm = R2MissionFSM()
        sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=False)
        out = fsm.update(_beacon(MsgID.INSERT_ALLOWED, 0), sensors)
        assert fsm.state != R2State.INSERTING
        assert out.action_hint == "wait_local_ready"


# ===================================================================
# INSERT_ALLOWED — duplicate seq debounce
# ===================================================================


class TestInsertAllowedDebounce:
    """Repeated INSERT_ALLOWED with the same seq must not retrigger one-shot actions."""

    def test_same_seq_while_inserting_continues(self) -> None:
        sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        fsm = _fsm_at(R2State.INSERTING, last_msg_id=MsgID.INSERT_ALLOWED, last_seq=1)
        out = fsm.update(_beacon(MsgID.INSERT_ALLOWED, 1), sensors)
        assert fsm.state == R2State.INSERTING
        assert out.action_hint == "continue_insert"
        assert out.reason == "insert_already_active"

    def test_new_seq_re_evaluates_sensors(self) -> None:
        """A new seq should re-evaluate local sensors, not blindly continue."""
        sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        fsm = _fsm_at(R2State.INSERTING, last_msg_id=MsgID.INSERT_ALLOWED, last_seq=1)
        out = fsm.update(_beacon(MsgID.INSERT_ALLOWED, 0), sensors)
        # new seq → falls through is_new_event check → re-checks sensors → still ok
        assert fsm.state == R2State.INSERTING
        assert out.action_hint in ("insert_head", "continue_insert")


# ===================================================================
# WEAPON_LOCKED — timing variants
# ===================================================================


class TestWeaponLocked:
    """WEAPON_LOCKED must only trigger head release when R2 has actually inserted."""

    def test_from_inserting_releases_head(self) -> None:
        fsm = _fsm_at(R2State.INSERTING)
        out = fsm.update(_beacon(MsgID.WEAPON_LOCKED, 0), R2Sensors())
        assert fsm.state == R2State.HEAD_RELEASED
        assert out.action_hint == "release_head_and_retreat"

    def test_with_insertion_motion_done_releases_head(self) -> None:
        """If insertion motion is complete (sensor), WEAPON_LOCKED should release."""
        fsm = _fsm_at(R2State.SEARCH_R1_TAG)
        sensors = R2Sensors(insertion_motion_done=True)
        out = fsm.update(_beacon(MsgID.WEAPON_LOCKED, 0), sensors)
        assert fsm.state == R2State.HEAD_RELEASED
        assert out.action_hint == "release_head_and_retreat"

    def test_early_before_insertion_is_gated(self) -> None:
        """WEAPON_LOCKED arriving before insertion must NOT trigger release."""
        fsm = R2MissionFSM()  # WAIT_R1
        sensors = R2Sensors(insertion_motion_done=False)
        out = fsm.update(_beacon(MsgID.WEAPON_LOCKED, 0), sensors)
        assert fsm.state != R2State.HEAD_RELEASED
        assert out.action_hint == "wait_insert_complete"
        assert out.reason == "weapon_locked_seen_early"


# ===================================================================
# R1_CLEAR_MC — sequence gating
# ===================================================================


class TestR1ClearMc:
    """R1_CLEAR_MC requires R2 to have released the head first."""

    def test_from_head_released_allows_leave_mc(self) -> None:
        fsm = _fsm_at(R2State.HEAD_RELEASED)
        out = fsm.update(_beacon(MsgID.R1_CLEAR_MC, 0), R2Sensors())
        assert fsm.state == R2State.READY_TO_LEAVE_MC
        assert out.action_hint == "leave_mc"

    def test_from_wait_r1_clear_mc_allows_leave_mc(self) -> None:
        fsm = _fsm_at(R2State.WAIT_R1_CLEAR_MC)
        out = fsm.update(_beacon(MsgID.R1_CLEAR_MC, 0), R2Sensors())
        assert fsm.state == R2State.READY_TO_LEAVE_MC
        assert out.action_hint == "leave_mc"

    def test_too_early_before_head_release_is_gated(self) -> None:
        """R1_CLEAR_MC arriving while R2 is still INSERTING must be gated."""
        fsm = _fsm_at(R2State.INSERTING)
        out = fsm.update(_beacon(MsgID.R1_CLEAR_MC, 0), R2Sensors())
        assert fsm.state == R2State.INSERTING  # unchanged
        assert out.action_hint == "wait_head_release"
        assert out.reason == "r1_clear_mc_seen_early"

    def test_from_wait_r1_unless_in_allowed_state_is_gated(self) -> None:
        """R1_CLEAR_MC from WAIT_R1 should also be gated."""
        fsm = R2MissionFSM()
        out = fsm.update(_beacon(MsgID.R1_CLEAR_MC, 0), R2Sensors())
        assert fsm.state == R2State.WAIT_R1  # unchanged
        assert out.action_hint == "wait_head_release"


# ===================================================================
# R1_IN_MF — sequence gating (must come after R1_CLEAR_MC)
# ===================================================================


class TestR1InMf:
    """R1_IN_MF must only be accepted after R2 is READY_TO_LEAVE_MC."""

    def test_from_ready_to_leave_enters_mf(self) -> None:
        fsm = _fsm_at(R2State.READY_TO_LEAVE_MC)
        out = fsm.update(_beacon(MsgID.R1_IN_MF, 0), R2Sensors())
        assert fsm.state == R2State.READY_TO_ENTER_MF
        assert out.action_hint == "enter_mf"

    def test_too_early_before_clear_mc_is_gated(self) -> None:
        """R1_IN_MF before R1_CLEAR_MC must not allow MF entry."""
        fsm = _fsm_at(R2State.HEAD_RELEASED)
        out = fsm.update(_beacon(MsgID.R1_IN_MF, 0), R2Sensors())
        assert fsm.state == R2State.HEAD_RELEASED  # unchanged
        assert out.action_hint == "wait_clear_mc_first"
        assert out.reason == "r1_in_mf_seen_early"

    def test_from_wait_r1_is_gated(self) -> None:
        fsm = R2MissionFSM()
        out = fsm.update(_beacon(MsgID.R1_IN_MF, 0), R2Sensors())
        assert fsm.state != R2State.READY_TO_ENTER_MF
        assert out.action_hint == "wait_clear_mc_first"


# ===================================================================
# R1_AT_ASSEMBLY_POSE — head_grabbed gating
# ===================================================================


class TestAtAssemblyPose:
    def test_without_head_grabbed_does_not_search_tag(self) -> None:
        """R1 reaching assembly pose is meaningless if R2 hasn't grabbed the head."""
        fsm = _fsm_at(R2State.PREPARE_HEAD)
        sensors = R2Sensors(head_grabbed=False)
        out = fsm.update(_beacon(MsgID.R1_AT_ASSEMBLY_POSE, 0), sensors)
        assert fsm.state != R2State.SEARCH_R1_TAG
        # State stays PREPARE_HEAD because head_grabbed is False,
        # and R1_AT_ASSEMBLY_POSE rule requires head_grabbed.
        assert out.action_hint != "search_r1_tag"

    def test_with_head_grabbed_searches_tag(self) -> None:
        fsm = _fsm_at(R2State.PREPARE_HEAD)
        sensors = R2Sensors(head_grabbed=True)
        out = fsm.update(_beacon(MsgID.R1_AT_ASSEMBLY_POSE, 0), sensors)
        assert fsm.state == R2State.SEARCH_R1_TAG
        assert out.action_hint == "search_r1_tag"


# ===================================================================
# Full sequence — integration (preserved from original tests)
# ===================================================================


class TestFullSequence:
    def test_r2_only_inserts_when_local_ready(self) -> None:
        """Original test — INSERT_ALLOWED gated by head_grabbed."""
        fsm = R2MissionFSM()
        sensors = R2Sensors(head_grabbed=False, r1_tag_visible=True, pre_insert_pose_ok=True)
        out = fsm.update(_beacon(MsgID.INSERT_ALLOWED), sensors)
        assert fsm.state != R2State.INSERTING
        assert out.action_hint == "wait_local_ready"

        sensors.head_grabbed = True
        out = fsm.update(_beacon(MsgID.INSERT_ALLOWED, seq=1), sensors)
        assert fsm.state == R2State.INSERTING
        assert out.action_hint == "insert_head"

    def test_full_happy_path_to_enter_mf(self) -> None:
        """Original full-sequence test."""
        fsm = R2MissionFSM()
        sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)

        assert fsm.update(_beacon(MsgID.R1_ROD_CLAMPED), sensors).action_hint == "grab_head"
        assert fsm.update(_beacon(MsgID.R1_AT_ASSEMBLY_POSE, 1), sensors).action_hint == "search_r1_tag"
        assert fsm.update(_beacon(MsgID.INSERT_ALLOWED, 0), sensors).action_hint == "insert_head"

        sensors.insertion_motion_done = True
        assert fsm.update(_beacon(MsgID.WEAPON_LOCKED, 1), sensors).action_hint == "release_head_and_retreat"
        assert fsm.update(_beacon(MsgID.R1_CLEAR_MC, 0), sensors).action_hint == "leave_mc"
        assert fsm.update(_beacon(MsgID.R1_IN_MF, 1), sensors).action_hint == "enter_mf"
        assert fsm.state == R2State.READY_TO_ENTER_MF


# ===================================================================
# Reset
# ===================================================================


class TestReset:
    def test_reset_returns_to_wait_r1(self) -> None:
        sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        fsm = R2MissionFSM()
        fsm.update(_beacon(MsgID.R1_ROD_CLAMPED, 0), sensors)
        fsm.update(_beacon(MsgID.R1_AT_ASSEMBLY_POSE, 1), sensors)
        fsm.update(_beacon(MsgID.INSERT_ALLOWED, 0), sensors)
        assert fsm.state == R2State.INSERTING

        out = fsm.reset()
        assert fsm.state == R2State.WAIT_R1
        assert fsm.last_seq is None
        assert fsm.last_msg_id is None
        assert out.action_hint == "wait"


# ===================================================================
# Edge cases
# ===================================================================


class TestEdgeCases:
    def test_no_matching_transition_returns_wait(self) -> None:
        """Any message without a matching rule must return 'wait' and not crash."""
        fsm = R2MissionFSM()
        # DEBUG msg has no transition rule
        out = fsm.update(_beacon(MsgID.DEBUG, 0), R2Sensors())
        assert fsm.state == R2State.WAIT_R1
        assert out.action_hint == "wait"

    def test_seq_update_persists_even_on_wait(self) -> None:
        """last_msg_id/last_seq must be updated even when no transition fires."""
        fsm = R2MissionFSM()
        fsm.update(_beacon(MsgID.R1_ROD_CLAMPED, 1), R2Sensors())
        assert fsm.last_msg_id == MsgID.R1_ROD_CLAMPED
        assert fsm.last_seq == 1

    def test_head_grabbed_auto_advances_to_search_tag_in_prepare_head(self) -> None:
        """When in PREPARE_HEAD with head_grabbed=True, FSM auto-advances to SEARCH_R1_TAG.

        This transition is sensor-driven: any beacon event (even the same one that
        triggered PREPARE_HEAD) causes the FSM to check head_grabbed and advance.
        This means PREPARE_HEAD is a transient state — once the head is grabbed,
        the next beacon immediately moves R2 to SEARCH_R1_TAG.
        """
        sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        fsm = R2MissionFSM()

        # First R1_ROD_CLAMPED → PREPARE_HEAD
        out1 = fsm.update(_beacon(MsgID.R1_ROD_CLAMPED, 0), sensors)
        assert fsm.state == R2State.PREPARE_HEAD
        assert out1.action_hint == "grab_head"

        # Second R1_ROD_CLAMPED with SAME seq → sensor check fires,
        # head_grabbed=True triggers advance to SEARCH_R1_TAG.
        out2 = fsm.update(_beacon(MsgID.R1_ROD_CLAMPED, 0), sensors)
        assert fsm.state == R2State.SEARCH_R1_TAG
        assert out2.action_hint in ("search_r1_tag", "wait")


# ===================================================================
# HOLD state — must not be escapable by normal messages
# ===================================================================


class TestHoldStateResilience:
    """Once in HOLD, only HOLD/ERROR/ABORT/ESTOP should affect state.

    HOLD is a safety barrier: R1 has told R2 to stop. Normal task messages
    (INSERT_ALLOWED, WEAPON_LOCKED, etc.) must NOT cause R2 to leave HOLD
    and resume autonomous actions.
    """

    def test_hold_receiving_hold_stays_hold(self) -> None:
        fsm = _fsm_at(R2State.HOLD)
        out = fsm.update(_beacon(MsgID.HOLD, 1), R2Sensors())
        assert fsm.state == R2State.HOLD
        assert out.action_hint == "hold"

    def test_hold_receiving_error_goes_to_error(self) -> None:
        """ERROR is higher severity than HOLD — HOLD→ERROR is correct."""
        fsm = _fsm_at(R2State.HOLD)
        out = fsm.update(_beacon(MsgID.ERROR, 0), R2Sensors())
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "hold"

    def test_hold_receiving_abort_stays_hold(self) -> None:
        fsm = _fsm_at(R2State.HOLD)
        out = fsm.update(_beacon(MsgID.ABORT_CURRENT_TASK, 0), R2Sensors())
        assert fsm.state == R2State.HOLD
        assert out.action_hint == "hold"

    def test_hold_receiving_estop_goes_to_error(self) -> None:
        fsm = _fsm_at(R2State.HOLD)
        sensors = R2Sensors(estop=True)
        out = fsm.update(_beacon(MsgID.R1_ROD_CLAMPED, 0), sensors)
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "stop_all"

    def test_hold_insert_allowed_with_all_sensors_ready(self) -> None:
        """SAFETY: INSERT_ALLOWED from HOLD is blocked by the HOLD safety gate.

        Even with all local sensors ready, the FSM must refuse to leave HOLD
        upon receiving a normal task message.
        """
        fsm = _fsm_at(R2State.HOLD)
        sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        out = fsm.update(_beacon(MsgID.INSERT_ALLOWED, 0), sensors)
        assert fsm.state == R2State.HOLD  # safety gate blocks insertion
        assert out.action_hint == "hold_active"
        assert "hold_active" in out.reason

    def test_hold_weapon_locked_is_gated(self) -> None:
        """WEAPON_LOCKED from HOLD is blocked by the HOLD safety gate."""
        fsm = _fsm_at(R2State.HOLD)
        sensors = R2Sensors(insertion_motion_done=False)
        out = fsm.update(_beacon(MsgID.WEAPON_LOCKED, 0), sensors)
        assert fsm.state == R2State.HOLD
        assert out.action_hint == "hold_active"

    def test_hold_weapon_locked_with_insertion_done_blocked(self) -> None:
        """WEAPON_LOCKED from HOLD even with insertion_motion_done=True is blocked.

        Previously this would release the head, but HOLD safety gate now
        prevents it.
        """
        fsm = _fsm_at(R2State.HOLD)
        sensors = R2Sensors(insertion_motion_done=True)
        out = fsm.update(_beacon(MsgID.WEAPON_LOCKED, 0), sensors)
        assert fsm.state == R2State.HOLD
        assert out.action_hint == "hold_active"

    def test_hold_r1_clear_mc_is_blocked(self) -> None:
        """R1_CLEAR_MC from HOLD is blocked by safety gate."""
        fsm = _fsm_at(R2State.HOLD)
        out = fsm.update(_beacon(MsgID.R1_CLEAR_MC, 0), R2Sensors())
        assert fsm.state == R2State.HOLD
        assert out.action_hint == "hold_active"

    def test_hold_r1_in_mf_is_blocked(self) -> None:
        """R1_IN_MF from HOLD is blocked by safety gate."""
        fsm = _fsm_at(R2State.HOLD)
        out = fsm.update(_beacon(MsgID.R1_IN_MF, 0), R2Sensors())
        assert fsm.state == R2State.HOLD
        assert out.action_hint == "hold_active"

    def test_hold_r1_rod_clamped_blocked(self) -> None:
        """R1_ROD_CLAMPED from HOLD is blocked by safety gate."""
        fsm = _fsm_at(R2State.HOLD)
        out = fsm.update(_beacon(MsgID.R1_ROD_CLAMPED, 0), R2Sensors())
        assert fsm.state == R2State.HOLD
        assert out.action_hint == "hold_active"

    def test_hold_r1_at_assembly_pose_blocked(self) -> None:
        """R1_AT_ASSEMBLY_POSE from HOLD is blocked by safety gate."""
        fsm = _fsm_at(R2State.HOLD)
        sensors = R2Sensors(head_grabbed=True)
        out = fsm.update(_beacon(MsgID.R1_AT_ASSEMBLY_POSE, 0), sensors)
        assert fsm.state == R2State.HOLD
        assert out.action_hint == "hold_active"

    def test_hold_irrelevant_msg_blocked(self) -> None:
        """Any normal message from HOLD is blocked by safety gate."""
        fsm = _fsm_at(R2State.HOLD)
        for msg_id in (MsgID.DEBUG, MsgID.TEST, MsgID.GRID_TARGET_1, MsgID.IDLE):
            out = fsm.update(_beacon(msg_id, 0), R2Sensors())
            assert fsm.state == R2State.HOLD
            assert out.action_hint == "hold_active"


# ===================================================================
# ERROR state — must not be escapable by normal messages
# ===================================================================


class TestErrorStateResilience:
    """Once in ERROR, only ESTOP should persist ERROR; HOLD/ABORT can downgrade.

    ERROR is the highest non-ESTOP severity. Normal task messages must NOT
    cause R2 to leave ERROR and resume autonomous actions.
    """

    def test_error_receiving_error_stays_error(self) -> None:
        fsm = _fsm_at(R2State.ERROR)
        out = fsm.update(_beacon(MsgID.ERROR, 1), R2Sensors())
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "hold"

    def test_error_receiving_hold_downgrades_to_hold(self) -> None:
        """HOLD from ERROR goes to HOLD — R1 is explicitly requesting hold."""
        fsm = _fsm_at(R2State.ERROR)
        out = fsm.update(_beacon(MsgID.HOLD, 0), R2Sensors())
        assert fsm.state == R2State.HOLD
        assert out.action_hint == "hold"

    def test_error_receiving_abort_goes_to_hold(self) -> None:
        fsm = _fsm_at(R2State.ERROR)
        out = fsm.update(_beacon(MsgID.ABORT_CURRENT_TASK, 0), R2Sensors())
        assert fsm.state == R2State.HOLD
        assert out.action_hint == "hold"

    def test_error_receiving_estop_stays_error(self) -> None:
        fsm = _fsm_at(R2State.ERROR)
        sensors = R2Sensors(estop=True)
        out = fsm.update(_beacon(MsgID.R1_ROD_CLAMPED, 0), sensors)
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "stop_all"

    def test_error_insert_allowed_is_blocked(self) -> None:
        """SAFETY: INSERT_ALLOWED from ERROR is blocked by the ERROR safety gate."""
        fsm = _fsm_at(R2State.ERROR)
        sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        out = fsm.update(_beacon(MsgID.INSERT_ALLOWED, 0), sensors)
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "hold_active"
        assert "error_active" in out.reason

    def test_error_weapon_locked_is_blocked(self) -> None:
        """WEAPON_LOCKED from ERROR is blocked by safety gate."""
        fsm = _fsm_at(R2State.ERROR)
        sensors = R2Sensors(insertion_motion_done=False)
        out = fsm.update(_beacon(MsgID.WEAPON_LOCKED, 0), sensors)
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "hold_active"

    def test_error_r1_clear_mc_is_blocked(self) -> None:
        fsm = _fsm_at(R2State.ERROR)
        out = fsm.update(_beacon(MsgID.R1_CLEAR_MC, 0), R2Sensors())
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "hold_active"

    def test_error_r1_in_mf_is_blocked(self) -> None:
        fsm = _fsm_at(R2State.ERROR)
        out = fsm.update(_beacon(MsgID.R1_IN_MF, 0), R2Sensors())
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "hold_active"

    def test_error_irrelevant_msg_blocked(self) -> None:
        fsm = _fsm_at(R2State.ERROR)
        for msg_id in (MsgID.DEBUG, MsgID.TEST, MsgID.R1_ROD_CLAMPED):
            out = fsm.update(_beacon(msg_id, 0), R2Sensors())
            assert fsm.state == R2State.ERROR
            assert out.action_hint == "hold_active"


# ===================================================================
# Vision messages must NEVER bypass local safety conditions
# ===================================================================


class TestVisionCannotBypassSafety:
    """The vision system provides hints — local sensors and FSM are the gate.

    Even with a valid, correct beacon message, R2 must NOT execute a dangerous
    action unless local sensors confirm the precondition.
    """

    def test_insert_allowed_without_head_grabbed_from_any_state(self) -> None:
        """INSERT_ALLOWED without head_grabbed must NEVER trigger insertion."""
        for state in (R2State.WAIT_R1, R2State.SEARCH_R1_TAG, R2State.PREPARE_HEAD,
                       R2State.HOLD, R2State.ERROR, R2State.HEAD_RELEASED):
            fsm = _fsm_at(state)
            sensors = R2Sensors(head_grabbed=False, r1_tag_visible=True, pre_insert_pose_ok=True)
            out = fsm.update(_beacon(MsgID.INSERT_ALLOWED, 0), sensors)
            assert fsm.state != R2State.INSERTING, f"INSERT_ALLOWED from {state} without head_grabbed must not insert"
            assert out.action_hint != "insert_head", f"from {state}: {out.action_hint}"

    def test_insert_allowed_without_tag_visible_from_any_state(self) -> None:
        """INSERT_ALLOWED without r1_tag_visible must NEVER trigger insertion."""
        for state in (R2State.WAIT_R1, R2State.SEARCH_R1_TAG, R2State.PREPARE_HEAD,
                       R2State.HOLD, R2State.ERROR):
            fsm = _fsm_at(state)
            sensors = R2Sensors(head_grabbed=True, r1_tag_visible=False, pre_insert_pose_ok=True)
            out = fsm.update(_beacon(MsgID.INSERT_ALLOWED, 0), sensors)
            assert fsm.state != R2State.INSERTING, f"INSERT_ALLOWED from {state} without tag_visible must not insert"
            assert out.action_hint != "insert_head", f"from {state}: {out.action_hint}"

    def test_insert_allowed_without_pre_insert_pose_from_any_state(self) -> None:
        """INSERT_ALLOWED without pre_insert_pose_ok must NEVER trigger insertion."""
        for state in (R2State.WAIT_R1, R2State.SEARCH_R1_TAG, R2State.PREPARE_HEAD,
                       R2State.HOLD, R2State.ERROR):
            fsm = _fsm_at(state)
            sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=False)
            out = fsm.update(_beacon(MsgID.INSERT_ALLOWED, 0), sensors)
            assert fsm.state != R2State.INSERTING, f"INSERT_ALLOWED from {state} without pose_ok must not insert"
            assert out.action_hint != "insert_head", f"from {state}: {out.action_hint}"

    def test_weapon_locked_without_insertion_never_releases_head(self) -> None:
        """WEAPON_LOCKED without insertion context must NEVER release head.

        Tested from states where R2 has NOT completed insertion.
        """
        for state in (R2State.WAIT_R1, R2State.PREPARE_HEAD, R2State.SEARCH_R1_TAG):
            fsm = _fsm_at(state)
            sensors = R2Sensors(insertion_motion_done=False)
            out = fsm.update(_beacon(MsgID.WEAPON_LOCKED, 0), sensors)
            assert fsm.state != R2State.HEAD_RELEASED, f"WEAPON_LOCKED from {state} without insertion must not release"
            assert out.action_hint != "release_head_and_retreat"

    def test_r1_clear_mc_without_head_release_is_gated(self) -> None:
        """R1_CLEAR_MC before head release must NEVER allow leaving MC."""
        for state in (R2State.WAIT_R1, R2State.PREPARE_HEAD, R2State.SEARCH_R1_TAG,
                       R2State.INSERTING, R2State.HOLD, R2State.ERROR):
            fsm = _fsm_at(state)
            out = fsm.update(_beacon(MsgID.R1_CLEAR_MC, 0), R2Sensors())
            assert fsm.state != R2State.READY_TO_LEAVE_MC, f"R1_CLEAR_MC from {state} must not allow leave_mc"
            assert out.action_hint != "leave_mc"

    def test_r1_in_mf_without_clear_mc_is_gated(self) -> None:
        """R1_IN_MF before R1_CLEAR_MC must NEVER allow entering MF."""
        for state in (R2State.WAIT_R1, R2State.PREPARE_HEAD, R2State.SEARCH_R1_TAG,
                       R2State.INSERTING, R2State.HEAD_RELEASED, R2State.HOLD, R2State.ERROR):
            fsm = _fsm_at(state)
            out = fsm.update(_beacon(MsgID.R1_IN_MF, 0), R2Sensors())
            assert fsm.state != R2State.READY_TO_ENTER_MF, f"R1_IN_MF from {state} must not enter MF"
            assert out.action_hint != "enter_mf"

    def test_invalid_beacon_never_triggers_action(self) -> None:
        """An invalid beacon must NEVER produce an action hint other than 'ignore'."""
        for state in R2State:
            fsm = _fsm_at(state)
            sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True,
                                insertion_motion_done=True)
            out = fsm.update(_invalid_beacon(), sensors)
            assert out.action_hint == "ignore", f"invalid beacon from {state} gave '{out.action_hint}'"

    def test_unknown_msg_never_triggers_action(self) -> None:
        """An unknown msg_id must NEVER produce an action hint other than 'ignore'."""
        from robocon_coop_comm.protocol import DecodedBeacon as ProtoBeacon
        unknown = ProtoBeacon(msg_id=99, seq=0, valid=True, bits={})
        for state in R2State:
            fsm = _fsm_at(state)
            out = fsm.update(unknown, R2Sensors())
            assert out.action_hint == "ignore", f"unknown msg from {state} gave '{out.action_hint}'"

    def test_no_msg_can_bypass_estop(self) -> None:
        """ESTOP active + any valid message = ERROR, action_hint='stop_all'.

        No amount of valid messages should override ESTOP.
        """
        sensors = R2Sensors(estop=True, head_grabbed=True, r1_tag_visible=True,
                            pre_insert_pose_ok=True, insertion_motion_done=True)
        all_msgs = [m for m in MsgID]
        fsm = R2MissionFSM()
        for msg in all_msgs:
            fsm.state = R2State.INSERTING  # reset to a non-ERROR state each time
            out = fsm.update(_beacon(msg, 0), sensors)
            assert fsm.state == R2State.ERROR, f"ESTOP + {msg.name} should → ERROR, got {fsm.state}"
            assert out.action_hint == "stop_all", f"ESTOP + {msg.name} action: {out.action_hint}"


# ===================================================================
# RETRY_RESET — recovery from HOLD/ERROR
# ===================================================================


class TestRetryReset:
    """RETRY_RESET (MsgID 15) handling.

    Current behaviour: RETRY_RESET has no dedicated handler, falls through
    to 'no_matching_transition'. Documenting this for future implementation.
    """

    def test_retry_reset_from_wait_r1_is_noop(self) -> None:
        fsm = R2MissionFSM()
        out = fsm.update(_beacon(MsgID.RETRY_RESET, 0), R2Sensors())
        assert fsm.state == R2State.WAIT_R1
        assert out.action_hint == "wait"
        assert out.reason == "no_matching_transition"

    def test_retry_reset_from_hold_is_blocked(self) -> None:
        """RETRY_RESET from HOLD is blocked by the safety gate.

        Future: if RETRY_RESET should recover from HOLD, add it to the
        HOLD/ERROR/ABORT override list in R2MissionFSM.update().
        """
        fsm = _fsm_at(R2State.HOLD)
        out = fsm.update(_beacon(MsgID.RETRY_RESET, 0), R2Sensors())
        assert fsm.state == R2State.HOLD
        assert out.action_hint == "hold_active"

    def test_retry_reset_from_error_is_blocked(self) -> None:
        """RETRY_RESET from ERROR is blocked by the safety gate."""
        fsm = _fsm_at(R2State.ERROR)
        out = fsm.update(_beacon(MsgID.RETRY_RESET, 0), R2Sensors())
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "hold_active"

    def test_retry_reset_from_inserting_is_noop(self) -> None:
        fsm = _fsm_at(R2State.INSERTING)
        out = fsm.update(_beacon(MsgID.RETRY_RESET, 0), R2Sensors())
        assert fsm.state == R2State.INSERTING
        assert out.action_hint == "wait"


# ===================================================================
# Duplicate seq debounce — all handled message types
# ===================================================================


class TestDuplicateSeqDebounceAll:
    """Duplicate seq+msg_id pairs should not retrigger one-shot actions.

    The FSM tracks (last_msg_id, last_seq) and uses is_new_event to gate
    re-evaluation. This applies to ALL messages, not just INSERT_ALLOWED.
    """

    def test_duplicate_weapon_locked_while_not_inserting_is_gated(self) -> None:
        """Same WEAPON_LOCKED seq from HEAD_RELEASED without insertion_done → gated.

        WEAPON_LOCKED checks (state==INSERTING or insertion_motion_done).
        From HEAD_RELEASED with insertion_motion_done=False, both are false → gated.
        """
        fsm = _fsm_at(R2State.HEAD_RELEASED, last_msg_id=MsgID.WEAPON_LOCKED, last_seq=0)
        out = fsm.update(_beacon(MsgID.WEAPON_LOCKED, 0), R2Sensors())
        # WEAPON_LOCKED gate: state!=INSERTING and !insertion_motion_done → gated
        assert out.action_hint == "wait_insert_complete"
        assert out.reason == "weapon_locked_seen_early"

    def test_duplicate_r1_clear_mc_while_ready_to_leave(self) -> None:
        """Same R1_CLEAR_MC seq from READY_TO_LEAVE_MC should wait."""
        fsm = _fsm_at(R2State.READY_TO_LEAVE_MC, last_msg_id=MsgID.R1_CLEAR_MC, last_seq=0)
        out = fsm.update(_beacon(MsgID.R1_CLEAR_MC, 0), R2Sensors())
        # R1_CLEAR_MC requires state in (HEAD_RELEASED, WAIT_R1_CLEAR_MC)
        # READY_TO_LEAVE_MC is neither → gated
        assert out.action_hint == "wait_head_release"

    def test_duplicate_r1_in_mf_while_ready_to_enter(self) -> None:
        """Same R1_IN_MF seq from READY_TO_ENTER_MF should wait."""
        fsm = _fsm_at(R2State.READY_TO_ENTER_MF, last_msg_id=MsgID.R1_IN_MF, last_seq=0)
        out = fsm.update(_beacon(MsgID.R1_IN_MF, 0), R2Sensors())
        # R1_IN_MF requires READY_TO_LEAVE_MC → gated from READY_TO_ENTER_MF
        assert out.action_hint == "wait_clear_mc_first"

    def test_duplicate_rod_clamped_from_prepare_head(self) -> None:
        """Same R1_ROD_CLAMPED seq from PREPARE_HEAD should wait (not WAIT_R1)."""
        fsm = _fsm_at(R2State.PREPARE_HEAD, last_msg_id=MsgID.R1_ROD_CLAMPED, last_seq=0)
        out = fsm.update(_beacon(MsgID.R1_ROD_CLAMPED, 0), R2Sensors())
        # R1_ROD_CLAMPED only from WAIT_R1 → wait
        assert out.action_hint == "wait"

    def test_new_seq_same_msg_id_re_evaluates(self) -> None:
        """A new seq with the same msg_id IS a new event — should re-evaluate."""
        fsm = _fsm_at(R2State.INSERTING, last_msg_id=MsgID.INSERT_ALLOWED, last_seq=1)
        sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        out = fsm.update(_beacon(MsgID.INSERT_ALLOWED, 0), sensors)
        # seq 0 != last_seq 1 → is_new_event=True → re-evaluates
        # All sensors ready → insert_head
        assert out.action_hint in ("insert_head", "continue_insert")

    def test_seq_tracking_updated_even_when_no_transition(self) -> None:
        """last_msg_id/last_seq must be updated even when message causes no transition."""
        fsm = R2MissionFSM()
        # DEBUG has no handler
        fsm.update(_beacon(MsgID.DEBUG, 1), R2Sensors())
        assert fsm.last_msg_id == MsgID.DEBUG
        assert fsm.last_seq == 1
        # Send DEBUG again with same seq → is_new_event=False
        out = fsm.update(_beacon(MsgID.DEBUG, 1), R2Sensors())
        assert out.action_hint == "wait"


# ===================================================================
# Comprehensive MsgID coverage from key states
# ===================================================================


class TestAllMsgIdsFromWaitR1:
    """Every defined MsgID sent while in WAIT_R1 — no crash, predictable output."""

    def test_all_msg_ids_from_wait_r1_no_crash(self) -> None:
        fsm = R2MissionFSM()
        for msg in MsgID:
            fsm.state = R2State.WAIT_R1
            fsm.last_msg_id = None
            fsm.last_seq = None
            out = fsm.update(_beacon(msg, 0), R2Sensors())
            assert out.state in R2State, f"MsgID.{msg.name} produced invalid state"
            assert isinstance(out.action_hint, str)
            assert isinstance(out.reason, str)

    def test_known_transitions_from_wait_r1(self) -> None:
        """Messages with explicit WAIT_R1 handlers."""
        fsm = R2MissionFSM()
        # R1_ROD_CLAMPED → PREPARE_HEAD
        out = fsm.update(_beacon(MsgID.R1_ROD_CLAMPED, 0), R2Sensors())
        assert fsm.state == R2State.PREPARE_HEAD

        # HOLD → HOLD
        fsm2 = R2MissionFSM()
        out2 = fsm2.update(_beacon(MsgID.HOLD, 0), R2Sensors())
        assert fsm2.state == R2State.HOLD

        # ERROR → ERROR
        fsm3 = R2MissionFSM()
        out3 = fsm3.update(_beacon(MsgID.ERROR, 0), R2Sensors())
        assert fsm3.state == R2State.ERROR

        # ABORT_CURRENT_TASK → HOLD
        fsm4 = R2MissionFSM()
        out4 = fsm4.update(_beacon(MsgID.ABORT_CURRENT_TASK, 0), R2Sensors())
        assert fsm4.state == R2State.HOLD

    def test_unhandled_msgs_from_wait_r1_stay_wait_r1(self) -> None:
        """Messages without explicit handlers should keep WAIT_R1."""
        unhandled = [
            MsgID.IDLE, MsgID.R1_ATTACK_READY, MsgID.R1_WAIT_R2,
            MsgID.LIFT_DOCK_READY, MsgID.R2_ON_LIFT_DETECTED,
            MsgID.TOP_RELEASE_ALLOWED, MsgID.DESCEND_ALLOWED,
            MsgID.RETRY_RESET, MsgID.DEBUG, MsgID.TEST,
        ] + [getattr(MsgID, f"GRID_TARGET_{i}") for i in range(1, 10)]

        for msg in unhandled:
            fsm = R2MissionFSM()
            out = fsm.update(_beacon(msg, 0), R2Sensors())
            assert fsm.state == R2State.WAIT_R1, f"MsgID.{msg.name} should keep WAIT_R1"
            assert out.action_hint == "wait"
            assert out.reason == "no_matching_transition"


class TestAllMsgIdsFromInserting:
    """Every MsgID sent while in INSERTING — safety checks still apply."""

    def test_all_msg_ids_from_inserting_no_crash(self) -> None:
        sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        for msg in MsgID:
            fsm = _fsm_at(R2State.INSERTING, last_msg_id=MsgID.INSERT_ALLOWED, last_seq=0)
            out = fsm.update(_beacon(msg, 1), sensors)
            assert out.state in R2State, f"MsgID.{msg.name} from INSERTING crashed or bad state"
            assert isinstance(out.action_hint, str)

    def test_hold_overrides_inserting(self) -> None:
        """HOLD/ERROR/ABORT must override even active insertion."""
        fsm = _fsm_at(R2State.INSERTING)
        out = fsm.update(_beacon(MsgID.HOLD, 1), R2Sensors())
        assert fsm.state == R2State.HOLD
        assert out.action_hint == "hold"

    def test_error_overrides_inserting(self) -> None:
        fsm = _fsm_at(R2State.INSERTING)
        out = fsm.update(_beacon(MsgID.ERROR, 1), R2Sensors())
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "hold"

    def test_abort_overrides_inserting(self) -> None:
        fsm = _fsm_at(R2State.INSERTING)
        out = fsm.update(_beacon(MsgID.ABORT_CURRENT_TASK, 1), R2Sensors())
        assert fsm.state == R2State.HOLD
        assert out.action_hint == "hold"


# ===================================================================
# PRE_INSERT_READY — defined but unused state
# ===================================================================


class TestPreInsertReady:
    """PRE_INSERT_READY is defined in R2State enum but never set by any transition.

    Tests document current behaviour and ensure the FSM handles this state
    gracefully if it were ever set externally.
    """

    def test_pre_insert_ready_defined_in_enum(self) -> None:
        assert hasattr(R2State, "PRE_INSERT_READY")

    def test_any_msg_from_pre_insert_ready_no_crash(self) -> None:
        """FSM must not crash when in PRE_INSERT_READY, regardless of message."""
        sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        fsm = _fsm_at(R2State.PRE_INSERT_READY)
        for msg in MsgID:
            fsm.state = R2State.PRE_INSERT_READY
            fsm.last_msg_id = None
            fsm.last_seq = None
            out = fsm.update(_beacon(msg, 0), sensors)
            assert out.state in R2State

    def test_insert_allowed_from_pre_insert_ready_with_sensors(self) -> None:
        """INSERT_ALLOWED from PRE_INSERT_READY with all sensors → INSERTING.

        Since INSERT_ALLOWED doesn't gate on current state, this works.
        """
        fsm = _fsm_at(R2State.PRE_INSERT_READY)
        sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        out = fsm.update(_beacon(MsgID.INSERT_ALLOWED, 0), sensors)
        # Documents current behaviour
        assert out.action_hint in ("insert_head", "wait_local_ready")

    def test_hold_from_pre_insert_ready_works(self) -> None:
        fsm = _fsm_at(R2State.PRE_INSERT_READY)
        out = fsm.update(_beacon(MsgID.HOLD, 0), R2Sensors())
        assert fsm.state == R2State.HOLD


# ===================================================================
# HEAD_RELEASED state — post-insertion behaviour
# ===================================================================


class TestHeadReleased:
    """Tests for HEAD_RELEASED state transitions."""

    def test_r1_clear_mc_from_head_released_transitions(self) -> None:
        fsm = _fsm_at(R2State.HEAD_RELEASED)
        out = fsm.update(_beacon(MsgID.R1_CLEAR_MC, 0), R2Sensors())
        assert fsm.state == R2State.READY_TO_LEAVE_MC
        assert out.action_hint == "leave_mc"

    def test_hold_from_head_released(self) -> None:
        fsm = _fsm_at(R2State.HEAD_RELEASED)
        out = fsm.update(_beacon(MsgID.HOLD, 0), R2Sensors())
        assert fsm.state == R2State.HOLD

    def test_error_from_head_released(self) -> None:
        fsm = _fsm_at(R2State.HEAD_RELEASED)
        out = fsm.update(_beacon(MsgID.ERROR, 0), R2Sensors())
        assert fsm.state == R2State.ERROR

    def test_irrelevant_msg_from_head_released_no_effect(self) -> None:
        fsm = _fsm_at(R2State.HEAD_RELEASED)
        out = fsm.update(_beacon(MsgID.R1_ROD_CLAMPED, 0), R2Sensors())
        assert fsm.state == R2State.HEAD_RELEASED
        assert out.action_hint == "wait"


# ===================================================================
# WAIT_R1_CLEAR_MC state
# ===================================================================


class TestWaitR1ClearMc:
    """WAIT_R1_CLEAR_MC is an intermediate state for R2 to wait in."""

    def test_r1_clear_mc_from_wait_r1_clear_mc_transitions(self) -> None:
        fsm = _fsm_at(R2State.WAIT_R1_CLEAR_MC)
        out = fsm.update(_beacon(MsgID.R1_CLEAR_MC, 0), R2Sensors())
        assert fsm.state == R2State.READY_TO_LEAVE_MC
        assert out.action_hint == "leave_mc"

    def test_hold_from_wait_r1_clear_mc(self) -> None:
        fsm = _fsm_at(R2State.WAIT_R1_CLEAR_MC)
        out = fsm.update(_beacon(MsgID.HOLD, 0), R2Sensors())
        assert fsm.state == R2State.HOLD

    def test_weapon_locked_from_wait_r1_clear_mc_is_gated(self) -> None:
        fsm = _fsm_at(R2State.WAIT_R1_CLEAR_MC)
        sensors = R2Sensors(insertion_motion_done=False)
        out = fsm.update(_beacon(MsgID.WEAPON_LOCKED, 0), sensors)
        assert fsm.state != R2State.HEAD_RELEASED
        assert out.action_hint == "wait_insert_complete"


# ===================================================================
# READY_TO_LEAVE_MC / READY_TO_ENTER_MF — terminal states
# ===================================================================


class TestTerminalStates:
    """Tests for near-terminal states."""

    def test_ready_to_leave_mc_receiving_r1_in_mf(self) -> None:
        fsm = _fsm_at(R2State.READY_TO_LEAVE_MC)
        out = fsm.update(_beacon(MsgID.R1_IN_MF, 0), R2Sensors())
        assert fsm.state == R2State.READY_TO_ENTER_MF
        assert out.action_hint == "enter_mf"

    def test_ready_to_enter_mf_hold_works(self) -> None:
        fsm = _fsm_at(R2State.READY_TO_ENTER_MF)
        out = fsm.update(_beacon(MsgID.HOLD, 0), R2Sensors())
        assert fsm.state == R2State.HOLD

    def test_ready_to_enter_mf_error_works(self) -> None:
        fsm = _fsm_at(R2State.READY_TO_ENTER_MF)
        out = fsm.update(_beacon(MsgID.ERROR, 0), R2Sensors())
        assert fsm.state == R2State.ERROR


# ===================================================================
# R2Sensors defaults and edge cases
# ===================================================================


class TestR2SensorsDefaults:
    """R2Sensors dataclass defaults and edge cases."""

    def test_default_sensors_all_false(self) -> None:
        s = R2Sensors()
        assert s.head_grabbed is False
        assert s.r1_tag_visible is False
        assert s.pre_insert_pose_ok is False
        assert s.insertion_motion_done is False
        assert s.head_released is False
        assert s.estop is False

    def test_sensors_can_be_modified(self) -> None:
        s = R2Sensors()
        s.head_grabbed = True
        assert s.head_grabbed is True

    def test_sensors_partial_init(self) -> None:
        s = R2Sensors(head_grabbed=True, estop=True)
        assert s.head_grabbed is True
        assert s.estop is True
        assert s.r1_tag_visible is False  # default


# ===================================================================
# R2Output dataclass
# ===================================================================


class TestR2Output:
    """R2Output frozen dataclass."""

    def test_output_fields(self) -> None:
        fsm = R2MissionFSM()
        out = fsm.output("test_hint", "test_reason")
        assert out.state == R2State.WAIT_R1
        assert out.action_hint == "test_hint"
        assert out.reason == "test_reason"

    def test_output_is_frozen(self) -> None:
        fsm = R2MissionFSM()
        out = fsm.output("hint", "reason")
        with __import__("pytest").raises(Exception):
            out.action_hint = "modified"  # type: ignore[misc]


# ===================================================================
# FSM constructor defaults
# ===================================================================


class TestFSMDefaults:
    def test_initial_state_is_wait_r1(self) -> None:
        fsm = R2MissionFSM()
        assert fsm.state == R2State.WAIT_R1

    def test_initial_seq_tracking_is_none(self) -> None:
        fsm = R2MissionFSM()
        assert fsm.last_seq is None
        assert fsm.last_msg_id is None

    def test_reset_from_initial_state_is_idempotent(self) -> None:
        fsm = R2MissionFSM()
        out1 = fsm.reset()
        out2 = fsm.reset()
        assert fsm.state == R2State.WAIT_R1
        assert out1 == out2


# ===================================================================
# Safety priority chain — ABORT / ESTOP must ALWAYS win
# ===================================================================


class TestSafetyPriorityChain:
    """Explicit audit of the safety priority chain in ``R2MissionFSM.update()``.

    Execution order (top to bottom, first match returns):

    1. **ESTOP** (line 60) — highest priority.  Does not even look at the beacon.
    2. invalid beacon (line 64) — return ``ignore``.
    3. unknown msg_id (line 67) — return ``ignore``.
    4. **HOLD / ERROR / ABORT** (line 72) — override to HOLD or ERROR.
    5. **safety gate** (line 81) — blocks HOLD/ERROR from normal transitions.
    6. normal task transitions (line 84+).

    This test class verifies that ABORT and ESTOP can never be blocked by
    the safety gate, because they are handled *before* it.
    """

    # ── HOLD + emergency messages ──────────────────────────────────

    def test_hold_plus_abort_goes_to_hold(self) -> None:
        """ABORT is handled at line 72, before the safety gate at line 81."""
        fsm = _fsm_at(R2State.HOLD)
        out = fsm.update(_beacon(MsgID.ABORT_CURRENT_TASK, 0), R2Sensors())
        assert fsm.state == R2State.HOLD
        assert out.action_hint == "hold"
        assert out.reason == "ABORT_CURRENT_TASK"

    def test_hold_plus_estop_goes_to_error(self) -> None:
        """ESTOP is handled at line 60, before everything else."""
        fsm = _fsm_at(R2State.HOLD)
        sensors = R2Sensors(estop=True)
        out = fsm.update(_beacon(MsgID.IDLE, 0), sensors)
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "stop_all"
        assert out.reason == "estop"

    def test_hold_plus_insert_allowed_rejected(self) -> None:
        """INSERT_ALLOWED is NOT handled before line 81 → blocked by safety gate."""
        fsm = _fsm_at(R2State.HOLD)
        sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        out = fsm.update(_beacon(MsgID.INSERT_ALLOWED, 0), sensors)
        assert fsm.state == R2State.HOLD  # did NOT become INSERTING
        assert out.action_hint == "hold_active"

    def test_hold_plus_weapon_locked_rejected(self) -> None:
        """WEAPON_LOCKED is NOT handled before line 81 → blocked by safety gate."""
        fsm = _fsm_at(R2State.HOLD)
        sensors = R2Sensors(insertion_motion_done=True)  # even with insertion done
        out = fsm.update(_beacon(MsgID.WEAPON_LOCKED, 0), sensors)
        assert fsm.state == R2State.HOLD
        assert out.action_hint == "hold_active"

    # ── ERROR + emergency messages ─────────────────────────────────

    def test_error_plus_abort_goes_to_hold(self) -> None:
        """ABORT from ERROR → HOLD (downgrade).  Line 72, before safety gate."""
        fsm = _fsm_at(R2State.ERROR)
        out = fsm.update(_beacon(MsgID.ABORT_CURRENT_TASK, 0), R2Sensors())
        assert fsm.state == R2State.HOLD
        assert out.action_hint == "hold"

    def test_error_plus_estop_stays_error(self) -> None:
        """ESTOP from ERROR → ERROR.  Line 60, before everything."""
        fsm = _fsm_at(R2State.ERROR)
        sensors = R2Sensors(estop=True)
        out = fsm.update(_beacon(MsgID.IDLE, 0), sensors)
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "stop_all"

    def test_error_plus_insert_allowed_rejected(self) -> None:
        """INSERT_ALLOWED from ERROR → blocked by safety gate."""
        fsm = _fsm_at(R2State.ERROR)
        sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        out = fsm.update(_beacon(MsgID.INSERT_ALLOWED, 0), sensors)
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "hold_active"

    def test_error_plus_weapon_locked_rejected(self) -> None:
        """WEAPON_LOCKED from ERROR → blocked by safety gate."""
        fsm = _fsm_at(R2State.ERROR)
        sensors = R2Sensors(insertion_motion_done=True)
        out = fsm.update(_beacon(MsgID.WEAPON_LOCKED, 0), sensors)
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "hold_active"

    # ── ESTOP always wins, regardless of everything ─────────────────

    def test_estop_wins_over_abort_message(self) -> None:
        """ESTOP (line 60) executes before ABORT message check (line 72)."""
        fsm = R2MissionFSM()
        sensors = R2Sensors(estop=True)
        out = fsm.update(_beacon(MsgID.ABORT_CURRENT_TASK, 0), sensors)
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "stop_all"
        assert out.reason == "estop"

    def test_estop_wins_with_invalid_beacon(self) -> None:
        """ESTOP must trigger even if the beacon is garbage."""
        fsm = _fsm_at(R2State.INSERTING)
        sensors = R2Sensors(estop=True)
        out = fsm.update(_invalid_beacon(), sensors)
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "stop_all"

    def test_estop_wins_with_unknown_msg(self) -> None:
        """ESTOP wins even with out-of-range msg_id."""
        fsm = _fsm_at(R2State.INSERTING)
        sensors = R2Sensors(estop=True)
        from robocon_coop_comm.protocol import DecodedBeacon as ProtoBeacon
        unknown = ProtoBeacon(msg_id=99, seq=0, valid=True, bits={})
        out = fsm.update(unknown, sensors)
        assert fsm.state == R2State.ERROR
        assert out.action_hint == "stop_all"

    def test_estop_wins_from_any_state(self) -> None:
        """ESTOP must trigger independently of current FSM state."""
        sensors = R2Sensors(estop=True)
        for state in R2State:
            fsm = _fsm_at(state)
            out = fsm.update(_beacon(MsgID.INSERT_ALLOWED, 0), sensors)
            assert fsm.state == R2State.ERROR, f"ESTOP from {state} should → ERROR"
            assert out.action_hint == "stop_all"

    # ── Safety gate is not reachable by HOLD/ERROR/ABORT messages ───

    def test_safety_gate_not_reachable_by_hold_msg(self) -> None:
        """HOLD msg returns at line 72-74, never reaches safety gate at line 81."""
        fsm = _fsm_at(R2State.HOLD)
        out = fsm.update(_beacon(MsgID.HOLD, 1), R2Sensors())
        # If safety gate had run, action_hint would be "hold_active".
        # HOLD/ERROR/ABORT handler returns "hold".
        assert out.action_hint == "hold"
        assert out.reason == "HOLD"

    def test_safety_gate_not_reachable_by_error_msg(self) -> None:
        """ERROR msg returns at line 72-74, never reaches safety gate at line 81."""
        fsm = _fsm_at(R2State.ERROR)
        out = fsm.update(_beacon(MsgID.ERROR, 1), R2Sensors())
        assert out.action_hint == "hold"
        assert out.reason == "ERROR"

    def test_safety_gate_not_reachable_by_abort_msg(self) -> None:
        """ABORT msg returns at line 72-74, never reaches safety gate at line 81."""
        fsm = _fsm_at(R2State.ERROR)
        out = fsm.update(_beacon(MsgID.ABORT_CURRENT_TASK, 0), R2Sensors())
        assert out.action_hint == "hold"
        assert out.reason == "ABORT_CURRENT_TASK"
