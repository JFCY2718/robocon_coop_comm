#!/usr/bin/env python3
"""Send the versioned four-light state frame to the Beacon STM32.

Supports two modes:

1. **Single-state mode** (backward compatible)::

    python tools/send_beacon_uart_v2.py \\
        --port /dev/ttyUSB0 --state INSERT_ALLOWED --count 20

2. **Sequence mode** — sends an ordered list of states with timed holds,
   validates ACKs, and optionally writes an expected CSV for validation
   with ``sixled_expected_observed_check.py``::

    python tools/send_beacon_uart_v2.py \\
        --port /dev/ttyUSB0 \\
        --states 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15 \\
        --hold-sec 3 --refresh-sec 0.05 --warmup-sec 1 \\
        --repeat 1 \\
        --expected-log /tmp/four_light_expected.csv

Expected CSV columns: start_ts, end_ts, state_id, value, state_name, bitmask, label.
The ``bitmask`` column uses the hex format ``"0xNN"``, compatible with
``tools/sixled_expected_observed_check.py``.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from robocon_coop_comm.beacon_uart_v2 import (  # noqa: E402
    AckStatus,
    BeaconAck,
    build_command,
    parse_ack,
)
from robocon_coop_comm.coop_protocol_v2 import (  # noqa: E402
    CoopMessage,
    encode_message,
)
from robocon_coop_comm.sixled_log import bitmask_to_hex_str  # noqa: E402


EXPECTED_CSV_FIELDNAMES = [
    "start_ts", "end_ts", "state_id", "value", "state_name", "bitmask", "label",
]


# ---------------------------------------------------------------------------
# Argument helpers
# ---------------------------------------------------------------------------


def _state(value: str) -> CoopMessage:
    """Parse a single state name or integer."""
    token = value.strip().upper()
    try:
        return CoopMessage(int(token, 0))
    except ValueError:
        try:
            return CoopMessage[token]
        except KeyError as exc:
            names = ", ".join(item.name for item in CoopMessage)
            raise argparse.ArgumentTypeError(
                f"state must be 0..15 or one of: {names}"
            ) from exc


def _states(value: str) -> list[CoopMessage]:
    """Parse a comma-separated list of state names or integers."""
    parts = [s.strip() for s in value.split(",") if s.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("--states requires at least one value")
    return [_state(s) for s in parts]


# ---------------------------------------------------------------------------
# Expected CSV
# ---------------------------------------------------------------------------


def _expected_record(state: CoopMessage, start_ts: float, end_ts: float) -> dict:
    """Build one expected CSV row for the four-light protocol."""
    state_id = int(state)
    mask = encode_message(state_id)
    return {
        "start_ts": f"{start_ts:.6f}",
        "end_ts": f"{end_ts:.6f}",
        "state_id": state_id,
        "value": state_id,
        "state_name": state.name,
        "bitmask": bitmask_to_hex_str(mask),
        "label": state.name,
    }


def write_expected_csv(path: str, expected: list[dict]) -> None:
    """Write expected CSV rows to *path*."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=EXPECTED_CSV_FIELDNAMES)
        writer.writeheader()
        for rec in expected:
            writer.writerow(rec)


