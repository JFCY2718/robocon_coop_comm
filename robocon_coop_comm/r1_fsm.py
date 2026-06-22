"""R1 mission state machine.

The R1 FSM receives operator requests and local sensor snapshots, then emits an R1->R2
beacon message. The operator never controls individual LEDs directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from .protocol import MsgID


class R1State(Enum):
    WAIT_START = auto()
    PICK_ROD = auto()
    ROD_CLAMPED = auto()
    AT_ASSEMBLY_POSE = auto()
    INSERT_ALLOWED = auto()
    WEAPON_LOCKED = auto()
    R1_CLEAR_MC = auto()
    R1_IN_MF = auto()
    HOLD = auto()
    ABORT = auto()
    ERROR = auto()


class OperatorCommand(Enum):
    NONE = auto()
    START = auto()
    NEXT = auto()
    HOLD = auto()
    RESET = auto()
    ABORT = auto()
    RETRY = auto()  # recover from ABORT back to WAIT_START


@dataclass
class R1Sensors:
    """Minimal local sensors needed for the first MC/MF communication milestone."""

    rod_clamped: bool = False
    in_assembly_pose: bool = False
    rod_pose_locked: bool = False
    chassis_stopped: bool = False
    weapon_locked: bool = False
    r1_clear_mc: bool = False
    r1_in_mf: bool = False
    estop: bool = False
    local_estop: bool = False  # local emergency stop button


@dataclass(frozen=True)
class R1Output:
    state: R1State
    msg_id: MsgID
    seq: int
    reason: str


class R1MissionFSM:
    """Finite state machine for R1 cooperation events."""

    def __init__(self) -> None:
        self.state = R1State.WAIT_START
        self.msg_id = MsgID.IDLE
        self.seq = 0

    def reset(self) -> R1Output:
        self.state = R1State.WAIT_START
        self.msg_id = MsgID.IDLE
        self.seq = 0
        return self.output("reset")

    def _set_msg(self, msg_id: MsgID) -> None:
        if msg_id != self.msg_id:
            self.seq ^= 1
            self.msg_id = msg_id

    def output(self, reason: str) -> R1Output:
        return R1Output(state=self.state, msg_id=self.msg_id, seq=self.seq, reason=reason)

    def update(self, command: OperatorCommand, sensors: R1Sensors) -> R1Output:
        """Update state machine.

        Most transitions are triggered by OperatorCommand.NEXT, but guarded by sensors.
        This matches the intended remote-control model: few buttons, guarded state changes.
        """

        # ── local_estop: highest priority ─────────────────────────────
        if sensors.local_estop:
            self.state = R1State.ERROR
            self._set_msg(MsgID.ERROR)
            return self.output("local_estop")

        # ── estop from R1 sensors ─────────────────────────────────────
        if sensors.estop:
            self.state = R1State.ERROR
            self._set_msg(MsgID.ERROR)
            return self.output("estop")

        # ── RESET always available (recover from HOLD/ABORT/ERROR) ────
        if command == OperatorCommand.RESET:
            return self.reset()

        # ── RETRY: recover from ABORT back to WAIT_START ──────────────
        if command == OperatorCommand.RETRY:
            if self.state == R1State.ABORT:
                return self.reset()
            return self.output("retry_noop")

        # ── HOLD ──────────────────────────────────────────────────────
        if command == OperatorCommand.HOLD:
            self.state = R1State.HOLD
            self._set_msg(MsgID.HOLD)
            return self.output("operator_hold")

        # ── ABORT: dedicated state ────────────────────────────────────
        if command == OperatorCommand.ABORT:
            self.state = R1State.ABORT
            self._set_msg(MsgID.ABORT_CURRENT_TASK)
            return self.output("operator_abort")

        # ── HOLD / ABORT / ERROR states block normal commands ─────────
        if self.state in (R1State.HOLD, R1State.ABORT, R1State.ERROR):
            if self.state == R1State.HOLD:
                self._set_msg(MsgID.HOLD)
                return self.output("hold_requires_reset")
            if self.state == R1State.ABORT:
                self._set_msg(MsgID.ABORT_CURRENT_TASK)
                return self.output("abort_requires_retry")
            self._set_msg(MsgID.ERROR)
            return self.output("error_requires_reset")

        # ── START from WAIT_START ─────────────────────────────────────
        if command == OperatorCommand.START and self.state == R1State.WAIT_START:
            self.state = R1State.PICK_ROD
            self._set_msg(MsgID.IDLE)
            return self.output("start_pick_rod")

        if command != OperatorCommand.NEXT:
            return self.output("no_transition")

        # ── Guarded NEXT transitions ──────────────────────────────────
        if self.state == R1State.WAIT_START:
            self.state = R1State.PICK_ROD
            self._set_msg(MsgID.IDLE)
            return self.output("next_start_pick_rod")

        if self.state == R1State.PICK_ROD:
            if sensors.rod_clamped:
                self.state = R1State.ROD_CLAMPED
                self._set_msg(MsgID.R1_ROD_CLAMPED)
                return self.output("rod_clamped")
            self._set_msg(MsgID.HOLD)
            return self.output("blocked_wait_rod_clamped")

        if self.state == R1State.ROD_CLAMPED:
            if sensors.in_assembly_pose:
                self.state = R1State.AT_ASSEMBLY_POSE
                self._set_msg(MsgID.R1_AT_ASSEMBLY_POSE)
                return self.output("at_assembly_pose")
            self._set_msg(MsgID.HOLD)
            return self.output("blocked_wait_assembly_pose")

        if self.state == R1State.AT_ASSEMBLY_POSE:
            if sensors.rod_clamped and sensors.rod_pose_locked and sensors.chassis_stopped:
                self.state = R1State.INSERT_ALLOWED
                self._set_msg(MsgID.INSERT_ALLOWED)
                return self.output("insert_allowed")
            self._set_msg(MsgID.HOLD)
            return self.output("blocked_wait_pose_lock_and_stop")

        if self.state == R1State.INSERT_ALLOWED:
            if sensors.weapon_locked:
                self.state = R1State.WEAPON_LOCKED
                self._set_msg(MsgID.WEAPON_LOCKED)
                return self.output("weapon_locked")
            # Keep INSERT_ALLOWED while waiting for R2 insertion and quick connector lock.
            self._set_msg(MsgID.INSERT_ALLOWED)
            return self.output("wait_weapon_lock")

        if self.state == R1State.WEAPON_LOCKED:
            if sensors.r1_clear_mc:
                self.state = R1State.R1_CLEAR_MC
                self._set_msg(MsgID.R1_CLEAR_MC)
                return self.output("r1_clear_mc")
            self._set_msg(MsgID.HOLD)
            return self.output("blocked_wait_clear_mc")

        if self.state == R1State.R1_CLEAR_MC:
            if sensors.r1_in_mf:
                self.state = R1State.R1_IN_MF
                self._set_msg(MsgID.R1_IN_MF)
                return self.output("r1_in_mf")
            self._set_msg(MsgID.R1_CLEAR_MC)
            return self.output("wait_in_mf")

        return self.output("unhandled")
