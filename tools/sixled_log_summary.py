#!/usr/bin/env python3
"""Summarise a 6-LED beacon log file (CSV or JSONL).

Reads the output of ``hikrobot_6led_live.py --log ...`` and prints per-LED
statistics, bitmask distribution, and confidence range.

Usage::

    python tools/sixled_log_summary.py data/sixled/logs/run.csv
    python tools/sixled_log_summary.py data/sixled/logs/run.jsonl
    python tools/sixled_log_summary.py --json data/sixled/logs/run.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

LED_NAMES = ["D0", "D1", "D2", "REF", "SEQ", "PAR"]

# Fields expected in a well-formed new-style CSV.
# Older CSVs have a shorter header and spill extra columns into row[None].
_NEW_STYLE_BITMASK_KEYS = ("bitmask", "bitmask_hex")
_NEW_STYLE_PATTERN_KEYS = ("pattern",)


# ---------------------------------------------------------------------------
# CSV reader
# ---------------------------------------------------------------------------


def _read_csv(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Row normalisation — handle old broken CSVs where extra fields end up in row[None]
# ---------------------------------------------------------------------------


def _normalise_row(row: dict) -> dict:
    """Normalise a CSV row so that six-LED fields are accessible by name.

    New-style CSV rows already have ``pattern``, ``bitmask``, ``D0``..``PAR``,
    etc. as top-level keys.

    Old-style (broken) CSV rows were written with a 6-column header and the
    six-LED data appended as extra values.  ``csv.DictReader`` puts those
    values into ``row[None]`` as a list::

        row[None] = [pattern, bitmask, D0, D1, D2, REF, SEQ, PAR,
                      D0_mean, D1_mean, D2_mean, REF_mean, SEQ_mean, PAR_mean]

    This function detects that case and lifts the values into named keys.
    """
    if None not in row:
        return row

    extra: list[str] = row[None]  # type: ignore[assignment]
    if not isinstance(extra, list):
        return row

    n = len(extra)
    # Heuristic: if we have at least 8 extra values (pattern+bitmask+6 LED bits)
    # it looks like an old broken six-LED CSV.
    normalised = dict(row)

    if n >= 1:
        normalised.setdefault("pattern", extra[0])
    if n >= 2:
        normalised.setdefault("bitmask", extra[1])
    # LED bits: positions 2..7
    for i, name in enumerate(LED_NAMES):
        if n > 2 + i:
            normalised.setdefault(name, extra[2 + i])
    # LED means: positions 8..13
    for i, name in enumerate(LED_NAMES):
        if n > 8 + i:
            mean_key = f"{name}_mean"
            normalised.setdefault(mean_key, extra[8 + i])

    return normalised


# ---------------------------------------------------------------------------
# JSONL reader
# ---------------------------------------------------------------------------


def _read_jsonl(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# auto-detect
# ---------------------------------------------------------------------------


def _auto_detect(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".csv":
        return "csv"
    if ext in (".jsonl", ".json"):
        return "jsonl"
    raise ValueError(
        f"Cannot auto-detect format for {path!r}.  Use --format csv or --format jsonl."
    )


# ---------------------------------------------------------------------------
# summary computation
# ---------------------------------------------------------------------------


def _resolve_bitmask(row: dict) -> str:
    """Return the bitmask string (hex or pattern) from a normalised row, or ''."""
    # Prefer explicit bitmask field.
    for key in _NEW_STYLE_BITMASK_KEYS:
        val = row.get(key, "")
        if val:
            return str(val)
    # Fall back to pattern field.
    for key in _NEW_STYLE_PATTERN_KEYS:
        val = row.get(key, "")
        if val:
            return str(val)
    return ""


def summarise(rows: list[dict]) -> dict:
    """Compute summary statistics from a list of log records.

    Rows are normalised via _normalise_row before processing, so both
    new-style and old-style (broken) CSVs are handled.
    """
    total = len(rows)
    if total == 0:
        return {
            "total_frames": 0,
            "valid_frames": 0,
            "invalid_frames": 0,
            "confidence": {"min": 0.0, "avg": 0.0, "max": 0.0},
            "bitmask_distribution": {},
            "led_on_ratio": {name: 0.0 for name in LED_NAMES},
        }

    valid_count = 0
    confidences: list[float] = []
    bitmask_counter: Counter = Counter()
    led_on_counts: dict[str, int] = {name: 0 for name in LED_NAMES}
    led_present_counts: dict[str, int] = {name: 0 for name in LED_NAMES}

    warned_old_style = False

    for row in rows:
        # Normalise for old-style broken CSVs.
        if None in row and not warned_old_style:
            warned_old_style = True

        normalised = _normalise_row(row)

        # valid
        valid_str = str(normalised.get("valid", "")).lower()
        is_valid = valid_str in ("true", "1", "yes")
        if is_valid:
            valid_count += 1

        # confidence
        try:
            confidences.append(float(normalised.get("confidence", 0)))
        except (ValueError, TypeError):
            pass

        # bitmask
        bitmask = _resolve_bitmask(normalised)
        if bitmask:
            bitmask_counter[bitmask] += 1

        # per-LED bits
        for name in LED_NAMES:
            val = normalised.get(name)
            if val is not None:
                try:
                    if int(val) == 1:
                        led_on_counts[name] += 1
                    led_present_counts[name] += 1
                except (ValueError, TypeError):
                    pass

    # Compute LED ON ratios.
    led_on_ratio: dict[str, float] = {}
    for name in LED_NAMES:
        n = led_present_counts[name]
        led_on_ratio[name] = round(led_on_counts[name] / n, 4) if n > 0 else 0.0

    return {
        "total_frames": total,
        "valid_frames": valid_count,
        "invalid_frames": total - valid_count,
        "confidence": {
            "min": round(min(confidences), 4) if confidences else 0.0,
            "avg": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
            "max": round(max(confidences), 4) if confidences else 0.0,
        },
        "bitmask_distribution": dict(
            bitmask_counter.most_common(20)  # top 20
        ),
        "led_on_ratio": led_on_ratio,
    }


# ---------------------------------------------------------------------------
# formatters
# ---------------------------------------------------------------------------


def _print_text(summary: dict) -> None:
    print(f"total_frames      {summary['total_frames']}")
    print(f"valid_frames      {summary['valid_frames']}")
    print(f"invalid_frames    {summary['invalid_frames']}")
    if summary["total_frames"] > 0:
        pct = summary["valid_frames"] / summary["total_frames"] * 100
        print(f"valid_ratio       {pct:.1f} %")

    c = summary["confidence"]
    print(f"confidence_min    {c['min']:.4f}")
    print(f"confidence_avg    {c['avg']:.4f}")
    print(f"confidence_max    {c['max']:.4f}")

    print("\nLED ON ratio:")
    for name in LED_NAMES:
        print(f"  {name:<6}  {summary['led_on_ratio'][name]:.2%}")

    bd = summary["bitmask_distribution"]
    if bd:
        print("\nBitmask distribution (top 20):")
        for mask, count in bd.items():
            print(f"  {mask:<10}  {count:>6}  {count/summary['total_frames']:.1%}")
    else:
        print("\nBitmask distribution: (no bitmask data in log)")


def _print_json(summary: dict) -> None:
    print(json.dumps(summary, indent=2))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarise a 6-LED beacon log (CSV or JSONL)"
    )
    parser.add_argument(
        "path", type=str, nargs="?", default=None,
        help="Path to log file (.csv or .jsonl)",
    )
    parser.add_argument(
        "--format", type=str, choices=["csv", "jsonl"],
        default=None,
        help="File format (auto-detected from extension if omitted)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output summary as JSON instead of text",
    )
    args = parser.parse_args()

    if args.path is None:
        parser.print_help()
        print("\nERROR: path to log file is required.", file=sys.stderr)
        sys.exit(1)

    fmt = args.format or _auto_detect(args.path)

    if fmt == "csv":
        rows = _read_csv(args.path)
    else:
        rows = _read_jsonl(args.path)

    if not rows:
        print(f"No records found in {args.path}", file=sys.stderr)
        sys.exit(1)

    summary = summarise(rows)

    if args.json:
        _print_json(summary)
    else:
        print(f"Source: {args.path}  ({fmt}, {len(rows)} records)\n")
        _print_text(summary)


if __name__ == "__main__":
    main()
