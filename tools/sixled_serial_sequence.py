#!/usr/bin/env python3
"""Send a sequence of bitmask values to the STM32 LED board via serial.

Generates an expected CSV log with time windows so that the corresponding
Hikrobot observed log can be validated by ``sixled_expected_observed_check.py``.

Usage::

    python tools/sixled_serial_sequence.py \
        --port /dev/ttyACM0 \
        --baud 115200 \
        --values 0,63,1,2,4,8,16,32 \
        --hold-sec 5 \
        --warmup-sec 2 \
        --log data/sixled/logs/round4b_expected.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time

from robocon_coop_comm.sixled_log import (
    LED_NAMES,
    bitmask_to_hex_str,
    bitmask_to_pattern,
)


# ---------------------------------------------------------------------------
# Serial helpers (lazy pyserial import — --help must work without it)
# ---------------------------------------------------------------------------


def _open_serial(port: str, baud: int, timeout: float = 1.0):
    """Open a serial port.  Raises clear messages on common failures."""
    try:
        import serial  # type: ignore[import-untyped]
    except ImportError:
        print("ERROR: pyserial is not installed.", file=sys.stderr)
        print("  Install it with: pip install pyserial", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(port):
        print(f"ERROR: serial port not found: {port}", file=sys.stderr)
        print(f"  Check ls /dev/tty* for available ports.", file=sys.stderr)
        sys.exit(1)

    try:
        return serial.Serial(port, baudrate=baud, timeout=timeout)
    except PermissionError:
        print(f"ERROR: permission denied for {port}", file=sys.stderr)
        print(f"  Try: sudo chmod 666 {port}", file=sys.stderr)
        print(f"  Or add your user to the dialout group.", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: cannot open serial port {port}: {exc}", file=sys.stderr)
        sys.exit(1)


def _send_bitmask(ser, bitmask: int, brightness: int = 255) -> None:
    """Send a 6-byte serial frame containing *bitmask* as msg_id.

    Frame format: AA 55 msg_id seq brightness checksum
    msg_id = bitmask (0–63), seq = 0, brightness = 255.
    """
    seq = 0
    bri = max(0, min(255, brightness))
    cs = bitmask ^ seq ^ bri
    frame = bytes([0xAA, 0x55, bitmask, seq, bri, cs])
    ser.write(frame)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send a sequence of bitmask values to STM32 and generate expected log"
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
        "--warmup-sec", type=float, default=2.0,
        help="Warmup seconds before sending first value (default: 2.0)",
    )
    parser.add_argument(
        "--brightness", type=int, default=255,
        help="LED brightness 0-255 (default: 255)",
    )
    parser.add_argument(
        "--log", type=str, default=None,
        help="Write expected CSV to this path",
    )
    parser.add_argument(
        "--newline", action="store_true",
        help="Print newline after each value change for readability",
    )
    args = parser.parse_args()

    # Parse values.
    values: list[int] = []
    for s in args.values.split(","):
        s = s.strip()
        if not s:
            continue
        try:
            v = int(s)
        except ValueError:
            print(f"ERROR: invalid value '{s}' — must be integer", file=sys.stderr)
            sys.exit(1)
        if not 0 <= v <= 63:
            print(f"ERROR: value {v} out of range 0–63", file=sys.stderr)
            sys.exit(1)
        values.append(v)

    if not values:
        print("ERROR: at least one value is required", file=sys.stderr)
        sys.exit(1)

    print(f"Port:        {args.port}")
    print(f"Baud:        {args.baud}")
    print(f"Values:      {values}")
    print(f"Hold:        {args.hold_sec} s")
    print(f"Warmup:      {args.warmup_sec} s")
    if args.log:
        print(f"Log:         {args.log}")

    # Open serial.
    ser = _open_serial(args.port, args.baud)

    # Prepare expected log records.
    expected: list[dict] = []
    label_map = {
        0: "all_off", 63: "all_on",
        1: "D0", 2: "D1", 4: "D2",
        8: "REF", 16: "SEQ", 32: "PAR",
    }

    try:
        # Warmup.
        if args.warmup_sec > 0:
            print(f"\nWarming up ({args.warmup_sec}s)...", end="", flush=True)
            time.sleep(args.warmup_sec)
            print(" done")

        for i, v in enumerate(values):
            pattern = bitmask_to_pattern(v)
            hex_str = bitmask_to_hex_str(v)
            label = label_map.get(v, f"value_{v}")

            start_ts = time.time()
            _send_bitmask(ser, v, args.brightness)
            ser.flush()
            end_ts = time.time()
            print(f"[{i+1}/{len(values)}] value={v} mask={hex_str} pattern={pattern} label={label}", end="")

            # Hold.
            time.sleep(args.hold_sec)
            actual_end = time.time()

            expected.append({
                "start_ts": f"{start_ts:.6f}",
                "end_ts": f"{actual_end:.6f}",
                "value": v,
                "bitmask": hex_str,
                "pattern": pattern,
                "label": label,
            })

            if args.newline:
                print()
            else:
                print(" ✓")

        print("\nSequence complete.")

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        ser.close()

    # Write expected CSV.
    if args.log:
        expected_fns = ["start_ts", "end_ts", "value", "bitmask", "pattern", "label"]
        os.makedirs(os.path.dirname(args.log) or ".", exist_ok=True)
        with open(args.log, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=expected_fns)
            writer.writeheader()
            for rec in expected:
                writer.writerow(rec)
        print(f"\nExpected log written to {args.log}  ({len(expected)} windows)")


if __name__ == "__main__":
    main()
