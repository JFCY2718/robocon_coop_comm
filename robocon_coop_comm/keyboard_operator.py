"""Keyboard input parser for operator commands.

Maps single keystrokes to OperatorCommand objects.
This is ONLY the input request layer — it does NOT generate msg_id,
LED bits, or direct R2 control.
"""

from __future__ import annotations

from .operator_command import (
    OperatorCommand,
    OperatorMode,
    OperatorRequest,
)

# Key -> OperatorRequest mapping
_KEY_MAP: dict[str, OperatorRequest] = {
    "s": OperatorRequest.START,
    "n": OperatorRequest.NEXT,
    "h": OperatorRequest.HOLD,
    "a": OperatorRequest.ABORT,
    "r": OperatorRequest.RESET,
    "c": OperatorRequest.CONFIRM,
    "]": OperatorRequest.TARGET_NEXT,
    "[": OperatorRequest.TARGET_PREV,
    "e": OperatorRequest.ARM_ENABLE,
    "d": OperatorRequest.ARM_DISABLE,
    "?": OperatorRequest.STATUS,
}

_MODE_CYCLE: list[OperatorMode] = [
    OperatorMode.IDLE,
    OperatorMode.MC_ASSEMBLY,
    OperatorMode.MF_COLLECT,
    OperatorMode.ATTACK_ZONE,
    OperatorMode.LIFT_TOP,
    OperatorMode.RETRY,
    OperatorMode.DEBUG,
]


def parse_key_to_operator_command(
    key: str,
    current_mode: OperatorMode,
    arm_enabled: bool,
    target_grid: int | None,
) -> OperatorCommand:
    """Parse a single key press into an OperatorCommand.

    Args:
        key: single character from keyboard.
        current_mode: the current operator mode.
        arm_enabled: whether ARM is currently enabled.
        target_grid: current target grid (1~9) or None.

    Returns:
        OperatorCommand with the parsed request.
        Unknown keys return OperatorRequest.NONE.
    """
    request = _KEY_MAP.get(key, OperatorRequest.NONE)
    return OperatorCommand(
        mode=current_mode,
        request=request,
        target_grid=target_grid,
        arm_enabled=arm_enabled,
        source="keyboard",
    )


def next_mode(current: OperatorMode) -> OperatorMode:
    """Cycle to the next operator mode."""
    idx = _MODE_CYCLE.index(current)
    return _MODE_CYCLE[(idx + 1) % len(_MODE_CYCLE)]
