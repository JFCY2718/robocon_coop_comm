#!/usr/bin/env python3
"""Validate observed six-LED log against an expected bitmask sequence.

Reads an expected CSV (from ``sixled_serial_sequence.py``) and an observed
CSV (from ``hikrobot_6led_live.py --log ...``), then compares dominant
observed bitmask in each time window against the expected value.

Usage::

    python tools/sixled_expected_observed_check.py \\
        --expected data/sixled/logs/round4b_expected.csv \\
        --observed data/sixled/logs/round4b_t40_e12000.csv \\
        --settle-sec 0.5 \\
        --min-dominant-ratio 0.90
"""

from __future__ import annotations

import argparse
import json
import sys

from robocon_coop_comm.sixled_log import (
    dominant_bitmask,
    normalise_row,
    parse_bitmask_str,
    read_csv,
)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _read_expected(path: str) -> list[dict]:
    """Read expected CSV, returning list of window dicts."""
    return read_csv(path)


# ---------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------


def _is_valid_window(row: dict) -> bool:
    """Return True if this expected row has valid start_ts and end_ts."""
    try:
        float(row["start_ts"])
        float(row["end_ts"])
        return True
    except (KeyError, ValueError, TypeError):
        return False


def check(
    expected_rows: list[dict],
    observed_rows: list[dict],
    settle_sec: float = 0.5,
    min_dominant_ratio: float = 0.90,
    min_valid_ratio: float = 0.50,
) -> dict:
    """Compare expected vs observed and return a result dict.

    Args:
        expected_rows: Rows from expected CSV (start_ts, end_ts, bitmask, …).
        observed_rows: Rows from observed CSV (timestamp, bitmask, …).
        settle_sec: Seconds to trim from start of each window (settling time).
        min_dominant_ratio: Minimum ratio for the dominant bitmask to be accepted.
        min_valid_ratio: Minimum ratio of frames with valid==1 per window.

    Returns:
        Dict with ``windows`` (list of per-window results) and ``overall_pass``.
    """
    # Pre-normalise observed rows.
    norm_obs = [normalise_row(r) for r in observed_rows]

    # Parse timestamps from observed rows — build a sorted list for fast window filtering.
    obs_stamps: list[float] = []
    for row in norm_obs:
        try:
            obs_stamps.append(float(row["timestamp"]))
        except (KeyError, ValueError, TypeError):
            obs_stamps.append(-1.0)

    windows: list[dict] = []
    all_pass = True

    for exp_row in expected_rows:
        if not _is_valid_window(exp_row):
            continue

        start = float(exp_row["start_ts"]) + settle_sec
        end = float(exp_row["end_ts"])  # no trim from end, but we already held for full window

        expected_bm = str(exp_row.get("bitmask", ""))
        expected_val = exp_row.get("value", "")
        label = exp_row.get("label", "")

        # Filter observed frames in this time window.
        window_frames = [
            norm_obs[i]
            for i, ts in enumerate(obs_stamps)
            if start <= ts <= end and ts >= 0
        ]

        # Count valid frames.
        valid_count = 0
        for row in window_frames:
            valid_str = str(row.get("valid", "")).lower()
            if valid_str in ("true", "1", "yes"):
                valid_count += 1

        dom_bm, dom_count, dom_ratio = dominant_bitmask(window_frames)
        valid_ratio = valid_count / len(window_frames) if window_frames else 0.0

        # Determine result.
        frame_count = len(window_frames)
        if frame_count == 0:
            result = "FAIL"
            reason = "no observed frames in window"
            all_pass = False
        elif valid_ratio < min_valid_ratio:
            result = "FAIL"
            reason = f"valid_ratio={valid_ratio:.2f} below min {min_valid_ratio:.2f}"
            all_pass = False
        elif dom_bm != expected_bm:
            result = "FAIL"
            reason = f"dominant {dom_bm} != expected {expected_bm}"
            all_pass = False
        elif dom_ratio < min_dominant_ratio:
            result = "FAIL"
            reason = f"dominant_ratio={dom_ratio:.3f} below min {min_dominant_ratio:.3f}"
            all_pass = False
        else:
            result = "PASS"
            reason = "ok"

        windows.append({
            "value": expected_val,
            "expected": expected_bm,
            "label": label,
            "dominant": dom_bm,
            "dominant_ratio": round(dom_ratio, 4),
            "dominant_count": dom_count,
            "frames": frame_count,
            "valid_ratio": round(valid_ratio, 4),
            "result": result,
            "reason": reason,
        })

    return {
        "windows": windows,
        "overall_pass": all_pass,
        "total_windows": len(windows),
        "passed_windows": sum(1 for w in windows if w["result"] == "PASS"),
        "failed_windows": sum(1 for w in windows if w["result"] != "PASS"),
    }


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------


