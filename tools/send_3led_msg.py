#!/usr/bin/env python3
import argparse
import time
from typing import Optional


MSG_NAMES = {
    0: "IDLE",
    1: "HOLD",
    2: "R1_ROD_CLAMPED",
    3: "R1_AT_ASSEMBLY_POSE",
    4: "INSERT_ALLOWED",
    5: "WEAPON_LOCKED",
    6: "R1_CLEAR_MC",
    7: "R1_IN_MF",
}


def make_frame(msg_id: int, seq: int, brightness: int) -> bytes:
    msg_id &= 0xFF
    seq &= 0xFF
    brightness &= 0xFF
    checksum = msg_id ^ seq ^ brightness
    return bytes([0xAA, 0x55, msg_id, seq, brightness, checksum])


def frame_hex(frame: bytes) -> str:
    return " ".join(f"{b:02X}" for b in frame)


def get_msg_name(msg_id: int) -> str:
    return MSG_NAMES.get(msg_id, "UNKNOWN")


def send_one(
    port: str,
    baudrate: int,
    msg_id: int,
    seq: int,
    brightness: int,
    dry_run: bool,
) -> None:
    frame = make_frame(msg_id, seq, brightness)
    name = get_msg_name(msg_id)

    print(f"msg_id={msg_id} {name}")
    print(f"seq={seq}")
    print(f"brightness={brightness}")
    print(f"frame={frame_hex(frame)}")

    if dry_run:
        print("dry-run: not sending to serial port")
        return

    try:
        import serial
    except ImportError:
        raise SystemExit("Missing pyserial. Run: pip install pyserial")

    with serial.Serial(port, baudrate, timeout=0.2) as ser:
        ser.write(frame)
        ser.flush()

        time.sleep(0.05)
        ack = ser.read(3)

    if ack:
        print(f"ack={frame_hex(ack)}")
    else:
        print("ack=none")


def send_loop(
    port: str,
    baudrate: int,
    brightness: int,
    delay_s: float,
    dry_run: bool,
) -> None:
    test_ids = [0, 1, 2, 4, 7]
    seq = 0

    if dry_run:
        while True:
            for msg_id in test_ids:
                frame = make_frame(msg_id, seq, brightness)
                print(
                    f"msg_id={msg_id} {get_msg_name(msg_id)} "
                    f"seq={seq} frame={frame_hex(frame)}"
                )
                seq ^= 1
                time.sleep(delay_s)

    try:
        import serial
    except ImportError:
        raise SystemExit("Missing pyserial. Run: pip install pyserial")

    with serial.Serial(port, baudrate, timeout=0.2) as ser:
        while True:
            for msg_id in test_ids:
                frame = make_frame(msg_id, seq, brightness)
                ser.write(frame)
                ser.flush()

                print(
                    f"sent msg_id={msg_id} {get_msg_name(msg_id)} "
                    f"seq={seq} frame={frame_hex(frame)}"
                )

                ack = ser.read(3)
                if ack:
                    print(f"ack={frame_hex(ack)}")

                seq ^= 1
                time.sleep(delay_s)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send 3LED mini-beacon msg_id frame to STM32 USART1."
    )
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--msg-id", type=int, default=None)
    parser.add_argument("--seq", type=int, default=1)
    parser.add_argument("--brightness", type=int, default=200)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.loop:
        send_loop(
            port=args.port,
            baudrate=args.baudrate,
            brightness=args.brightness,
            delay_s=args.delay,
            dry_run=args.dry_run,
        )
        return

    if args.msg_id is None:
        raise SystemExit("Use --msg-id 0..7, or use --loop")

    if not (0 <= args.msg_id <= 255):
        raise SystemExit("--msg-id must be 0..255")

    if not (0 <= args.seq <= 255):
        raise SystemExit("--seq must be 0..255")

    if not (0 <= args.brightness <= 255):
        raise SystemExit("--brightness must be 0..255")

    send_one(
        port=args.port,
        baudrate=args.baudrate,
        msg_id=args.msg_id,
        seq=args.seq,
        brightness=args.brightness,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
