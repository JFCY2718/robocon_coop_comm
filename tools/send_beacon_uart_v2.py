#!/usr/bin/env python3
"""Send the versioned four-light state frame to the Beacon STM32."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from robocon_coop_comm.beacon_uart_v2 import build_command, parse_ack  # noqa: E402
from robocon_coop_comm.coop_protocol_v2 import CoopMessage  # noqa: E402


def _state(value: str) -> CoopMessage:
    token = value.strip().upper()
    try:
        return CoopMessage(int(token, 0))
    except ValueError:
        try:
            return CoopMessage[token]
        except KeyError as exc:
            names = ", ".join(item.name for item in CoopMessage)
            raise argparse.ArgumentTypeError(f"state must be 0..15 or one of: {names}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Send four-light V2 state to Beacon STM32")
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--state", type=_state, default=CoopMessage.IDLE)
    parser.add_argument("--brightness", type=int, default=255)
    parser.add_argument("--period", type=float, default=0.05)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not 0 <= args.brightness <= 255:
        parser.error("--brightness must be in 0..255")
    if args.period <= 0 or args.count <= 0:
        parser.error("--period and --count must be positive")

    frames = [build_command(args.state, counter, args.brightness) for counter in range(args.count)]
    if args.dry_run:
        for frame in frames:
            print(frame.hex(" "))
        return

    try:
        import serial
    except ImportError as exc:
        raise SystemExit("pyserial is required for hardware mode: pip install pyserial") from exc

    with serial.Serial(args.port, args.baud, timeout=max(0.1, args.period)) as port:
        for frame in frames:
            port.write(frame)
            ack_raw = port.read(6)
            try:
                ack = parse_ack(ack_raw)
            except ValueError as exc:
                raise SystemExit(f"invalid ACK {ack_raw.hex(' ')}: {exc}") from exc
            print(
                f"state={ack.state_id} counter={ack.counter} "
                f"status={ack.status.name} frame={frame.hex(' ')}"
            )
            time.sleep(args.period)


if __name__ == "__main__":
    main()
