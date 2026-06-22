"""Shared six-LED log utilities.

Used by tools/sixled_log_summary.py and tools/sixled_expected_observed_check.py
so that row normalisation and bitmask helpers are defined in one place.
"""

from __future__ import annotations

import csv
from collections import Counter

LED_NAMES = ["D0", "D1", "D2", "REF", "SEQ", "PAR"]

# Bit position for each LED: D0=bit0 … PAR=bit5.
LED_BIT_MAP = {"D0": 0, "D1": 1, "D2": 2, "REF": 3, "SEQ": 4, "PAR": 5}

# Fields expected in a well-formed new-style CSV.
_NEW_STYLE_BITMASK_KEYS = ("bitmask", "bitmask_hex")
_NEW_STYLE_PATTERN_KEYS = ("pattern",)


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------


def read_csv(path: str) -> list[dict]:
    """Read a CSV log file and return rows as dicts (raw, NOT normalised)."""
    rows: list[dict] = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Row normalisation
# ---------------------------------------------------------------------------


def normalise_row(row: dict) -> dict:
    """Normalise a CSV row so that six-LED fields are accessible by name.

    New-style CSV rows already have ``pattern``, ``bitmask``, ``D0``..``PAR``,
    ``D0_mean``..``PAR_mean`` as top-level keys.

    Old-style (broken) CSV rows were written with a 6-column header and the
    six-LED data appended as extra values.  ``csv.DictReader`` puts those
    values into ``row[None]`` as a list::

        row[None] = [pattern, bitmask, D0, D1, D2, REF, SEQ, PAR,
                      D0_mean, D1_mean, D2_mean, REF_mean, SEQ_mean, PAR_mean]

    This function detects that case and lifts the values into named keys.
    Existing named keys in *row* take priority (are not overwritten).
    """
    if None not in row:
        return row

    extra: list[str] = row[None]  # type: ignore[assignment]
    if not isinstance(extra, list):
        return row

    n = len(extra)
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
# Bitmask helpers
# ---------------------------------------------------------------------------


def bits_to_bitmask(bits: dict[str, int]) -> int:
    """Convert a dict of LED name -> 0/1 into an integer bitmask.

    D0 → bit0 (LSB), PAR → bit5.
    """
    val = 0
    for name, bit in bits.items():
        if bit:
            val |= 1 << LED_BIT_MAP[name]
    return val


def bitmask_to_pattern(bitmask: int) -> str:
    """Convert an integer bitmask to a 6-character string (D0 first, PAR last).

    Example: 0x3F → \"111111\", 0x01 → \"000001\", 0x20 → \"100000\".
    """
    return "".join(str((bitmask >> LED_BIT_MAP[n]) & 1) for n in LED_NAMES)


def bitmask_to_hex_str(bitmask: int) -> str:
    """Convert an integer bitmask to a hex string like \"0x3F\"."""
    return f"0x{bitmask & 0x3F:02X}"


def parse_bitmask_str(s: str) -> int | None:
    """Parse a hex or decimal bitmask string.

    Accepts \"0x3F\", \"63\", \"0x00\", etc.
    Returns None on parse failure.
    """
    s = str(s).strip()
    if not s:
        return None
    try:
        if s.lower().startswith("0x"):
            return int(s, 16)
        return int(s)
    except (ValueError, TypeError):
        return None


def resolve_bitmask(row: dict) -> str:
    """Return the bitmask string (hex or pattern) from a normalised row, or ''."""
    for key in _NEW_STYLE_BITMASK_KEYS:
        val = row.get(key, "")
        if val:
            return str(val)
    for key in _NEW_STYLE_PATTERN_KEYS:
        val = row.get(key, "")
        if val:
            return str(val)
    return ""


# ---------------------------------------------------------------------------
# Dominant bitmask
# ---------------------------------------------------------------------------


def dominant_bitmask(
    rows: list[dict],
    min_window_frames: int = 1,
) -> tuple[str, int, float]:
    """Find the most common bitmask in a set of normalised rows.

    Args:
        rows: Normalised log rows.
        min_window_frames: Minimum number of frames required for a valid result.

    Returns:
        ``(bitmask_str, count, ratio)`` — ratio is count / len(rows).
        If there are no rows, returns ``("", 0, 0.0)``.
    """
    if not rows:
        return ("", 0, 0.0)
    counter: Counter = Counter()
    for row in rows:
        bm = resolve_bitmask(row)
        if bm:
            counter[bm] += 1
    if not counter:
        return ("", 0, 0.0)
    top = counter.most_common(1)[0]
    return (top[0], top[1], top[1] / len(rows))
