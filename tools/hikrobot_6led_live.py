#!/usr/bin/env python3
"""Hikrobot 6-LED live decode — thin CLI wrapper.

Opens a Hikrobot camera, lets the user click 6 LED positions or load them from
a JSON ROI file, and displays live decoding results.  All reusable logic lives
in ``robocon_coop_comm.six_led_decoder`` and ``robocon_coop_comm.pattern_mapper``.

LED order (click sequence / ROI file):  D0  D1  D2  REF  SEQ  PAR

Bitmask mapping::

    D0  -> bit0 (LSB)
    D1  -> bit1
    D2  -> bit2
    REF -> bit3
    SEQ -> bit4
    PAR -> bit5 (MSB)

Usage::

    # interactive: click 6 LEDs
    python tools/hikrobot_6led_live.py

    # save ROI after calibration
    python tools/hikrobot_6led_live.py --save-roi configs/my_roi.json

    # load saved ROI (skip clicking)
    python tools/hikrobot_6led_live.py --roi-file configs/my_roi.json

    # with logging + protocol display
    python tools/hikrobot_6led_live.py --roi-file configs/my_roi.json \\
        --log data/sixled/logs/run.csv --protocol
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import cv2

LED_NAMES_6 = ["D0", "D1", "D2", "REF", "SEQ", "PAR"]

# Bit position for each LED.
LED_BIT_MAP = {"D0": 0, "D1": 1, "D2": 2, "REF": 3, "SEQ": 4, "PAR": 5}


# ---------------------------------------------------------------------------
# ROI file helpers
# ---------------------------------------------------------------------------


def _load_roi_file(path: str) -> list[tuple[int, int]]:
    """Load ROI points from a JSON file.

    Expected format::

        {
            "led_order": ["D0","D1","D2","REF","SEQ","PAR"],
            "points": {"D0":[x,y], "D1":[x,y], ...}
        }
    """
    with open(path) as fh:
        data = json.load(fh)

    led_order = data.get("led_order", LED_NAMES_6)
    points: list[tuple[int, int]] = []
    for name in led_order:
        pt = data["points"].get(name)
        if pt is None:
            raise ValueError(f"LED '{name}' not found in ROI file")
        points.append((int(pt[0]), int(pt[1])))
    return points


def _save_roi_file(path: str, points: list[tuple[int, int]], **extra) -> None:
    """Save ROI points to a JSON file."""
    data = {
        "description": extra.pop("description", "Hikrobot 6-LED ROI calibration"),
        "led_order": LED_NAMES_6,
        "bitmask_mapping": LED_BIT_MAP,
        "points": {name: list(pt) for name, pt in zip(LED_NAMES_6, points)},
    }
    data.update(extra)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
    print(f"\nROI saved to {path}")


# ---------------------------------------------------------------------------
# LED ROI selector (UI helper)
# ---------------------------------------------------------------------------


class LedSelector6:
    """Collect up to 6 LED ROI positions via mouse clicks.

    Click order: D0 → D1 → D2 → REF → SEQ → PAR.
    """

    def __init__(self) -> None:
        self.points: list[tuple[int, int]] = []

    def callback(self, event: int, x: int, y: int, flags: int, param: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            if len(self.points) < 6:
                name = LED_NAMES_6[len(self.points)]
                self.points.append((x, y))
                print(f"Set {name}=({x}, {y})  ({len(self.points)}/6)")
            else:
                print("Already selected all 6 LEDs. Press r to reset, s to save.")

    @property
    def ready(self) -> bool:
        return len(self.points) >= 6


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hikrobot 6-LED live decode"
    )
    parser.add_argument(
        "--threshold", type=int, default=120,
        help="Brightness threshold (0-255)",
    )
    parser.add_argument(
        "--roi-size", type=int, default=24,
        help="ROI sampling square side length",
    )
    parser.add_argument(
        "--roi-file", type=str, default=None,
        help="Load ROI positions from JSON file (skip interactive clicking)",
    )
    parser.add_argument(
        "--save-roi", type=str, default=None,
        help="Save ROI positions to JSON file (press 's' in window, or auto-save on quit)",
    )
    parser.add_argument(
        "--log", type=str, default=None,
        help="Output CSV/JSONL log file path",
    )
    parser.add_argument(
        "--log-format", type=str, default="csv", choices=["csv", "jsonl"],
        help="Log output format (default: csv)",
    )
    parser.add_argument(
        "--exposure", type=float, default=10000.0,
        help="Exposure time in µs",
    )
    parser.add_argument(
        "--gain", type=float, default=5.0,
        help="Analog gain",
    )
    parser.add_argument(
        "--timeout", type=int, default=1000,
        help="Frame grab timeout in ms",
    )
    parser.add_argument(
        "--protocol", action="store_true",
        help="Show protocol-level decoded beacon (msg_id/seq/valid)",
    )
    args = parser.parse_args()

    # Lazy imports so --help works without the package.
    try:
        from robocon_coop_comm.hikrobot_frame_provider import (
            HikrobotFrameProvider,
        )
        from robocon_coop_comm.six_led_decoder import SixLedRoiDecoder
        from robocon_coop_comm.frame_logger import FrameLogger
    except ImportError as exc:
        print(f"Failed to import robocon_coop_comm: {exc}", file=sys.stderr)
        print("Run: pip install -e .", file=sys.stderr)
        sys.exit(1)

    if args.protocol:
        from robocon_coop_comm.six_led_decoder import six_led_to_decoded_beacon

    # --- load ROI from file (skip clicking) ---
    preloaded_points: list[tuple[int, int]] | None = None
    if args.roi_file:
        try:
            preloaded_points = _load_roi_file(args.roi_file)
            print(f"Loaded {len(preloaded_points)} ROI points from {args.roi_file}")
            for name, pt in zip(LED_NAMES_6, preloaded_points):
                print(f"  {name}=({pt[0]}, {pt[1]})")
        except Exception as exc:
            print(f"ERROR loading ROI file: {exc}", file=sys.stderr)
            sys.exit(1)

    # --- logger ---
    logger: FrameLogger | None = None
    if args.log:
        logger = FrameLogger(args.log, format=args.log_format)
        print(f"Logging to {args.log} (format={args.log_format})")

    decoder = SixLedRoiDecoder(
        threshold=args.threshold, roi_size=args.roi_size
    )
    provider: HikrobotFrameProvider | None = None

    try:
        provider = HikrobotFrameProvider(
            exposure_time=args.exposure,
            gain=args.gain,
            timeout_ms=args.timeout,
        )
        provider.open()

        selector = LedSelector6()
        if preloaded_points is not None:
            selector.points = list(preloaded_points)

        window = "Hikrobot 6LED Live"
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(window, selector.callback)

        threshold = args.threshold

        if preloaded_points is not None:
            print("ROI preloaded.  Keys: q=quit, r=re-click, +=threshold up, -=threshold down")
        else:
            print("Click in order:  D0  D1  D2  REF  SEQ  PAR")
            print("Keys: q=quit, r=reset, s=save ROI, +=threshold up, -=threshold down")

        while True:
            t_grab = time.perf_counter()
            frame = provider.get_frame()

            if frame is None or frame.image is None:
                print("Frame grab failed")
                continue

            gray = frame.image
            display = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

            if selector.ready:
                from robocon_coop_comm.apriltag_roi_mapper import RoiPoint

                half = args.roi_size // 2
                roi_points = [
                    RoiPoint(name=name, x_px=x, y_px=y, radius_px=half)
                    for name, (x, y) in zip(LED_NAMES_6, selector.points)
                ]

                reading = decoder.decode(frame, roi_points)
                latency_ms = (time.perf_counter() - t_grab) * 1000.0

                # --- draw ROI overlays ---
                for rp in roi_points:
                    b = reading.brightness.get(rp.name, 0.0)
                    bit = reading.bits.get(rp.name, 0)
                    color = (0, 255, 0) if bit else (0, 0, 255)
                    sz = rp.radius_px
                    cv2.rectangle(
                        display,
                        (rp.x_px - sz, rp.y_px - sz),
                        (rp.x_px + sz, rp.y_px + sz),
                        color, 2,
                    )
                    cv2.putText(
                        display,
                        f"{rp.name}={bit} {b:.0f}",
                        (rp.x_px - 40, rp.y_px - sz - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2,
                    )

                # --- build bitmask in bit order ---
                bit_str = "".join(
                    str(reading.bits.get(n, "?")) for n in LED_NAMES_6
                )
                bit_val = 0
                for name in LED_NAMES_6:
                    bit_val |= (reading.bits.get(name, 0) << LED_BIT_MAP[name])

                status_lines = [
                    f"thr={threshold}  mask={bit_str}  val=0x{bit_val:02X}",
                    f"conf={reading.confidence:.3f}  valid={reading.valid}"
                    f"  lat={latency_ms:.1f}ms",
                ]

                if args.protocol:
                    proto = six_led_to_decoded_beacon(reading, source="6led_live")
                    status_lines.append(
                        f"msg_id={proto.msg_id} {proto.msg_name}  "
                        f"seq={proto.seq}  valid={proto.valid}"
                    )

                for i, line in enumerate(status_lines):
                    cv2.putText(
                        display, line,
                        (20, 35 + i * 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2,
                    )

                # --- console output ---
                bits_display = " ".join(
                    f"{n}={reading.bits.get(n,'?')}({reading.brightness.get(n,0):.0f})"
                    for n in LED_NAMES_6
                )
                line = (
                    f"{bits_display} => mask={bit_str} val=0x{bit_val:02X} "
                    f"conf={reading.confidence:.2f} valid={reading.valid}"
                )
                if args.protocol:
                    proto = six_led_to_decoded_beacon(reading, source="6led_live")
                    line += f" msg_id={proto.msg_id} {proto.msg_name} seq={proto.seq}"
                print(line, end="\r")

                # --- log ---
                if logger is not None:
                    log_extra = {
                        "bitmask": bit_str,
                        "bitmask_hex": f"0x{bit_val:02X}",
                        **{name: reading.bits.get(name, -1) for name in LED_NAMES_6},
                        **{
                            f"b_{name}": f"{reading.brightness.get(name, 0):.1f}"
                            for name in LED_NAMES_6
                        },
                    }
                    logger.log(
                        timestamp=time.time(),
                        msg_id=0,  # 6-LED vision layer doesn't decode msg_id
                        seq=0,
                        valid=reading.valid,
                        confidence=reading.confidence,
                        latency_ms=latency_ms,
                        extra=log_extra,
                    )
            else:
                next_name = LED_NAMES_6[len(selector.points)]
                cv2.putText(
                    display,
                    f"Click {next_name} LED center  ({len(selector.points)}/6)",
                    (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                    (0, 255, 255), 2,
                )

            cv2.imshow(window, display)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break
            if key == ord("r"):
                selector.points.clear()
                print("\nReset LED points — click again: D0 D1 D2 REF SEQ PAR")
            elif key == ord("s"):
                if selector.ready:
                    save_path = args.save_roi or "sixled_roi.json"
                    _save_roi_file(
                        save_path, selector.points,
                        roi_size=args.roi_size, threshold=args.threshold,
                    )
                else:
                    print(f"\nSelect all 6 LEDs before saving ({len(selector.points)}/6)")
            elif key in (ord("+"), ord("=")):
                threshold = min(255, threshold + 5)
                decoder.threshold = threshold
                print(f"\nthreshold={threshold}")
            elif key == ord("-"):
                threshold = max(0, threshold - 5)
                decoder.threshold = threshold
                print(f"\nthreshold={threshold}")

    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        if provider is not None:
            try:
                provider.close()
            except Exception:
                pass

        # Auto-save ROI on clean exit if requested and we have points.
        if args.save_roi and selector.ready and not preloaded_points:
            _save_roi_file(
                args.save_roi, selector.points,
                roi_size=args.roi_size, threshold=args.threshold,
            )

        if logger is not None:
            logger.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
