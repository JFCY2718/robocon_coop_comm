#!/usr/bin/env python3
"""Hikrobot 6-LED live decode — thin CLI wrapper.

Opens a Hikrobot camera, lets the user click 6 LED positions or load them from
a JSON ROI file, and displays live decoding results.  All reusable logic lives
in ``robocon_coop_comm.six_led_decoder`` and ``robocon_coop_comm.pattern_mapper``.

LED order (click sequence / ROI file):  D0  D1  D2  D3  REF  PAR

Bitmask mapping::

    D0  -> bit0 (LSB)
    D1  -> bit1
    D2  -> bit2
    D3  -> bit3
    REF -> bit4
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

LED_NAMES_6 = ["D0", "D1", "D2", "D3", "REF", "PAR"]

# Bit position for each LED.
LED_BIT_MAP = {"D0": 0, "D1": 1, "D2": 2, "D3": 3, "REF": 4, "PAR": 5}

# Extra columns for CSV logging — must match what we write in log_extra.
# Header: pattern, bitmask, D0..PAR (bits), D0_mean..PAR_mean (brightness).
_SIXLED_CSV_EXTRA_COLUMNS = [
    "pattern", "bitmask",
    "D0", "D1", "D2", "D3", "REF", "PAR",
    "D0_mean", "D1_mean", "D2_mean", "D3_mean", "REF_mean", "PAR_mean",
    "roi_mode", "tag_seen", "tag_id", "tag_center_x", "tag_center_y",
    "tag_decision_margin", "tag_hamming", "dynamic_roi_valid", "invalid_reason",
    "tag_tracked", "effective_threshold", "saturation_max", "uncertain_leds",
    "raw_msg_id", "gated_msg_id", "gated_valid", "gated_reason",
    "capture_age_ms", "dropped_frames",
]


def _get_cv2():
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV is required for the six-LED vision tool. "
            "Install with: pip install -e '.[vision]'"
        ) from exc
    return cv2


# ---------------------------------------------------------------------------
# ROI file helpers
# ---------------------------------------------------------------------------


def _load_roi_file(path: str) -> list[tuple[int, int]]:
    """Load ROI points from a JSON file.

    Expected format::

        {
            "led_order": ["D0","D1","D2","D3","REF","PAR"],
            "points": {"D0":[x,y], "D1":[x,y], ...}
        }
    """
    with open(path) as fh:
        data = json.load(fh)

    led_order = data.get("led_order", LED_NAMES_6)
    if list(led_order) != LED_NAMES_6:
        raise ValueError(
            f"led_order must remain {LED_NAMES_6}, got {list(led_order)}"
        )
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


def _load_led_gains(path: str | None) -> dict[str, float]:
    if path is None:
        return {}
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    gains = payload.get("led_gains", payload)
    if not isinstance(gains, dict):
        raise ValueError("LED gain file must be an object or contain a led_gains object")
    unknown = set(gains) - set(LED_NAMES_6)
    if unknown:
        raise ValueError(f"unknown LED gain names: {sorted(unknown)}")
    return {name: float(value) for name, value in gains.items()}


def _apply_competition_preset(args) -> None:
    """Apply the tested low-latency, ambient-robust defaults."""
    args.protocol = True
    args.protocol_mode = "four-light"
    args.roi_mode = "apriltag"
    args.adaptive = True
    args.background_ring = True
    args.sample_statistic = "percentile"
    args.hysteresis_fraction = 0.12
    args.max_saturation_fraction = 0.50
    args.temporal_validate = True
    args.optical_flow = True
    args.latest_frame = True
    if args.exposure == 10000.0:
        args.exposure = 5000.0
    if args.gain == 5.0:
        args.gain = 0.0
    if args.timeout == 1000:
        args.timeout = 100
    if args.tag_detection_interval == 1:
        args.tag_detection_interval = 2
    if args.apriltag_threads == 1:
        args.apriltag_threads = 2


# ---------------------------------------------------------------------------
# LED ROI selector (UI helper)
# ---------------------------------------------------------------------------


class LedSelector6:
    """Collect up to 6 LED ROI positions via mouse clicks.

    Click order: D0 → D1 → D2 → D3 → REF → PAR.
    """

    def __init__(self) -> None:
        self.points: list[tuple[int, int]] = []

    def callback(self, event: int, x: int, y: int, flags: int, param: object) -> None:
        cv2 = _get_cv2()
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
        "--competition", action="store_true",
        help="Enable the recommended AprilTag, robust decode, temporal gate and latest-frame preset",
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
    parser.add_argument(
        "--protocol-mode", choices=["four-light", "legacy"], default="four-light",
        help="Protocol bridge used by --protocol (default: four-light)",
    )
    parser.add_argument(
        "--roi-mode", choices=["fixed", "apriltag"], default="fixed",
        help="ROI source; fixed preserves the existing click/ROI-file path",
    )
    parser.add_argument("--image", help="Decode one offline image instead of opening a camera")
    parser.add_argument("--output-image", help="Write the annotated offline image")
    parser.add_argument("--tag-family", default="tag36h11")
    parser.add_argument("--apriltag-threads", type=int, default=1)
    parser.add_argument("--tag-id", type=int, default=0)
    parser.add_argument("--tag-size", type=float, default=0.150, help="Black tag edge in metres")
    parser.add_argument("--tag-min-margin", type=float, default=30.0)
    parser.add_argument("--tag-max-hamming", type=int, default=0)
    parser.add_argument("--beacon-layout", help="Beacon geometry JSON override")
    parser.add_argument("--camera-calibration", help="Validated JSON intrinsics for optional pose")
    parser.add_argument("--roi-radius-scale", type=float, default=0.65)
    parser.add_argument("--tag-lost-frames", type=int, default=5)
    parser.add_argument("--tag-detection-interval", type=int, default=1)
    parser.add_argument(
        "--optical-flow", action="store_true",
        help="Track tag corners between periodic full detections",
    )
    parser.add_argument(
        "--latest-frame", action="store_true",
        help="Use a one-frame asynchronous buffer so queued old frames are dropped",
    )
    parser.add_argument("--draw-tag", action="store_true")
    parser.add_argument("--draw-dynamic-rois", action="store_true")
    parser.add_argument(
        "--pose", action="store_true",
        help="Request pose output (requires a real --camera-calibration file)",
    )
    parser.add_argument(
        "--adaptive", action="store_true",
        help="Auto-compute brightness threshold from REF LED (distance/exposure invariant)",
    )
    parser.add_argument(
        "--ref-fraction", type=float, default=0.45,
        help="Fraction of REF brightness used as threshold in adaptive mode (default: 0.45)",
    )
    parser.add_argument(
        "--background-ring", action="store_true",
        help="Sample a background ring and use centre-minus-background contrast (ambient-light robust)",
    )
    parser.add_argument(
        "--ring-ratio", type=float, default=2.5,
        help="Background ring outer radius relative to LED ROI radius (default: 2.5)",
    )
    parser.add_argument(
        "--contrast-floor", type=float, default=15.0,
        help="Minimum centre-minus-background contrast to classify as 'on' (default: 15)",
    )
    parser.add_argument(
        "--sample-statistic", choices=["mean", "percentile"], default="mean",
        help="ROI statistic; percentile is more tolerant of small projection errors",
    )
    parser.add_argument("--centre-percentile", type=float, default=70.0)
    parser.add_argument("--background-percentile", type=float, default=50.0)
    parser.add_argument("--hysteresis-fraction", type=float, default=0.0)
    parser.add_argument("--max-saturation-fraction", type=float, default=1.0)
    parser.add_argument(
        "--led-gains", help="JSON file containing optional per-LED multiplicative gains",
    )
    parser.add_argument(
        "--temporal-validate", action="store_true",
        help="Require an M-of-N vote; motion-authorising states require consecutive frames",
    )
    parser.add_argument("--temporal-window", type=int, default=5)
    parser.add_argument("--temporal-min-matches", type=int, default=3)
    parser.add_argument("--dangerous-consecutive", type=int, default=5)
    parser.add_argument("--min-protocol-confidence", type=float, default=0.70)
    parser.add_argument("--max-signal-age", type=float, default=0.30)
    args = parser.parse_args()

    if args.competition:
        _apply_competition_preset(args)

    if args.tag_size <= 0:
        parser.error("--tag-size must be positive")
    if args.apriltag_threads < 1:
        parser.error("--apriltag-threads must be >= 1")
    if args.tag_detection_interval < 1:
        parser.error("--tag-detection-interval must be >= 1")
    if args.pose and not args.camera_calibration:
        parser.error("--pose requires --camera-calibration; example intrinsics are not accepted")
    if args.temporal_validate and not args.protocol:
        parser.error("--temporal-validate requires --protocol")
    if args.temporal_validate and args.protocol_mode != "four-light":
        parser.error("--temporal-validate currently supports --protocol-mode four-light")

    cv2 = _get_cv2()

    # Lazy imports so --help works without the package.
    try:
        from robocon_coop_comm.hikrobot_frame_provider import HikrobotFrameProvider
        from robocon_coop_comm.latest_frame_provider import LatestFrameProvider
        from robocon_coop_comm.six_led_decoder import SixLedRoiDecoder
        from robocon_coop_comm.frame_logger import FrameLogger
    except ImportError as exc:
        print(f"Failed to import robocon_coop_comm: {exc}", file=sys.stderr)
        print("Run: pip install -e .", file=sys.stderr)
        sys.exit(1)

    if args.protocol:
        from robocon_coop_comm.six_led_decoder import (
            six_led_to_coop_beacon,
            six_led_to_decoded_beacon,
        )

        protocol_decoder = (
            six_led_to_coop_beacon
            if args.protocol_mode == "four-light"
            else six_led_to_decoded_beacon
        )

    temporal_validator = None
    if args.temporal_validate:
        from robocon_coop_comm.temporal_beacon_validator import TemporalBeaconValidator

        temporal_validator = TemporalBeaconValidator(
            window_size=args.temporal_window,
            min_matches=args.temporal_min_matches,
            dangerous_consecutive=args.dangerous_consecutive,
            min_confidence=args.min_protocol_confidence,
            max_age_s=args.max_signal_age,
        )

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
        logger = FrameLogger(args.log, format=args.log_format, extra_columns=_SIXLED_CSV_EXTRA_COLUMNS)
        print(f"Logging to {args.log} (format={args.log_format})")

    try:
        led_gains = _load_led_gains(args.led_gains)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(f"cannot load --led-gains: {exc}")

    decoder = SixLedRoiDecoder(
        threshold=args.threshold,
        roi_size=args.roi_size,
        sample_shape="circle" if args.roi_mode == "apriltag" else "square",
        adaptive_threshold=args.adaptive,
        ref_fraction=args.ref_fraction,
        background_ring=args.background_ring,
        ring_ratio=args.ring_ratio,
        contrast_floor=args.contrast_floor,
        sample_statistic=args.sample_statistic,
        centre_percentile=args.centre_percentile,
        background_percentile=args.background_percentile,
        hysteresis_fraction=args.hysteresis_fraction,
        led_gains=led_gains,
        max_saturation_fraction=args.max_saturation_fraction,
    )
    dynamic_tracker = None
    if args.roi_mode == "apriltag":
        from dataclasses import replace

        from robocon_coop_comm.apriltag_detector import ApriltagDetector
        from robocon_coop_comm.beacon_geometry import BeaconGeometry
        from robocon_coop_comm.camera_calibration import CameraCalibration
        from robocon_coop_comm.dynamic_sixled import DynamicSixLedTracker

        geometry = (
            BeaconGeometry.from_json(args.beacon_layout)
            if args.beacon_layout
            else BeaconGeometry()
        )
        geometry = replace(
            geometry,
            tag_size_mm=args.tag_size * 1000.0,
            roi_radius_scale=args.roi_radius_scale,
        )
        calibration = None
        if args.camera_calibration:
            calibration = CameraCalibration.from_json(args.camera_calibration)
        dynamic_tracker = DynamicSixLedTracker(
            ApriltagDetector(families=args.tag_family, nthreads=args.apriltag_threads),
            geometry,
            decoder,
            target_tag_id=args.tag_id,
            min_decision_margin=args.tag_min_margin,
            max_hamming=args.tag_max_hamming,
            tag_lost_frames=args.tag_lost_frames,
            camera_params=(
                None if calibration is None or not args.pose else calibration.pupil_camera_params
            ),
            detection_interval=args.tag_detection_interval,
            track_between_detections=args.optical_flow,
        )
    provider = None
    selector = LedSelector6()   # safe to create outside try — no SDK needed
    if preloaded_points is not None:
        selector.points = list(preloaded_points)

    if args.image:
        from robocon_coop_comm.apriltag_roi_mapper import RoiPoint
        from robocon_coop_comm.beacon_types import BeaconFrame

        image = cv2.imread(args.image, cv2.IMREAD_GRAYSCALE)
        if image is None:
            print(f"ERROR: cannot read image: {args.image}", file=sys.stderr)
            sys.exit(2)
        frame = BeaconFrame(image=image, source=f"image:{args.image}", frame_id=0)
        if args.roi_mode == "apriltag":
            result = dynamic_tracker.process(frame)
            reading = result.reading
            roi_points = list(result.rois)
            invalid_reason = result.invalid_reason
            tag = result.tag
        else:
            if not selector.ready:
                parser.error("fixed --image mode requires --roi-file with six points")
            half = args.roi_size // 2
            roi_points = [
                RoiPoint(name=name, x_px=x, y_px=y, radius_px=half)
                for name, (x, y) in zip(LED_NAMES_6, selector.points)
            ]
            reading = decoder.decode(frame, roi_points)
            invalid_reason = "" if reading.valid else "sixled_reading_invalid"
            tag = None

        bit_val = sum(
            reading.bits.get(name, 0) << LED_BIT_MAP[name] for name in LED_NAMES_6
        )
        print(json.dumps({
            "roi_mode": args.roi_mode,
            "bitmask": f"0x{bit_val:02X}",
            "bits": [reading.bits.get(name, 0) for name in LED_NAMES_6],
            "confidence": reading.confidence,
            "valid": reading.valid,
            "invalid_reason": invalid_reason,
            "tag_id": None if tag is None else tag.tag_id,
            "tag_center_px": None if tag is None else tag.center,
            "pose_R": None if tag is None or tag.pose_R is None else tag.pose_R.tolist(),
            "pose_t": None if tag is None or tag.pose_t is None else tag.pose_t.tolist(),
            "dynamic_rois": [
                [roi.name, roi.x_px, roi.y_px, roi.radius_px] for roi in roi_points
            ],
            "protocol": (
                None
                if not args.protocol
                else protocol_decoder(reading, source="6led_offline").__dict__
            ),
        }, ensure_ascii=False))
        if args.output_image:
            display = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            for roi in roi_points:
                cv2.circle(display, (roi.x_px, roi.y_px), roi.radius_px, (0, 255, 0), 2)
                cv2.putText(display, roi.name, (roi.x_px, roi.y_px - roi.radius_px - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
            cv2.imwrite(args.output_image, display)
        return

    try:
        camera_provider = HikrobotFrameProvider(
            exposure_time=args.exposure,
            gain=args.gain,
            timeout_ms=args.timeout,
        )
        provider = (
            LatestFrameProvider(camera_provider, wait_timeout_s=max(0.1, args.timeout / 1000.0 * 2))
            if args.latest_frame
            else camera_provider
        )
        provider.open()

        window = "Hikrobot 6LED Live"
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(window, selector.callback)

        threshold = args.threshold

        if preloaded_points is not None:
            print("ROI preloaded.  Keys: q=quit, r=re-click, +=threshold up, -=threshold down")
        elif args.roi_mode == "apriltag":
            print("AprilTag auto-ROI mode — no clicking needed.")
            if args.adaptive:
                print(f"  Adaptive threshold: REF brightness × {args.ref_fraction}")
            if args.background_ring:
                print("  Background-ring subtraction: centre − ring (ambient robust)")
            print("Keys: q=quit, +=threshold up, -=threshold down")
        else:
            print("Click in order:  D0  D1  D2  D3  REF  PAR")
            print("Keys: q=quit, r=reset, s=save ROI, +=threshold up, -=threshold down")

        while True:
            t_grab = time.perf_counter()
            frame = provider.get_frame()

            if frame is None or frame.image is None:
                print("Frame grab failed")
                continue

            gray = frame.image
            capture_age_ms = (
                0.0
                if frame.timestamp is None
                else max(0.0, (time.monotonic() - frame.timestamp) * 1000.0)
            )
            display = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

            dynamic_result = None
            if args.roi_mode == "apriltag":
                dynamic_result = dynamic_tracker.process(frame)
                roi_points = list(dynamic_result.rois)
                reading = dynamic_result.reading
                ready_to_display = True
            elif selector.ready:
                from robocon_coop_comm.apriltag_roi_mapper import RoiPoint

                half = args.roi_size // 2
                roi_points = [
                    RoiPoint(name=name, x_px=x, y_px=y, radius_px=half)
                    for name, (x, y) in zip(LED_NAMES_6, selector.points)
                ]

                reading = decoder.decode(frame, roi_points)
                ready_to_display = True
            else:
                ready_to_display = False

            if ready_to_display:
                latency_ms = (time.perf_counter() - t_grab) * 1000.0
                raw_proto = None
                gated_proto = None
                if args.protocol:
                    raw_proto = protocol_decoder(reading, source="6led_live")
                    gated_proto = (
                        raw_proto
                        if temporal_validator is None
                        else temporal_validator.update(
                            raw_proto,
                            timestamp=frame.timestamp,
                        )
                    )

                # --- draw ROI overlays ---
                for rp in roi_points:
                    if args.roi_mode == "apriltag" and not args.draw_dynamic_rois:
                        continue
                    b = reading.brightness.get(rp.name, 0.0)
                    bit = reading.bits.get(rp.name, 0)
                    color = (0, 255, 0) if bit else (0, 0, 255)
                    sz = rp.radius_px
                    if args.roi_mode == "apriltag":
                        cv2.circle(display, (rp.x_px, rp.y_px), sz, color, 2)
                    else:
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
                    f"thr={threshold}" + (f"→{decoder.effective_threshold:.0f}" if args.adaptive else "") +
                    f"  {'contrast' if args.background_ring else 'raw'}  "
                    f"mask={bit_str}  val=0x{bit_val:02X}",
                    f"conf={reading.confidence:.3f}  valid={reading.valid}"
                    f"  lat={latency_ms:.1f}ms age={capture_age_ms:.1f}ms",
                ]
                if dynamic_result is not None:
                    status_lines.append(
                        f"tag={dynamic_result.tag.tag_id if dynamic_result.tag else '-'} "
                        f"lost={dynamic_result.lost_frames} reason={dynamic_result.invalid_reason or '-'}"
                    )

                if args.draw_tag and dynamic_result is not None and dynamic_result.tag is not None:
                    corners = [tuple(map(int, point)) for point in dynamic_result.tag.corners]
                    for start, end in zip(corners, corners[1:] + corners[:1]):
                        cv2.line(display, start, end, (255, 255, 0), 2)

                if args.protocol:
                    status_lines.append(
                        f"raw={raw_proto.msg_id}:{raw_proto.msg_name} "
                        f"raw_valid={raw_proto.valid} gated={gated_proto.valid}"
                    )
                    status_lines.append(
                        f"gate={gated_proto.reason or '-'} conf={gated_proto.confidence:.2f}"
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
                    line += (
                        f" msg_id={raw_proto.msg_id} {raw_proto.msg_name}"
                        f" gated={gated_proto.valid} reason={gated_proto.reason or '-'}"
                    )
                print(line, end="\r")

                # --- log ---
                if logger is not None:
                    log_extra = {
                        "pattern": bit_str,
                        "bitmask": f"0x{bit_val:02X}",
                        **{name: reading.bits.get(name, -1) for name in LED_NAMES_6},
                        **{
                            f"{name}_mean": f"{reading.brightness.get(name, 0):.1f}"
                            for name in LED_NAMES_6
                        },
                        "roi_mode": args.roi_mode,
                        "tag_seen": bool(dynamic_result and dynamic_result.tag),
                        "tag_id": "" if not dynamic_result or not dynamic_result.tag else dynamic_result.tag.tag_id,
                        "tag_center_x": "" if not dynamic_result or not dynamic_result.tag else dynamic_result.tag.center[0],
                        "tag_center_y": "" if not dynamic_result or not dynamic_result.tag else dynamic_result.tag.center[1],
                        "tag_decision_margin": "" if not dynamic_result or not dynamic_result.tag else dynamic_result.tag.decision_margin,
                        "tag_hamming": "" if not dynamic_result or not dynamic_result.tag else dynamic_result.tag.hamming,
                        "dynamic_roi_valid": "" if dynamic_result is None else dynamic_result.valid,
                        "invalid_reason": "" if dynamic_result is None else dynamic_result.invalid_reason,
                        "tag_tracked": bool(
                            dynamic_result
                            and dynamic_result.tag
                            and dynamic_result.tag.extra.get("tracked", False)
                        ),
                        "effective_threshold": decoder.effective_threshold,
                        "saturation_max": max(
                            reading.extra.get("saturation_fraction", {}).values(),
                            default=0.0,
                        ),
                        "uncertain_leds": ",".join(reading.extra.get("uncertain_leds", ())),
                        "raw_msg_id": "" if raw_proto is None else raw_proto.msg_id,
                        "gated_msg_id": "" if gated_proto is None else gated_proto.msg_id,
                        "gated_valid": "" if gated_proto is None else gated_proto.valid,
                        "gated_reason": "" if gated_proto is None else gated_proto.reason,
                        "capture_age_ms": f"{capture_age_ms:.2f}",
                        "dropped_frames": getattr(provider, "dropped_frames", 0),
                    }
                    logger.log(
                        timestamp=time.time(),
                        msg_id=0 if gated_proto is None else gated_proto.msg_id,
                        seq=0 if gated_proto is None else gated_proto.seq,
                        valid=reading.valid if gated_proto is None else gated_proto.valid,
                        confidence=(
                            reading.confidence
                            if gated_proto is None
                            else gated_proto.confidence
                        ),
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
                print("\nReset LED points — click again: D0 D1 D2 D3 REF PAR")
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

    except RuntimeError as exc:
        print(f"\nERROR: Cannot open Hikrobot camera.\n{exc}", file=sys.stderr)
        print("\nHikrobot MVS SDK environment variables required:", file=sys.stderr)
        print("  export MVCAM_COMMON_RUNENV=/opt/MVS/lib", file=sys.stderr)
        print("  export PYTHONPATH=/opt/MVS/Samples/64/Python/MvImport:$PYTHONPATH", file=sys.stderr)
        print("  export LD_LIBRARY_PATH=/opt/MVS/lib/64:/opt/MVS/bin:$LD_LIBRARY_PATH", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        if provider is not None:
            try:
                provider.close()
            except Exception:
                pass

        # Auto-save ROI on clean exit if requested and we have points.
        if args.save_roi and selector is not None and selector.ready and not preloaded_points:
            _save_roi_file(
                args.save_roi, selector.points,
                roi_size=args.roi_size, threshold=args.threshold,
            )

        if logger is not None:
            logger.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
