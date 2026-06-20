#!/usr/bin/env python3
"""Hikrobot 6-LED live decode — thin CLI wrapper.

Opens a Hikrobot camera, lets the user click 6 LED positions (REF/D0/D1/D2/SEQ/PAR),
and displays live decoding results.  All reusable logic lives in
``robocon_coop_comm.six_led_decoder`` and ``robocon_coop_comm.pattern_mapper``.

Usage::

    python tools/hikrobot_6led_live.py
    python tools/hikrobot_6led_live.py --threshold 100 --roi-size 20
    python tools/hikrobot_6led_live.py --pattern 6led_horizontal
    python tools/hikrobot_6led_live.py --log /tmp/beacon_6led.csv
    python tools/hikrobot_6led_live.py --protocol  # show protocol-level decode
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import TYPE_CHECKING

import cv2

if TYPE_CHECKING:
    pass


LED_NAMES_6 = ["REF", "D0", "D1", "D2", "SEQ", "PAR"]


# ---------------------------------------------------------------------------
# LED ROI selector (UI helper)
# ---------------------------------------------------------------------------


class LedSelector6:
    """Collect up to 6 LED ROI positions via mouse clicks."""

    def __init__(self) -> None:
        self.points: list[tuple[int, int]] = []

    def callback(self, event: int, x: int, y: int, flags: int, param: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            if len(self.points) < 6:
                name = LED_NAMES_6[len(self.points)]
                self.points.append((x, y))
                print(f"Set {name}=({x}, {y})")
            else:
                print("Already selected all 6 LEDs. Press r to reset.")

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
        "--threshold", type=int, default=120, help="Brightness threshold (0-255)"
    )
    parser.add_argument(
        "--roi-size", type=int, default=24, help="ROI sampling square side length"
    )
    parser.add_argument(
        "--log", type=str, default=None,
        help="Output CSV/JSONL log file path (e.g. /tmp/beacon_6led.csv)",
    )
    parser.add_argument(
        "--log-format", type=str, default="csv", choices=["csv", "jsonl"],
        help="Log output format (default: csv)",
    )
    parser.add_argument(
        "--exposure", type=float, default=10000.0, help="Exposure time in µs"
    )
    parser.add_argument(
        "--gain", type=float, default=5.0, help="Analog gain"
    )
    parser.add_argument(
        "--timeout", type=int, default=1000, help="Frame grab timeout in ms"
    )
    parser.add_argument(
        "--protocol", action="store_true",
        help="Show protocol-level decoded beacon (msg_id/seq/valid) in addition to raw bits",
    )
    args = parser.parse_args()

    # Lazy imports so --help works even without the package installed.
    try:
        from robocon_coop_comm.hikrobot_frame_provider import (
            HikrobotFrameProvider,
            roi_mean,
        )
        from robocon_coop_comm.six_led_decoder import SixLedRoiDecoder
        from robocon_coop_comm.frame_logger import FrameLogger
    except ImportError as exc:
        print(f"Failed to import robocon_coop_comm: {exc}", file=sys.stderr)
        print("Run: pip install -e .", file=sys.stderr)
        sys.exit(1)

    # --- optional protocol bridge ---
    if args.protocol:
        from robocon_coop_comm.six_led_decoder import six_led_to_decoded_beacon

    # --- optional debug logger ---
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
        window = "Hikrobot 6LED Live"
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(window, selector.callback)

        threshold = args.threshold

        print("Instructions:")
        print("  Click in order: REF  D0  D1  D2  SEQ  PAR")
        print("Keys: q=quit, r=reset, +=threshold up, -=threshold down")

        while True:
            t_grab = time.perf_counter()
            frame = provider.get_frame()

            if frame is None or frame.image is None:
                print("Frame grab failed")
                continue

            gray = frame.image
            display = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

            if selector.ready:
                # Build RoiPoint-compatible list for the decoder.
                from robocon_coop_comm.apriltag_roi_mapper import RoiPoint

                half = args.roi_size // 2
                roi_points = [
                    RoiPoint(
                        name=name, x_px=x, y_px=y, radius_px=half,
                    )
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

                # --- status text ---
                bit_str = "".join(
                    str(reading.bits.get(n, "?")) for n in LED_NAMES_6
                )
                status_lines = [
                    f"thr={threshold}  bits={bit_str}",
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
                line = f"{bits_display} => mask={bit_str} conf={reading.confidence:.2f} valid={reading.valid}"
                if args.protocol:
                    proto = six_led_to_decoded_beacon(reading, source="6led_live")
                    line += f" msg_id={proto.msg_id} {proto.msg_name} seq={proto.seq}"
                print(line, end="\r")

                # --- log ---
                if logger is not None:
                    log_extra = {
                        name: reading.bits.get(name, -1)
                        for name in LED_NAMES_6
                    }
                    log_extra.update({
                        f"b_{name}": f"{reading.brightness.get(name, 0):.1f}"
                        for name in LED_NAMES_6
                    })
                    logger.log(
                        timestamp=time.time(),
                        bitmask=bit_str,
                        confidence=reading.confidence,
                        valid=reading.valid,
                        latency_ms=latency_ms,
                        extra=log_extra,
                    )
            else:
                # Prompt user to click next LED
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
                print("\nReset LED points")
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
        if logger is not None:
            logger.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
