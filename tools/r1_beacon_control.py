#!/usr/bin/env python3
"""Interactive R1 Beacon serial control console.

Usage:
    # Interactive mode (real serial):
    python tools/r1_beacon_control.py --port /dev/ttyACM0

    # Interactive mode (dry-run, no serial):
    python tools/r1_beacon_control.py --dry-run

    # One-shot send:
    python tools/r1_beacon_control.py --dry-run --command insert
    python tools/r1_beacon_control.py --port /dev/ttyACM0 --command insert
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Optional

# Add project root to import path.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from robocon_coop_comm.protocol import MsgID
from robocon_coop_comm.serial_frame import encode_frame

# ---------------------------------------------------------------------------
# Command -> MsgID mapping
# ---------------------------------------------------------------------------

COMMAND_MAP: dict[str, MsgID] = {
    "idle": MsgID.IDLE,
    "hold": MsgID.HOLD,
    "rod": MsgID.R1_ROD_CLAMPED,
    "pose": MsgID.R1_AT_ASSEMBLY_POSE,
    "insert": MsgID.INSERT_ALLOWED,
    "locked": MsgID.WEAPON_LOCKED,
    "clear": MsgID.R1_CLEAR_MC,
    "mf": MsgID.R1_IN_MF,
}

# Reverse map for display
MSG_ID_TO_COMMAND: dict[int, str] = {int(v): k for k, v in COMMAND_MAP.items()}


def frame_hex(frame: bytes) -> str:
    """Format frame bytes as uppercase hex, space-separated."""
    return " ".join(f"{b:02X}" for b in frame)


def parse_ack(raw: bytes) -> Optional[tuple[int, int]]:
    """Try to parse a 3-byte ACK response: CC msg_id seq.

    Returns (msg_id, seq) or None if parsing fails.
    """
    if len(raw) >= 3 and raw[0] == 0xCC:
        return (raw[1], raw[2])
    return None


# ---------------------------------------------------------------------------
# Beacon Controller
# ---------------------------------------------------------------------------


class R1BeaconController:
    """Manages R1 beacon serial state and sends frames to the MCU.

    Args:
        port: Serial port path (e.g. /dev/ttyACM0). None for dry-run.
        baudrate: Serial baud rate.
        brightness: LED brightness 0-255.
        dry_run: If True, never open a serial port.
        timeout: Serial read timeout in seconds for ACK.
    """

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 115200,
        brightness: int = 200,
        dry_run: bool = False,
        timeout: float = 0.2,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.brightness = brightness
        self.dry_run = dry_run
        self.timeout = timeout

        self.current_msg_id: int = MsgID.IDLE
        self.current_seq: int = 0
        self._ser: object = None  # pyserial Serial instance, set lazily

    # -- serial helpers -------------------------------------------------------

    def _get_serial(self) -> object:
        """Lazily open the serial port. Cached for the lifetime of the controller."""
        if self._ser is not None:
            return self._ser
        if self.dry_run or self.port is None:
            return None
        try:
            import serial  # type: ignore[import-untyped]
        except ImportError:
            raise SystemExit(
                "pyserial is required for real serial port access.\n"
                "Install it with: pip install pyserial"
            )
        self._ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
        return self._ser

    def _close_serial(self) -> None:
        if self._ser is not None:
            self._ser.close()
            self._ser = None

    # -- send ----------------------------------------------------------------

    def send(self, msg_id: int) -> None:
        """Send a beacon frame and wait for ACK.

        Flips seq (0 ↔ 1) on every call.
        """
        self.current_msg_id = msg_id
        self.current_seq ^= 1

        name = MSG_ID_TO_COMMAND.get(msg_id, MsgID(msg_id).name)
        print(f"event={MsgID(msg_id).name}")
        print(f"msg_id={msg_id}")
        print(f"seq={self.current_seq}")

        frame = encode_frame(msg_id, self.current_seq, self.brightness)
        print(f"frame={frame_hex(frame)}")

        if self.dry_run:
            print("dry-run: not sending to serial port")
            return

        ser = self._get_serial()
        if ser is None:
            print("warning: no serial port configured")
            return

        try:
            ser.write(frame)
            ser.flush()
            time.sleep(0.05)
            raw = ser.read(3)
        except Exception as exc:
            print(f"warning: serial write/read error: {exc}")
            return

        ack = parse_ack(raw)
        if ack is not None:
            print(f"ack=CC {ack[0]:02X} {ack[1]:02X}")
        else:
            if raw:
                print(f"ack=? raw={frame_hex(raw)}")
            else:
                print("warning: no ACK received (timeout)")

    # -- status ---------------------------------------------------------------

    def status(self) -> None:
        """Print current controller status."""
        state_name = MSG_ID_TO_COMMAND.get(self.current_msg_id, MsgID(self.current_msg_id).name)
        print(f"current state:     {state_name}")
        print(f"current msg_id:    {self.current_msg_id}")
        print(f"current seq:       {self.current_seq}")
        print(f"port:              {self.port or 'none'}")
        print(f"dry_run:           {self.dry_run}")
        print(f"brightness:        {self.brightness}")


# ---------------------------------------------------------------------------
# Interactive console
# ---------------------------------------------------------------------------

HELP_TEXT = """Commands:
  idle     Send IDLE (msg_id=0)
  hold     Send HOLD (msg_id=1)
  rod      Send R1_ROD_CLAMPED (msg_id=2)
  pose     Send R1_AT_ASSEMBLY_POSE (msg_id=3)
  insert   Send INSERT_ALLOWED (msg_id=4)
  locked   Send WEAPON_LOCKED (msg_id=5)
  clear    Send R1_CLEAR_MC (msg_id=6)
  mf       Send R1_IN_MF (msg_id=7)
  status   Show current state / port / brightness
  help     Show this help
  q/quit/exit  Exit"""


def interactive_loop(ctrl: R1BeaconController) -> None:
    """Run the interactive command loop."""
    print("R1 Beacon Control Console")
    print(f"port={ctrl.port or 'none'}  dry_run={ctrl.dry_run}  brightness={ctrl.brightness}")
    print('Type "help" for commands, "q" to quit.')
    print()

    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue

        cmd = raw.lower()

        if cmd in ("q", "quit", "exit"):
            break
        if cmd == "help":
            print(HELP_TEXT)
            continue
        if cmd == "status":
            ctrl.status()
            continue

        if cmd in COMMAND_MAP:
            ctrl.send(int(COMMAND_MAP[cmd]))
        else:
            print(f"unknown command: {raw}  (type 'help' for available commands)")

    ctrl._close_serial()
    print("bye.")


# ---------------------------------------------------------------------------
# One-shot mode
# ---------------------------------------------------------------------------

def one_shot(ctrl: R1BeaconController, command: str) -> None:
    """Send a single command and exit."""
    cmd = command.lower()
    if cmd not in COMMAND_MAP:
        print(f"error: unknown command '{command}'", file=sys.stderr)
        print(
            f"available: {', '.join(sorted(COMMAND_MAP.keys()))}", file=sys.stderr
        )
        sys.exit(1)

    ctrl.send(int(COMMAND_MAP[cmd]))
    ctrl._close_serial()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="R1 Beacon serial control console."
    )
    parser.add_argument(
        "--port",
        default="/dev/ttyACM0",
        help="Serial port path (default: /dev/ttyACM0)",
    )
    parser.add_argument(
        "--baudrate", type=int, default=115200, help="Baud rate (default: 115200)"
    )
    parser.add_argument(
        "--brightness", type=int, default=200, help="LED brightness 0-255 (default: 200)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not open a serial port; print frames only.",
    )
    parser.add_argument(
        "--command",
        type=str,
        default=None,
        help="Send a single command and exit (idle/hold/rod/pose/insert/locked/clear/mf). "
        "Without --command, enter interactive mode.",
    )

    args = parser.parse_args()

    # Validate brightness early.
    if not 0 <= args.brightness <= 255:
        print("error: brightness must be 0-255", file=sys.stderr)
        sys.exit(1)

    # Determine port: if --dry-run, port may be None.
    port: Optional[str] = None if args.dry_run else args.port

    ctrl = R1BeaconController(
        port=port,
        baudrate=args.baudrate,
        brightness=args.brightness,
        dry_run=args.dry_run,
    )

    if args.command is not None:
        one_shot(ctrl, args.command)
    else:
        interactive_loop(ctrl)


if __name__ == "__main__":
    main()
