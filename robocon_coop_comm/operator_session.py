"""Operator session: maintains mode, target grid, ARM state.

Processes keyboard input through OperatorSession.handle_key() which
returns an OperatorCommand.  The session does NOT directly operate the
R1 FSM or LEDs — it only produces OperatorCommand objects.
"""

from __future__ import annotations

from .keyboard_operator import next_mode, parse_key_to_operator_command
from .operator_command import OperatorCommand, OperatorMode, OperatorRequest


class OperatorSession:
    """Tracks the current operator state and translates key presses.

    Attributes:
        mode: current mission phase.
        target_grid: selected grid target (1~9) or None.
        arm_enabled: whether dangerous actions are armed.
    """

    def __init__(self) -> None:
        self.mode: OperatorMode = OperatorMode.IDLE
        self.target_grid: int | None = None
        self.arm_enabled: bool = False

    def handle_key(self, key: str) -> OperatorCommand:
        """Process a key press, update session state, return OperatorCommand.

        The returned OperatorCommand is a REQUEST, not a control signal.
        It does NOT contain msg_id or LED bits.
        """
        cmd = parse_key_to_operator_command(
            key, self.mode, self.arm_enabled, self.target_grid
        )

        # Apply side effects based on request
        if cmd.request == OperatorRequest.TARGET_NEXT:
            if self.target_grid is None:
                self.target_grid = 1
            else:
                self.target_grid = (self.target_grid % 9) + 1

        elif cmd.request == OperatorRequest.TARGET_PREV:
            if self.target_grid is None:
                self.target_grid = 9
            else:
                self.target_grid = ((self.target_grid - 2) % 9) + 1

        elif cmd.request == OperatorRequest.ARM_ENABLE:
            self.arm_enabled = True

        elif cmd.request in (
            OperatorRequest.ARM_DISABLE,
            OperatorRequest.HOLD,
            OperatorRequest.ABORT,
            OperatorRequest.RESET,
        ):
            self.arm_enabled = False

        elif cmd.request == OperatorRequest.STATUS:
            # Mode cycle on STATUS key
            self.mode = next_mode(self.mode)

        # Rebuild command with updated state
        return OperatorCommand(
            mode=self.mode,
            request=cmd.request,
            target_grid=self.target_grid,
            arm_enabled=self.arm_enabled,
            source=cmd.source,
        )