def _print_text_report(result: dict) -> None:
    """Print a human-readable table report."""
    print("Round 4B expected-vs-observed report\n")
    header = f"{'window':<7} {'value':<6} {'expected':<8} {'dominant':<8} {'ratio':<7} {'frames':<7} {'result':<6}"
    print(header)
    print("-" * len(header))
    for i, w in enumerate(result["windows"], 1):
        print(
            f"{i:<7} {w['value']:<6} {w['expected']:<8} "
            f"{w['dominant']:<8} {w['dominant_ratio']:<7.3f} "
            f"{w['frames']:<7} {w['result']:<6}"
        )

    print(f"\noverall: {'PASS' if result['overall_pass'] else 'FAIL'}")
    print(f"  {result['passed_windows']}/{result['total_windows']} windows passed")

    # Print failed window details if any.
    failed = [w for w in result["windows"] if w["result"] != "PASS"]
    if failed:
        print("\nFailed windows:")
        for i, w in enumerate(result["windows"]):
            if w["result"] != "PASS":
                print(f"  window {i+1}: {w['expected']} — {w['reason']}")


def _print_json_report(result: dict) -> None:
    print(json.dumps(result, indent=2, default=str))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate observed six-LED log against expected bitmask sequence"
    )
    parser.add_argument(
        "--expected", type=str, required=True,
        help="Path to expected CSV (from sixled_serial_sequence.py)",
    )
    parser.add_argument(
        "--observed", type=str, required=True,
        help="Path to observed CSV (from hikrobot_6led_live.py --log ...)",
    )
    parser.add_argument(
        "--settle-sec", type=float, default=0.5,
        help="Seconds to trim from start of each window for LED settling (default: 0.5)",
    )
    parser.add_argument(
        "--min-dominant-ratio", type=float, default=0.90,
        help="Minimum dominant bitmask ratio to pass (default: 0.90)",
    )
    parser.add_argument(
        "--min-valid-ratio", type=float, default=0.50,
        help="Minimum valid frame ratio per window (default: 0.50)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output result as JSON",
    )
    args = parser.parse_args()

    # Read inputs.
    expected_rows = _read_expected(args.expected)
    if not expected_rows:
        print(f"ERROR: no windows found in {args.expected}", file=sys.stderr)
        sys.exit(1)

    try:
        observed_rows = read_csv(args.observed)
    except FileNotFoundError:
        print(f"ERROR: observed log not found: {args.observed}", file=sys.stderr)
        sys.exit(1)

    if not observed_rows:
        print(f"ERROR: no frames found in {args.observed}", file=sys.stderr)
        sys.exit(1)

    result = check(
        expected_rows=expected_rows,
        observed_rows=observed_rows,
        settle_sec=args.settle_sec,
        min_dominant_ratio=args.min_dominant_ratio,
        min_valid_ratio=args.min_valid_ratio,
    )

    if args.json:
        _print_json_report(result)
    else:
        _print_text_report(result)

    if not result["overall_pass"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
