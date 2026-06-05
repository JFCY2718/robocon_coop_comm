#!/usr/bin/env python3
"""Command-line tool to generate (and optionally send) an LED MCU serial frame.

Usage:
    # Print hex only (no serial port needed):
    python tools/send_led_frame.py --msg-id 4 --seq 1 --brightness 200

    # Send to a real serial port (requires pyserial):
    python tools/send_led_frame.py --msg-id 4 --seq 1 --brightness 200 --port /dev/ttyACM0
"""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate / send an LED MCU serial frame."
    )
    parser.add_argument("--msg-id", type=int, required=True, help="Message ID (0~31)")
    parser.add_argument("--seq", type=int, required=True, help="Sequence bit (0 or 1)")
    parser.add_argument(
        "--brightness", type=int, default=200, help="LED brightness (0~255, default 200)"
    )
    parser.add_argument("--port", type=str, default=None, help="Serial port (e.g. /dev/ttyACM0)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default 115200)")

    args = parser.parse_args()

    # Add project root to path so we can import the package
    import os

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from robocon_coop_comm.serial_frame import encode_frame

    try:
        frame = encode_frame(args.msg_id, args.seq, args.brightness)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    hex_str = " ".join(f"{b:02X}" for b in frame)
    print(f"Frame: {hex_str}")

    if args.port is None:
        return

    # Send to real serial port
    try:
        from robocon_coop_comm.serial_transport import PySerialTransport

        transport = PySerialTransport(args.port, baudrate=args.baud)
        try:
            written = transport.write(frame)
            print(f"Sent {written} bytes to {args.port}")
        finally:
            transport.close()
    except ImportError:
        print(
            "Error: pyserial is not installed.\n"
            "Install it with: pip install pyserial",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
