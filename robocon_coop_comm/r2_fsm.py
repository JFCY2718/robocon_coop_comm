"""R2 simplified autonomous state machine using decoded R1 beacon events."""

from __future__ import annotations

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


@dataclass(frozen=True)
class R2Output:
    state: R2State
    action_hint: str
    reason: str


class R2MissionFSM:
    """R2 uses R1 beacons as event cues, not as manual commands."""

    def __init__(self) -> None:
        self.state = R2State.WAIT_R1
        self.last_seq: int | None = None
        self.last_msg_id: int | None = None

    def output(self, action_hint: str, reason: str) -> R2Output:
        return R2Output(self.state, action_hint, reason)

    def reset(self) -> R2Output:
        self.state = R2State.WAIT_R1
        self.last_seq = None
        self.last_msg_id = None
        return self.output("wait", "reset")

    def update(self, beacon: DecodedBeacon, sensors: R2Sensors) -> R2Output:
        if sensors.estop:
            self.state = R2State.ERROR
            return self.output("stop_all", "estop")

        if not beacon.valid:
            return self.output("ignore", "invalid_beacon")

        try:
            msg = MsgID(beacon.msg_id)
        except ValueError:
            return self.output("ignore", "unknown_msg")

        if msg in (MsgID.HOLD, MsgID.ERROR, MsgID.ABORT_CURRENT_TASK):
            self.state = R2State.HOLD if msg != MsgID.ERROR else R2State.ERROR
            return self.output("hold", msg.name)

        # Repeated same seq+msg is allowed for holding current permission, but should not retrigger
        # one-shot actions unless the state also permits it.
        is_new_event = (self.last_msg_id, self.last_seq) != (beacon.msg_id, beacon.seq)
        self.last_msg_id = beacon.msg_id
        self.last_seq = beacon.seq

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
