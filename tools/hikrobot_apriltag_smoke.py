#!/usr/bin/env python3
"""Hikrobot AprilTag smoke test — verify tag36h11 detection with a real camera.

Uses HikrobotFrameProvider for camera lifecycle and ApriltagDetector for
tag detection.  Prints corner coordinates, centre, and decision margin
for every detection.

Usage::

    python tools/hikrobot_apriltag_smoke.py
    python tools/hikrobot_apriltag_smoke.py --display
    python tools/hikrobot_apriltag_smoke.py --log-jsonl /tmp/tags.jsonl
    python tools/hikrobot_apriltag_smoke.py --save-frame /tmp/frame.png
"""

from __future__ import annotations

import argparse
import json
import sys
import time


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hikrobot AprilTag smoke test"
    )
    parser.add_argument(
        "--family", type=str, default="tag36h11",
        help="Tag family (default: tag36h11)",
    )
    parser.add_argument(
        "--tag-id", type=int, default=None,
        help="Expected tag id (if set, print a warning when a different id is seen)",
    )
    parser.add_argument(
        "--display", action="store_true",
        help="Show live OpenCV window with tag overlays",
    )
    parser.add_argument(
        "--save-frame", type=str, default=None,
        help="Save the first frame with detections to this PNG path and exit",
    )
    parser.add_argument(
        "--log-jsonl", type=str, default=None,
        help="Write one JSON line per detection to this file",
    )
    parser.add_argument(
        "--no-print", action="store_true",
        help="Suppress per-frame console output",
    )
    parser.add_argument(
        "--exposure", type=float, default=10000.0,
        help="Camera exposure time in µs (default: 10000)",
    )
    parser.add_argument(
        "--gain", type=float, default=5.0,
        help="Camera analog gain (default: 5.0)",
    )
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # lazy imports — --help works without any optional deps
    # ------------------------------------------------------------------

    try:
        from robocon_coop_comm.hikrobot_frame_provider import HikrobotFrameProvider
        from robocon_coop_comm.apriltag_detector import ApriltagDetector, ApriltagNotAvailable
    except ImportError as exc:
        print(f"ERROR: cannot import robocon_coop_comm: {exc}", file=sys.stderr)
        print("Run:  pip install -e .", file=sys.stderr)
        sys.exit(1)

    try:
        detector = ApriltagDetector(families=args.family)
    except ApriltagNotAvailable as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.display or args.save_frame:
        try:
            import cv2
        except ImportError:
            print("ERROR: --display / --save-frame require opencv-python", file=sys.stderr)
            sys.exit(1)

    # ------------------------------------------------------------------
    # open camera
    # ------------------------------------------------------------------

    provider = HikrobotFrameProvider(
        exposure_time=args.exposure, gain=args.gain
    )
    try:
        provider.open()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Camera opened.  Detecting family={args.family}", end="")
    if args.tag_id is not None:
        print(f"  expecting tag_id={args.tag_id}", end="")
    print()
    print("Press Ctrl-C to stop.")
    print()

    # ------------------------------------------------------------------
    # log file
    # ------------------------------------------------------------------

    log_fh = None
    if args.log_jsonl:
        log_fh = open(args.log_jsonl, "w")

    # ------------------------------------------------------------------
    # main loop
    # ------------------------------------------------------------------

    detection_count = 0
    frame_count = 0

    try:
        while True:
            t0 = time.perf_counter()
            frame = provider.get_frame()
            if frame is None or frame.image is None:
                print("  (frame grab timeout)")
                continue

            frame_count += 1
            gray = frame.image

            detections = detector.detect(gray)
            latency_ms = (time.perf_counter() - t0) * 1000.0

            # Filter by tag-id if requested.
            if args.tag_id is not None:
                matching = [d for d in detections if d.tag_id == args.tag_id]
                if matching:
                    # Keep only the best match (highest decision margin).
                    detections = [max(matching, key=lambda d: d.decision_margin)]
                else:
                    detections = []

            # --- console output ---
            if not args.no_print or not detections:
                ts = time.time()
                tag_list = ", ".join(
                    f"id={d.tag_id} dm={d.decision_margin:.2f}" for d in detections
                ) or "(none)"
                print(
                    f"[{frame_count:5d}] "
                    f"ts={ts:.3f}  "
                    f"tags: {tag_list}  "
                    f"lat={latency_ms:.1f}ms",
                    end="\n" if detections else "\r",
                )

            for d in detections:
                detection_count += 1

                # Detailed detection output to console.
                print(f"  ┌─ tag_id={d.tag_id}  family={d.family}")
                print(f"  ├─ center=({d.center[0]:.1f}, {d.center[1]:.1f})")
                print(f"  ├─ decision_margin={d.decision_margin:.4f}")
                corners_str = ", ".join(
                    f"({cx:.1f},{cy:.1f})" for cx, cy in d.corners
                )
                print(f"  └─ corners=[{corners_str}]")

                # --- JSONL log ---
                if log_fh is not None:
                    record = {
                        "timestamp": ts,
                        "frame": frame_count,
                        "tag_id": d.tag_id,
                        "family": d.family,
                        "center": list(d.center),
                        "corners": [list(c) for c in d.corners],
                        "decision_margin": d.decision_margin,
                        "latency_ms": round(latency_ms, 3),
                    }
                    log_fh.write(json.dumps(record) + "\n")
                    log_fh.flush()

            # --- display window ---
            if args.display:
                import cv2
                import numpy as np

                disp = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

                for d in detections:
                    # Draw polygon outline.
                    pts = np.array(
                        [[int(x), int(y)] for x, y in d.corners], dtype=np.int32
                    )
                    cv2.polylines(disp, [pts], True, (0, 255, 0), 2)

                    # Corner index numbers.
                    for i, (cx, cy) in enumerate(d.corners):
                        cv2.circle(disp, (int(cx), int(cy)), 4, (0, 0, 255), -1)
                        cv2.putText(
                            disp, str(i), (int(cx) + 6, int(cy) - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2,
                        )

                    # Tag id label at centre.
                    ctr = (int(d.center[0]), int(d.center[1]))
                    cv2.putText(
                        disp, f"id={d.tag_id}", (ctr[0] - 25, ctr[1] - 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2,
                    )

                    # Decision margin.
                    cv2.putText(
                        disp, f"dm={d.decision_margin:.3f}",
                        (ctr[0] - 30, ctr[1] + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1,
                    )

                cv2.imshow("AprilTag Smoke", disp)

                # Exit on 'q' or Esc.
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break

            # --- save single frame ---
            if args.save_frame is not None and detection_count > 0:
                import cv2

                disp = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
                for d in detections:
                    import numpy as np

                    pts = np.array(
                        [[int(x), int(y)] for x, y in d.corners], dtype=np.int32
                    )
                    cv2.polylines(disp, [pts], True, (0, 255, 0), 2)
                    for i, (cx, cy) in enumerate(d.corners):
                        cv2.circle(disp, (int(cx), int(cy)), 4, (0, 0, 255), -1)
                    ctr = (int(d.center[0]), int(d.center[1]))
                    cv2.putText(
                        disp, f"id={d.tag_id}", (ctr[0] - 25, ctr[1] - 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2,
                    )
                cv2.imwrite(args.save_frame, disp)
                print(f"\nSaved detection frame to {args.save_frame}")
                break

    except KeyboardInterrupt:
        print("\nStopped.")

    finally:
        provider.close()
        if log_fh is not None:
            log_fh.close()
        if args.display:
            cv2.destroyAllWindows()

    # ------------------------------------------------------------------
    # summary
    # ------------------------------------------------------------------
    print(f"\nFrames: {frame_count}  Detections: {detection_count}")


if __name__ == "__main__":
    main()
