"""Operator command abstraction layer.

Unifies keyboard, gamepad, serial controller inputs into a single
OperatorCommand that is then fed to the R1 FSM.

Key safety guarantees:
- OperatorCommand NEVER contains msg_id.
- OperatorCommand NEVER contains LED bits.
- OperatorCommand NEVER directly controls R2.
- OperatorCommand only requests R1 state transitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class OperatorMode(Enum):
    """High-level mission phase selected by the operator."""

    IDLE = auto()
    MC_ASSEMBLY = auto()
    MF_COLLECT = auto()
    ATTACK_ZONE = auto()
    LIFT_TOP = auto()
    RETRY = auto()
    DEBUG = auto()


class OperatorRequest(Enum):
    """What the operator is asking for."""

    NONE = auto()
    START = auto()
    NEXT = auto()
    HOLD = auto()
    ABORT = auto()
    RESET = auto()
    CONFIRM = auto()
    TARGET_NEXT = auto()
    TARGET_PREV = auto()
    ARM_ENABLE = auto()
    ARM_DISABLE = auto()
    STATUS = auto()


@dataclass(frozen=True)
class OperatorCommand:
    """A single operator input event.

    This is an input REQUEST, not a control command.
    It does NOT contain msg_id, LED bits, or R2 directives.
    """

    mode: OperatorMode
    request: OperatorRequest
    target_grid: int | None = None
    arm_enabled: bool = False
    source: str = "unknown"


def validate_operator_command(cmd: OperatorCommand) -> None:
    """Validate an operator command.

    Raises:
        ValueError: on invalid target_grid or unsafe confirm.
    """
    if cmd.target_grid is not None and not 1 <= cmd.target_grid <= 9:
        raise ValueError(f"target_grid must be 1~9, got {cmd.target_grid}")

    # Dangerous modes require ARM for CONFIRM
    if cmd.request == OperatorRequest.CONFIRM:
        if cmd.mode in (
            OperatorMode.ATTACK_ZONE,
            OperatorMode.LIFT_TOP,
        ) and not cmd.arm_enabled:
            raise ValueError(
                f"CONFIRM in {cmd.mode.name} requires arm_enabled=True"
            )


# Mapping from OperatorRequest to the command strings that r1_fsm.py understands.
# r1_fsm.OperatorCommand enum values: START, NEXT, HOLD, RESET, ABORT, NONE
_R1_FSM_COMMAND_MAP: dict[OperatorRequest, str] = {
    OperatorRequest.START: "start",
    OperatorRequest.NEXT: "next",
    OperatorRequest.HOLD: "hold",
    OperatorRequest.ABORT: "abort",
    OperatorRequest.RESET: "reset",
}


def request_to_r1_command(cmd: OperatorCommand) -> str:
    """Map an OperatorCommand to the R1 FSM command string.

    Returns:
        One of "start", "next", "hold", "abort", "reset", or "none".
    """
    return _R1_FSM_COMMAND_MAP.get(cmd.request, "none")