def validate_ack(frame: bytes, expected_state: int, expected_counter: int) -> BeaconAck:
    """Parse an ACK and require an exact successful echo of the command."""
    ack = parse_ack(frame)
    if ack.status != AckStatus.OK:
        raise ValueError(f"ack_status_{ack.status.name.lower()}")
    if ack.state_id != int(expected_state):
        raise ValueError(
            f"ack_state_mismatch expected={int(expected_state)} actual={ack.state_id}"
        )
    expected_counter &= 0xFF
    if ack.counter != expected_counter:
        raise ValueError(
            f"ack_counter_mismatch expected={expected_counter} actual={ack.counter}"
        )
    return ack


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send four-light V2 state to Beacon STM32"
    )
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)

    # Single-state mode (backward compatible)
    parser.add_argument(
        "--state", type=_state, default=None,
        help="Single state name or number (default: IDLE)",
    )
    parser.add_argument(
        "--count", type=int, default=20,
        help="Number of frames in single-state mode (default: 20)",
    )
    parser.add_argument(
        "--period", type=float, default=0.05,
        help="Seconds between frames in single-state mode (default: 0.05)",
    )

    # Sequence mode
    parser.add_argument(
        "--states", type=_states, default=None,
        help="Comma-separated ordered state list, e.g. 0,1,2,3",
    )
    parser.add_argument(
        "--hold-sec", type=float, default=3.0,
        help="Seconds to hold each state in sequence mode (default: 3.0)",
    )
    parser.add_argument(
        "--refresh-sec", type=float, default=0.05,
        help="Seconds between refresh sends inside a hold (default: 0.05 = 50 ms)",
    )
    parser.add_argument(
        "--warmup-sec", type=float, default=1.0,
        help="Warmup seconds before first state (default: 1.0)",
    )
    parser.add_argument(
        "--repeat", type=int, default=1,
        help="Repeat the full sequence this many times (default: 1)",
    )
    parser.add_argument(
        "--expected-log", type=str, default=None,
        help="Write expected CSV to this path (sequence mode only)",
    )

    parser.add_argument("--brightness", type=int, default=255)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Validate args
    # ------------------------------------------------------------------
    if not 0 <= args.brightness <= 255:
        parser.error("--brightness must be in 0..255")

    if args.period <= 0:
        parser.error("--period must be positive")
    if args.count <= 0:
        parser.error("--count must be positive")
    if args.refresh_sec <= 0:
        parser.error("--refresh-sec must be positive")
    if args.hold_sec <= 0:
        parser.error("--hold-sec must be positive")
    if args.warmup_sec < 0:
        parser.error("--warmup-sec must be >= 0")
    if args.repeat <= 0:
        parser.error("--repeat must be positive")

    # Determine mode and state list
    if args.states is not None:
        # Sequence mode
        mode = "sequence"
        default_state = args.states[0]  # used if --state not specified separately
        state_list = args.states
    else:
        # Single-state mode
        mode = "single"
        default_state = args.state if args.state is not None else CoopMessage.IDLE
        state_list = [default_state]

    # ------------------------------------------------------------------
    # Dry-run: print frames, optionally write expected CSV, then exit
    # ------------------------------------------------------------------
    if args.dry_run:
        if mode == "single":
            frames = [
                build_command(int(default_state), counter, args.brightness)
                for counter in range(args.count)
            ]
        else:
            frames = []
            counter = 0
            for _repeat in range(args.repeat):
                for state in state_list:
                    refreshes = max(1, math.ceil(args.hold_sec / args.refresh_sec))
                    for _r in range(refreshes):
                        frames.append(
                            build_command(int(state), counter, args.brightness)
                        )
                        counter = (counter + 1) & 0xFF

        for frame in frames:
            print(frame.hex(" "))

        # When --expected-log is given in dry-run mode, write a minimal CSV
        # with placeholder timestamps so the format can be inspected.
        if args.expected_log and mode == "sequence":
            dry_expected: list[dict] = []
            fake_start = 0.0
            for _repeat in range(args.repeat):
                for state in state_list:
                    fake_end = fake_start + args.hold_sec
                    dry_expected.append(
                        _expected_record(state, fake_start, fake_end)
                    )
                    fake_start = fake_end
            write_expected_csv(args.expected_log, dry_expected)
            print(
                f"Expected log written to {args.expected_log}  "
                f"({len(dry_expected)} windows, dry-run timestamps)"
            )
        return

    # ------------------------------------------------------------------
    # Hardware mode — open serial port
    # ------------------------------------------------------------------
    try:
        import serial  # type: ignore[import-untyped]
    except ImportError as exc:
        raise SystemExit(
            "pyserial is required for hardware mode: pip install pyserial"
        ) from exc

    if not os.path.exists(args.port):
        print(f"ERROR: serial port not found: {args.port}", file=sys.stderr)
        sys.exit(1)

    try:
        port = serial.Serial(args.port, args.baud, timeout=max(0.1, args.period))
    except PermissionError:
        print(f"ERROR: permission denied for {args.port}", file=sys.stderr)
        print("  Add the user to the serial-port group, then sign in again.", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: cannot open {args.port}: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        # --------------------------------------------------------------
        # Single-state mode
        # --------------------------------------------------------------
        if mode == "single":
            state_id = int(default_state)
            for counter in range(args.count):
                frame = build_command(state_id, counter, args.brightness)
                port.write(frame)
                ack_raw = port.read(6)
                try:
                    ack = validate_ack(ack_raw, state_id, counter)
                except ValueError as exc:
                    raise SystemExit(
                        f"invalid ACK {ack_raw.hex(' ')}: {exc}"
                    ) from exc
                print(
                    f"state={ack.state_id} counter={ack.counter} "
                    f"status={ack.status.name} frame={frame.hex(' ')}"
                )
                time.sleep(args.period)
            return

        # --------------------------------------------------------------
        # Sequence mode
        # --------------------------------------------------------------
        expected: list[dict] = []
        counter = 0

        # Warmup
        if args.warmup_sec > 0:
            print(f"Warming up ({args.warmup_sec}s)...", end="", flush=True)
            time.sleep(args.warmup_sec)
            print(" done")

        for repeat_idx in range(args.repeat):
            if args.repeat > 1:
                print(f"\n--- Repeat {repeat_idx + 1}/{args.repeat} ---")

            for state_idx, state in enumerate(state_list):
                state_id = int(state)
                mask = encode_message(state_id)
                hex_str = bitmask_to_hex_str(mask)
                refreshes = max(1, math.ceil(args.hold_sec / args.refresh_sec))

                start_ts = time.time()
                for refresh_idx in range(refreshes):
                    frame = build_command(state_id, counter, args.brightness)
                    port.write(frame)
                    ack_raw = port.read(6)
                    try:
                        ack = validate_ack(ack_raw, state_id, counter)
                    except ValueError as exc:
                        raise SystemExit(
                            f"invalid ACK for state={state.name} counter={counter} "
                            f"frame={ack_raw.hex(' ')}: {exc}"
                        ) from exc

                    counter = (counter + 1) & 0xFF

                    if refresh_idx < refreshes - 1:
                        time.sleep(args.refresh_sec)

                # Wait out remaining hold time
                elapsed = time.time() - start_ts
                remaining = args.hold_sec - elapsed
                if remaining > 0:
                    time.sleep(remaining)
                actual_end = time.time()

                print(
                    f"[{repeat_idx * len(state_list) + state_idx + 1}"
                    f"/{args.repeat * len(state_list)}] "
                    f"state={state.name} value={state_id} mask={hex_str} "
                    f"refreshes={refreshes} hold={actual_end - start_ts:.3f}s"
                )

                expected.append(_expected_record(state, start_ts, actual_end))

        print(f"\nSequence complete.  {len(expected)} windows.")

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        expected = []
    finally:
        port.close()

    if args.expected_log:
        write_expected_csv(args.expected_log, expected)
        print(f"Expected log written to {args.expected_log}  ({len(expected)} windows)")


if __name__ == "__main__":
    main()
