#!/usr/bin/env python3
"""Send a sequence of six-LED bitmask values over serial.

Generates an expected CSV log with time windows so that the corresponding
Hikrobot observed log can be validated by ``sixled_expected_observed_check.py``.

Usage::

    python tools/sixled_serial_sequence.py \
        --protocol ascii \
        --port /dev/ttyACM0 \
        --baud 115200 \
        --values 0,63,1,2,4,8,16,32 \
        --hold-sec 5 \
        --warmup-sec 2 \
        --log data/sixled/logs/round4b_expected.csv

    python tools/sixled_serial_sequence.py \
        --protocol rscontrol2 \
        --port COM3 \
        --baud 115200 \
        --values 0,63,1,2,4,8,16,32 \
        --hold-sec 5 \
        --refresh-sec 0.2 \
        --log data/sixled/logs/round4b_expected_rscontrol2.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from robocon_coop_comm.sixled_log import (
    bitmask_to_hex_str,
    bitmask_to_pattern,
)


DEFAULT_PROTOCOL = "ascii"
SUPPORTED_PROTOCOLS = ("ascii", "rscontrol2")


# ---------------------------------------------------------------------------
# Frame helpers
# ---------------------------------------------------------------------------


def build_ascii_frame(bitmask: int) -> bytes:
    """Build the STM32F103 breadboard test frame: decimal mask + newline."""
    return f"{bitmask & 0x3F}\n".encode("ascii")


def build_rscontrol2_frame(bitmask: int, seq: int) -> bytes:
    """Build the Rscontrol2 F407 0xBC beacon frame."""
    return bytes([0xBC, 0x00, bitmask & 0x3F, seq & 0xFF, 0x55])


def build_serial_frame(protocol: str, bitmask: int, seq: int) -> bytes:
    """Build one serial frame for the selected protocol."""
    if protocol == "ascii":
        return build_ascii_frame(bitmask)
    if protocol == "rscontrol2":
        return build_rscontrol2_frame(bitmask, seq)
    raise ValueError(f"unsupported protocol: {protocol}")


def next_seq(seq: int) -> int:
    """Increment an 8-bit sequence counter with wrap."""
    return (seq + 1) & 0xFF


def refresh_count(hold_sec: float, refresh_sec: float) -> int:
    """Return how many sends occur inside one hold window."""
    return max(1, math.ceil(hold_sec / refresh_sec))


def _send_bitmask(
    ser,
    bitmask: int,
    *,
    protocol: str,
    seq: int,
) -> int:
    """Send one bitmask frame and return the next sequence value."""
    frame = build_serial_frame(protocol, bitmask, seq)
    ser.write(frame)
    return next_seq(seq)


# ---------------------------------------------------------------------------
# Serial helpers (lazy pyserial import; --help must work without it)
# ---------------------------------------------------------------------------


def _is_windows_com_port(port: str) -> bool:
    """Return True for Windows serial names such as COM3 or \\\\.\\COM10."""
    name = port.strip()
    upper = name.upper()
    if upper.startswith("\\\\.\\COM"):
        return upper[7:].isdigit()
    return upper.startswith("COM") and upper[3:].isdigit()


def _open_serial(port: str, baud: int, timeout: float = 1.0):
    """Open a serial port. Raises clear messages on common failures."""
    try:
        import serial  # type: ignore[import-untyped]
    except ImportError:
        print("ERROR: pyserial is not installed.", file=sys.stderr)
        print("  Install it with: pip install pyserial", file=sys.stderr)
        sys.exit(1)

    if not _is_windows_com_port(port) and not os.path.exists(port):
        print(f"ERROR: serial port not found: {port}", file=sys.stderr)
        print("  Check ls /dev/tty* for available ports.", file=sys.stderr)
        sys.exit(1)

    try:
        return serial.Serial(port, baudrate=baud, timeout=timeout)
    except PermissionError:
        print(f"ERROR: permission denied for {port}", file=sys.stderr)
        print(f"  Try: sudo chmod 666 {port}", file=sys.stderr)
        print("  Or add your user to the dialout group.", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: cannot open serial port {port}: {exc}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Sequence runner
# ---------------------------------------------------------------------------


def _expected_record(value: int, start_ts: float, end_ts: float) -> dict:
    label_map = {
        0: "all_off",
        63: "all_on",
        1: "D0",
        2: "D1",
        4: "D2",
        8: "REF",
        16: "SEQ",
        32: "PAR",
    }
    return {
        "start_ts": f"{start_ts:.6f}",
        "end_ts": f"{end_ts:.6f}",
        "value": value,
        "bitmask": bitmask_to_hex_str(value),
        "pattern": bitmask_to_pattern(value),
        "label": label_map.get(value, f"value_{value}"),
    }


def run_sequence(
    ser,
    values: list[int],
    *,
    protocol: str,
    hold_sec: float,
    refresh_sec: float,
    warmup_sec: float,
    newline: bool,
    sleep_fn: Callable[[float], None] = time.sleep,
    time_fn: Callable[[], float] = time.time,
) -> list[dict]:
    """Send the sequence and return expected CSV records.

    Refresh sends keep the hardware state alive, but expected CSV remains one
    window per requested mask value.
    """
    expected: list[dict] = []
    seq = 0

    if warmup_sec > 0:
        print(f"\nWarming up ({warmup_sec}s)...", end="", flush=True)
        sleep_fn(warmup_sec)
        print(" done")

    for i, value in enumerate(values):
        pattern = bitmask_to_pattern(value)
        hex_str = bitmask_to_hex_str(value)
        label = _expected_record(value, 0.0, 0.0)["label"]
        send_count = refresh_count(hold_sec, refresh_sec)

        start_ts = time_fn()
        for refresh_idx in range(send_count):
            send_seq = seq
            seq = _send_bitmask(ser, value, protocol=protocol, seq=seq)
            if hasattr(ser, "flush"):
                ser.flush()
            frame = build_serial_frame(protocol, value, send_seq)
            print(
                f"[{i+1}/{len(values)}] value={value} mask={hex_str} "
                f"pattern={pattern} label={label} refresh={refresh_idx+1}/{send_count} "
                f"seq={send_seq} frame={frame.hex(' ')}",
                end="",
            )
            if newline:
                print()
            else:
                print(" ok")

            if refresh_idx < send_count - 1:
                sleep_fn(refresh_sec)

        remaining = hold_sec - (max(0, send_count - 1) * refresh_sec)
        if remaining > 0:
            sleep_fn(remaining)
        actual_end = time_fn()

        expected.append(_expected_record(value, start_ts, actual_end))

    return expected


def write_expected_csv(path: str, expected: list[dict]) -> None:
    expected_fns = ["start_ts", "end_ts", "value", "bitmask", "pattern", "label"]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=expected_fns)
        writer.writeheader()
        for rec in expected:
            writer.writerow(rec)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def _parse_values(raw: str) -> list[int]:
    values: list[int] = []
    for s in raw.split(","):
        s = s.strip()
        if not s:
            continue
        try:
            value = int(s)
        except ValueError:
            print(f"ERROR: invalid value '{s}' - must be integer", file=sys.stderr)
            sys.exit(1)
        if not 0 <= value <= 63:
            print(f"ERROR: value {value} out of range 0-63", file=sys.stderr)
            sys.exit(1)
        values.append(value)

    if not values:
        print("ERROR: at least one value is required", file=sys.stderr)
        sys.exit(1)
    return values


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send a sequence of six-LED bitmask values and generate expected log"
    )
    parser.add_argument(
        "--protocol",
        choices=SUPPORTED_PROTOCOLS,
        default=DEFAULT_PROTOCOL,
        help="Serial protocol: ascii for STM32F103 breadboard, rscontrol2 for F407 0xBC frames (default: ascii)",
    )
    parser.add_argument("--port", default="/dev/ttyACM0", help="Serial port (default: /dev/ttyACM0)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    parser.add_argument(
        "--values", type=str, default="0,63,1,2,4,8,16,32",
        help="Comma-separated bitmask values to send (default: 0,63,1,2,4,8,16,32)",
    )
    parser.add_argument(
        "--hold-sec", type=float, default=5.0,
        help="Seconds to hold each value before switching (default: 5.0)",
    )
    parser.add_argument(
        "--refresh-sec", type=float, default=0.2,
        help="Seconds between repeated sends while holding one value (default: 0.2)",
    )
    parser.add_argument(
        "--warmup-sec", type=float, default=2.0,
        help="Warmup seconds before sending first value (default: 2.0)",
    )
    parser.add_argument(
        "--brightness", type=int, default=255,
        help="Reserved for older binary LED MCU tools; ignored by ascii and rscontrol2 protocols",
    )
    parser.add_argument(
        "--log", type=str, default=None,
        help="Write expected CSV to this path",
    )
    parser.add_argument(
        "--newline", action="store_true",
        help="Print newline after each send for readability",
    )
    args = parser.parse_args()

    values = _parse_values(args.values)
    if args.refresh_sec <= 0:
        print("ERROR: --refresh-sec must be > 0", file=sys.stderr)
        sys.exit(1)

    print(f"Protocol:    {args.protocol}")
    print(f"Port:        {args.port}")
    print(f"Baud:        {args.baud}")
    print(f"Values:      {values}")
    print(f"Hold:        {args.hold_sec} s")
    print(f"Refresh:     {args.refresh_sec} s")
    print(f"Warmup:      {args.warmup_sec} s")
    if args.log:
        print(f"Log:         {args.log}")

    ser = _open_serial(args.port, args.baud)
    try:
        expected = run_sequence(
            ser,
            values,
            protocol=args.protocol,
            hold_sec=args.hold_sec,
            refresh_sec=args.refresh_sec,
            warmup_sec=args.warmup_sec,
            newline=args.newline,
        )
        print("\nSequence complete.")
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        expected = []
    finally:
        ser.close()

    if args.log:
        write_expected_csv(args.log, expected)
        print(f"\nExpected log written to {args.log}  ({len(expected)} windows)")


if __name__ == "__main__":
    main()
