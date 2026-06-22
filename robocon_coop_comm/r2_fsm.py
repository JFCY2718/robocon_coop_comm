"""R2 simplified autonomous state machine using decoded R1 beacon events."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum, auto

from .protocol import DecodedBeacon, MsgID


class R2State(Enum):
    WAIT_R1 = auto()
    PREPARE_HEAD = auto()
    SEARCH_R1_TAG = auto()
    PRE_INSERT_READY = auto()
    INSERTING = auto()
    HEAD_RELEASED = auto()
    WAIT_R1_CLEAR_MC = auto()
    READY_TO_LEAVE_MC = auto()
    READY_TO_ENTER_MF = auto()
    HOLD = auto()
    ERROR = auto()


@dataclass
class R2Sensors:
    head_grabbed: bool = False
    r1_tag_visible: bool = False
    pre_insert_pose_ok: bool = False
    insertion_motion_done: bool = False
    head_released: bool = False
    estop: bool = False
    local_estop: bool = False  # local emergency stop (hardware button, not R1 beacon)


@dataclass(frozen=True)
class R2Output:
    state: R2State
    action_hint: str
    reason: str


# Messages that may change FSM state even when in HOLD/ERROR.
# RETRY_RESET is allowed to recover from non-ESTOP safety states.
_SAFETY_OVERRIDE_MSGS: set[MsgID] = {
    MsgID.HOLD,
    MsgID.ERROR,
    MsgID.ABORT_CURRENT_TASK,
    MsgID.RETRY_RESET,
}


class R2MissionFSM:
    """R2 uses R1 beacons as event cues, not as manual commands.

    Args:
        min_confidence: Minimum beacon confidence to accept (default 0.7).
        max_age_s: Maximum beacon age in seconds before stale rejection (default 2.0).
    """

    def __init__(
        self,
        min_confidence: float = 0.7,
        max_age_s: float = 2.0,
    ) -> None:
        self.state = R2State.WAIT_R1
        self.last_seq: int | None = None
        self.last_msg_id: int | None = None
        self.min_confidence = float(min_confidence)
        self.max_age_s = float(max_age_s)
        self._last_update_time: float | None = None

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def output(self, action_hint: str, reason: str) -> R2Output:
        return R2Output(self.state, action_hint, reason)

    def reset(self) -> R2Output:
        self.state = R2State.WAIT_R1
        self.last_seq = None
        self.last_msg_id = None
        self._last_update_time = None
        return self.output("wait", "reset")

    def _is_stale(self, beacon_timestamp: float | None) -> bool:
        """Check if a beacon timestamp is too old."""
        if beacon_timestamp is None:
            return False  # no timestamp → assume fresh
        if self.max_age_s <= 0:
            return False  # staleness check disabled
        return time.monotonic() - beacon_timestamp > self.max_age_s

    # ------------------------------------------------------------------
    # update — accepts protocol.DecodedBeacon OR BeaconEvent-like objects
    # ------------------------------------------------------------------

    def update(
        self,
        beacon: DecodedBeacon | object,
        sensors: R2Sensors,
    ) -> R2Output:
        """Update state machine.

        Accepts ``protocol.DecodedBeacon`` (backward-compatible) or any
        object with ``.valid``, ``.msg_id``, ``.seq``, and optionally
        ``.confidence`` and ``.timestamp`` attributes (e.g. ``BeaconEvent``).
        """
        # ── local_estop — highest priority ────────────────────────────
        if sensors.local_estop:
            self.state = R2State.ERROR
            self._last_update_time = time.monotonic()
            return self.output("stop_all", "local_estop")

        # ── ESTOP from R1 — second highest priority ───────────────────
        if sensors.estop:
            self.state = R2State.ERROR
            self._last_update_time = time.monotonic()
            return self.output("stop_all", "estop")

        # ── extract beacon fields with fallbacks ──────────────────────
        valid: bool = getattr(beacon, "valid", False)
        msg_id_raw: int = getattr(beacon, "msg_id", -1)
        seq: int = getattr(beacon, "seq", 0)
        confidence: float = getattr(beacon, "confidence", 1.0)
        beacon_ts: float | None = getattr(beacon, "timestamp", None)

        # ── invalid beacon ────────────────────────────────────────────
        if not valid:
            return self.output("ignore", "invalid_beacon")

        # ── unknown msg_id ────────────────────────────────────────────
        try:
            msg = MsgID(msg_id_raw)
        except ValueError:
            return self.output("ignore", "unknown_msg")

        # ── low confidence guard ──────────────────────────────────────
        if confidence < self.min_confidence:
            return self.output("ignore", "low_confidence")

        # ── stale timestamp guard ─────────────────────────────────────
        if self._is_stale(beacon_ts):
            return self.output("ignore", "stale_beacon")

        self._last_update_time = time.monotonic()

        # ── safety override messages (HOLD / ERROR / ABORT / RETRY_RESET) ──
        if msg in _SAFETY_OVERRIDE_MSGS:
            if msg == MsgID.RETRY_RESET:
                # RETRY_RESET recovers from HOLD/ERROR to WAIT_R1.
                if self.state in (R2State.HOLD, R2State.ERROR):
                    return self.reset()
                # Outside HOLD/ERROR, RETRY_RESET is a no-op.
                return self.output("wait", "retry_reset_noop")
            # HOLD / ERROR / ABORT_CURRENT_TASK
            if msg == MsgID.ERROR:
                self.state = R2State.ERROR
            else:
                self.state = R2State.HOLD
            return self.output("hold", msg.name)

        # ── safety gate: HOLD / ERROR lock out normal task messages ──
        # Only HOLD, ERROR, ABORT, RETRY_RESET, ESTOP (handled above) may
        # change state once the FSM has entered HOLD or ERROR.  Normal task
        # messages (INSERT_ALLOWED, WEAPON_LOCKED, R1_CLEAR_MC, …) must NOT
        # be able to sneak R2 out of a safety hold.
        if self.state in (R2State.HOLD, R2State.ERROR):
            return self.output("hold_active", self.state.name.lower() + "_active")

        # ── duplicate seq tracking ────────────────────────────────────
        is_new_event = (self.last_msg_id, self.last_seq) != (msg_id_raw, seq)
        self.last_msg_id = msg_id_raw
        self.last_seq = seq

        # ── normal task transitions ───────────────────────────────────
        if self.state == R2State.WAIT_R1 and msg == MsgID.R1_ROD_CLAMPED:
            self.state = R2State.PREPARE_HEAD
            return self.output("grab_head", "r1_rod_clamped")

        if self.state in (R2State.PREPARE_HEAD, R2State.SEARCH_R1_TAG):
            if sensors.head_grabbed:
                self.state = R2State.SEARCH_R1_TAG
            if msg == MsgID.R1_AT_ASSEMBLY_POSE and sensors.head_grabbed:
                self.state = R2State.SEARCH_R1_TAG
                return self.output("search_r1_tag", "r1_at_assembly_pose")

        if msg == MsgID.INSERT_ALLOWED:
            if self.state == R2State.INSERTING and not is_new_event:
                return self.output("continue_insert", "insert_already_active")
            if sensors.head_grabbed and sensors.r1_tag_visible and sensors.pre_insert_pose_ok:
                self.state = R2State.INSERTING
                return self.output("insert_head", "insert_allowed_and_local_ready")
            return self.output("wait_local_ready", "insert_allowed_but_local_not_ready")

        if msg == MsgID.WEAPON_LOCKED:
            if self.state == R2State.INSERTING or sensors.insertion_motion_done:
                self.state = R2State.HEAD_RELEASED
                return self.output("release_head_and_retreat", "weapon_locked")
            return self.output("wait_insert_complete", "weapon_locked_seen_early")

        if msg == MsgID.R1_CLEAR_MC:
            if self.state in (R2State.HEAD_RELEASED, R2State.WAIT_R1_CLEAR_MC):
                self.state = R2State.READY_TO_LEAVE_MC
                return self.output("leave_mc", "r1_clear_mc")
            return self.output("wait_head_release", "r1_clear_mc_seen_early")

        if msg == MsgID.R1_IN_MF:
            if self.state == R2State.READY_TO_LEAVE_MC:
                self.state = R2State.READY_TO_ENTER_MF
                return self.output("enter_mf", "r1_in_mf")
            return self.output("wait_clear_mc_first", "r1_in_mf_seen_early")

        return self.output("wait", "no_matching_transition")
