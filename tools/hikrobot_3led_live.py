#!/usr/bin/env python3
"""Hikrobot 3-LED live decode — thin CLI wrapper.

Opens a Hikrobot camera, lets the user click D0/D1/D2 LED positions,
and displays live decoding results.  All reusable camera and decode
logic lives in ``robocon_coop_comm.hikrobot_frame_provider``.

Usage::

    python tools/hikrobot_3led_live.py
    python tools/hikrobot_3led_live.py --threshold 100 --roi-size 20
    python tools/hikrobot_3led_live.py --log /tmp/beacon_log.csv
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import TYPE_CHECKING

import cv2

if TYPE_CHECKING:
    pass


LED_NAMES = ["D0", "D1", "D2"]


# ---------------------------------------------------------------------------
# LED ROI selector (UI helper)
# ---------------------------------------------------------------------------


class LedSelector:
    """Collect up to 3 LED ROI positions via mouse clicks."""

    def __init__(self) -> None:
        self.points: list[tuple[int, int]] = []

    def callback(self, event: int, x: int, y: int, flags: int, param: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            if len(self.points) < 3:
                name = LED_NAMES[len(self.points)]
                self.points.append((x, y))
                print(f"Set {name}=({x}, {y})")
            else:
                print("Already selected D0/D1/D2. Press r to reset.")

    @property
    def ready(self) -> bool:
        return len(self.points) >= 3


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hikrobot 3-LED live decode"
    )
    parser.add_argument(
        "--threshold", type=int, default=120, help="Brightness threshold (0-255)"
    )
    parser.add_argument(
        "--roi-size", type=int, default=24, help="ROI sampling square side length"
    )
    parser.add_argument(
        "--log", type=str, default=None,
        help="Output CSV/JSONL log file path (e.g. /tmp/beacon.csv or /tmp/beacon.jsonl)",
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
    args = parser.parse_args()

    # Lazy imports so --help works even without the package installed.
    try:
        from robocon_coop_comm.hikrobot_frame_provider import (
            HikrobotFrameProvider,
            ThreeLedRoiDecoder,
            roi_mean,
        )
        from robocon_coop_comm.frame_logger import FrameLogger
    except ImportError as exc:
        print(f"Failed to import robocon_coop_comm: {exc}", file=sys.stderr)
        print("Run: pip install -e .", file=sys.stderr)
        sys.exit(1)

    # --- optional debug logger ---
    logger: FrameLogger | None = None
    if args.log:
        logger = FrameLogger(args.log, format=args.log_format)
        print(f"Logging to {args.log} (format={args.log_format})")

    decoder = ThreeLedRoiDecoder(
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

        selector = LedSelector()
        window = "Hikrobot 3LED Live"
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(window, selector.callback)

        threshold = args.threshold

        print("Instructions:")
        print("1. Click D0 LED center")
        print("2. Click D1 LED center")
        print("3. Click D2 LED center")
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
                # Use the package decoder for proper protocol integration.
                decoded = decoder.decode(frame, selector.points)
                latency_ms = (time.perf_counter() - t_grab) * 1000.0

                # Draw ROI overlays
                bits_3: dict[str, int] = {}
                brightness: dict[str, float] = {}
                for i, (x, y) in enumerate(selector.points):
                    name = LED_NAMES[i]
                    b = roi_mean(gray, x, y, args.roi_size)
                    on = 1 if b > threshold else 0
                    bits_3[name] = on
                    brightness[name] = b

                    color = (0, 255, 0) if on else (0, 0, 255)
                    half = args.roi_size // 2
                    cv2.rectangle(
                        display,
                        (x - half, y - half),
                        (x + half, y + half),
                        color,
                        2,
                    )
                    cv2.putText(
                        display,
                        f"{name}={on} {b:.0f}",
                        (x - 40, y - half - 8),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        color,
                        2,
                    )

                # Status text
                text = (
                    f"thr={threshold} "
                    f"D2D1D0={bits_3.get('D2','?')}{bits_3.get('D1','?')}{bits_3.get('D0','?')} "
                    f"msg_id={decoded.msg_id} {decoded.msg_name} "
                    f"valid={decoded.valid} conf={decoded.confidence:.2f}"
                )
                cv2.putText(
                    display, text,
                    (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2,
                )

                # Console output
                print(
                    f"D0={bits_3.get('D0','?')}({brightness.get('D0',0):.0f}) "
                    f"D1={bits_3.get('D1','?')}({brightness.get('D1',0):.0f}) "
                    f"D2={bits_3.get('D2','?')}({brightness.get('D2',0):.0f}) "
                    f"=> msg_id={decoded.msg_id} {decoded.msg_name} "
                    f"seq={decoded.seq} valid={decoded.valid} "
                    f"conf={decoded.confidence:.2f} "
                    f"lat={latency_ms:.1f}ms",
                    end="\r",
                )

                # Log to file if requested
                if logger is not None:
                    logger.log(
                        timestamp=time.time(),
                        msg_id=decoded.msg_id,
                        seq=decoded.seq,
                        valid=decoded.valid,
                        confidence=decoded.confidence,
                        latency_ms=latency_ms,
                        extra={
                            "D0": bits_3.get("D0", -1),
                            "D1": bits_3.get("D1", -1),
                            "D2": bits_3.get("D2", -1),
                            "b_D0": f"{brightness.get('D0', 0):.1f}",
                            "b_D1": f"{brightness.get('D1', 0):.1f}",
                            "b_D2": f"{brightness.get('D2', 0):.1f}",
                        },
                    )
            else:
                # Prompt user to click next LED
                next_name = LED_NAMES[len(selector.points)]
                cv2.putText(
                    display,
                    f"Click {next_name} LED center",
                    (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (0, 255, 255),
                    2,
                )

            cv2.imshow(window, display)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break
            if key == ord("r"):
                selector.points.clear()
                decoder.reset_seq()
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
