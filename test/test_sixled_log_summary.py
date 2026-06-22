"""Tests for sixled_log_summary — log analysis tool.

Covers:
- CSV parsing (new-style with full header)
- JSONL parsing
- Old broken CSV compatibility (row[None] handling)
- Empty log
- Summary statistics correctness
- LED ON ratio calculation
- Bitmask distribution (all-on, all-off, mixed)
- CLI --help
- CLI with synthetic log files (integration)
- Header/data column count must match (no row[None] in new logs)
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tools.sixled_log_summary import (
    LED_NAMES,
    _auto_detect,
    _normalise_row,
    _read_csv,
    _read_jsonl,
    summarise,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# New-style six-LED CSV columns (matches _SIXLED_CSV_EXTRA_COLUMNS in hikrobot_6led_live.py).
_NEW_CSV_FIELDNAMES = [
    "timestamp", "msg_id", "seq", "valid", "confidence", "latency_ms",
    "pattern", "bitmask",
    "D0", "D1", "D2", "REF", "SEQ", "PAR",
    "D0_mean", "D1_mean", "D2_mean", "REF_mean", "SEQ_mean", "PAR_mean",
]


def _make_csv(rows: list[dict], fieldnames: list[str] | None = None) -> str:
    """Write rows to a temp CSV file and return the path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    )
    if not rows:
        tmp.close()
        return tmp.name

    fn = fieldnames if fieldnames is not None else list(rows[0].keys())
    writer = csv.DictWriter(tmp, fieldnames=fn)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    tmp.close()
    return tmp.name


def _make_jsonl(rows: list[dict]) -> str:
    """Write rows to a temp JSONL file and return the path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False,
    )
    for r in rows:
        tmp.write(json.dumps(r) + "\n")
    tmp.close()
    return tmp.name


def _new_style_row(
    *,
    pattern: str = "111111",
    bitmask: str = "0x3F",
    bits: dict[str, int] | None = None,
    means: dict[str, float] | None = None,
    valid: str = "1",
    confidence: str = "0.95",
) -> dict:
    """Build a single new-style CSV row with all six-LED columns."""
    if bits is None:
        bits = {n: 1 for n in LED_NAMES}
    if means is None:
        means = {n: 200.0 for n in LED_NAMES}
    return {
        "timestamp": "1720000000.123456",
        "msg_id": "0",
        "seq": "0",
        "valid": valid,
        "confidence": confidence,
        "latency_ms": "5.0",
        "pattern": pattern,
        "bitmask": bitmask,
        **{n: str(bits[n]) for n in LED_NAMES},
        **{f"{n}_mean": str(means[n]) for n in LED_NAMES},
    }


def _old_broken_csv_content(num_rows: int = 10) -> str:
    """Build a complete old-style (broken) CSV as a string.

    Old CSV: 6-column header, 20-column rows.
    DictReader puts the 14 extra values into row[None].
    """
    from io import StringIO

    buf = StringIO()
    writer = csv.writer(buf)
    # old 6-column header
    writer.writerow(["timestamp", "msg_id", "seq", "valid", "confidence", "latency_ms"])
    for i in range(num_rows):
        all_on = (i % 2 == 0)
        bits = [1 if all_on else 0 for _ in range(6)]
        means = [200.0 if all_on else 10.0 for _ in range(6)]
        row = [
            f"{1720000000 + i}.123456",  # timestamp
            "0",                          # msg_id
            "0",                          # seq
            "1" if all_on else "0",       # valid
            f"{0.8 + i * 0.01:.4f}",     # confidence
            f"{10.0 + i * 0.5:.3f}",     # latency_ms
            # --- extra values that end up in row[None] ---
            "111111" if all_on else "000000",           # pattern
            f"0x{0x3F if all_on else 0x00:02X}",        # bitmask
                            # D0..PAR bits
            str(bits[0]), str(bits[1]), str(bits[2]),
            str(bits[3]), str(bits[4]), str(bits[5]),
                            # D0_mean..PAR_mean
            f"{means[0]:.1f}", f"{means[1]:.1f}", f"{means[2]:.1f}",
            f"{means[3]:.1f}", f"{means[4]:.1f}", f"{means[5]:.1f}",
        ]
        writer.writerow(row)
    return buf.getvalue()


def _sample_rows_new(n: int = 10) -> list[dict]:
    """Generate synthetic new-style six-LED log records."""
    rows = []
    for i in range(n):
        all_on = (i % 2 == 0)
        rows.append(_new_style_row(
            pattern="111111" if all_on else "000000",
            bitmask=f"0x{0x3F if all_on else 0x00:02X}",
            bits={name: (1 if all_on else 0) for name in LED_NAMES},
            means={name: (200.0 if all_on else 10.0) for name in LED_NAMES},
            valid="1" if all_on else "0",
            confidence=f"{0.8 + i * 0.01:.4f}",
        ))
    return rows


# Alias for backward compatibility with original test naming.
_sample_rows = _sample_rows_new


# ---------------------------------------------------------------------------
# Auto-detect
# ---------------------------------------------------------------------------


class TestAutoDetect:
    def test_csv_extension(self) -> None:
        assert _auto_detect("log.csv") == "csv"

    def test_jsonl_extension(self) -> None:
        assert _auto_detect("log.jsonl") == "jsonl"

    def test_json_extension(self) -> None:
        assert _auto_detect("log.json") == "jsonl"

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="auto-detect"):
            _auto_detect("log.txt")


# ---------------------------------------------------------------------------
# CSV / JSONL parsing
# ---------------------------------------------------------------------------


class TestParsing:
    def test_read_csv(self) -> None:
        rows = _sample_rows(5)
        path = _make_csv(rows, fieldnames=_NEW_CSV_FIELDNAMES)
        try:
            parsed = _read_csv(path)
            assert len(parsed) == 5
            assert "bitmask" in parsed[0]
        finally:
            Path(path).unlink(missing_ok=True)

    def test_read_jsonl(self) -> None:
        rows = _sample_rows(3)
        path = _make_jsonl(rows)
        try:
            parsed = _read_jsonl(path)
            assert len(parsed) == 3
        finally:
            Path(path).unlink(missing_ok=True)

    def test_read_empty_csv(self) -> None:
        path = _make_csv([])
        try:
            parsed = _read_csv(path)
            assert parsed == []
        finally:
            Path(path).unlink(missing_ok=True)

    def test_read_empty_jsonl(self) -> None:
        rows: list[dict] = []
        path = _make_jsonl(rows)
        try:
            parsed = _read_jsonl(path)
            assert parsed == []
        finally:
            Path(path).unlink(missing_ok=True)

    def test_new_csv_no_row_none(self) -> None:
        """New-style CSV must NOT produce row[None]."""
        rows = _sample_rows(5)
        path = _make_csv(rows, fieldnames=_NEW_CSV_FIELDNAMES)
        try:
            parsed = _read_csv(path)
            for row in parsed:
                assert None not in row, f"row[None]={row.get(None)}"
        finally:
            Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Old broken CSV compatibility
# ---------------------------------------------------------------------------


class TestOldBrokenCsv:
    """Old CSVs where extra fields spill into row[None] must still work."""

    def test_old_csv_has_row_none(self) -> None:
        """Simulate old broken CSV: 6-col header, 20-col rows."""
        content = _old_broken_csv_content(5)
        import io
        reader = csv.DictReader(io.StringIO(content))
        first = next(reader)
        assert None in first, "old broken CSV must have row[None]"
        assert isinstance(first[None], list)
        assert len(first[None]) >= 8

    def test_normalise_lifts_pattern(self) -> None:
        row = {None: ["111111", "0x3F", "1", "1", "1", "1", "1", "1",
                        "50.0", "52.0", "72.0", "78.0", "41.0", "60.0"]}
        norm = _normalise_row(row)
        assert norm.get("pattern") == "111111"
        assert norm.get("bitmask") == "0x3F"

    def test_normalise_lifts_led_bits(self) -> None:
        row = {None: ["000000", "0x00", "0", "0", "0", "0", "0", "0",
                        "10.0", "10.0", "10.0", "10.0", "10.0", "10.0"]}
        norm = _normalise_row(row)
        for name in LED_NAMES:
            assert norm.get(name) == "0", f"{name} should be 0"

    def test_normalise_lifts_means(self) -> None:
        row = {None: ["111111", "0x3F", "1", "1", "1", "1", "1", "1",
                        "50.0", "52.0", "72.0", "78.0", "41.0", "60.0"]}
        norm = _normalise_row(row)
        assert norm.get("D0_mean") == "50.0"
        assert norm.get("D1_mean") == "52.0"
        assert norm.get("PAR_mean") == "60.0"

    def test_normalise_does_not_overwrite_existing(self) -> None:
        """If row already has named keys, they take priority over row[None]."""
        row = {
            "pattern": "existing_pattern",
            None: ["000000", "0x00", "1", "1", "1", "1", "1", "1",
                    "10.0", "10.0", "10.0", "10.0", "10.0", "10.0"],
        }
        norm = _normalise_row(row)
        assert norm["pattern"] == "existing_pattern"  # not overwritten

    def test_normalise_no_none_is_noop(self) -> None:
        row = {"pattern": "111111", "D0": "1"}
        norm = _normalise_row(row)
        assert norm is row  # same object, no copy needed

    def test_old_csv_summary_all_on(self) -> None:
        """Old broken CSV with all-on frames → LED ON ratio ~100%."""
        content = _old_broken_csv_content(20)  # 10 all-on, 10 all-off
        import io, tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            rows = _read_csv(tmp_path)
            summary = summarise(rows)
            assert summary["total_frames"] == 20
            # 10 all-on → 50%
            for name in LED_NAMES:
                assert summary["led_on_ratio"][name] == pytest.approx(0.5)
            assert "0x3F" in summary["bitmask_distribution"]
            assert "0x00" in summary["bitmask_distribution"]
        finally:
            Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# summarise — new-style CSV
# ---------------------------------------------------------------------------


class TestSummarise:
    def test_empty(self) -> None:
        s = summarise([])
        assert s["total_frames"] == 0
        assert s["valid_frames"] == 0

    def test_total_count(self) -> None:
        rows = _sample_rows(10)
        s = summarise(rows)
        assert s["total_frames"] == 10

    def test_valid_invalid_split(self) -> None:
        rows = _sample_rows(10)
        s = summarise(rows)
        # 5 valid (indices 0,2,4,6,8), 5 invalid (indices 1,3,5,7,9)
        assert s["valid_frames"] == 5
        assert s["invalid_frames"] == 5

    def test_confidence_range(self) -> None:
        rows = _sample_rows(5)
        s = summarise(rows)
        assert s["confidence"]["min"] > 0.0
        assert s["confidence"]["max"] > s["confidence"]["min"]
        assert s["confidence"]["avg"] > 0.0

    def test_led_on_ratio(self) -> None:
        rows = _sample_rows(10)
        s = summarise(rows)
        # Half the frames are all-on, all LEDs have 50% ON ratio.
        for name in LED_NAMES:
            assert s["led_on_ratio"][name] == pytest.approx(0.5)

    def test_bitmask_distribution(self) -> None:
        rows = _sample_rows(10)
        s = summarise(rows)
        bd = s["bitmask_distribution"]
        assert "0x3F" in bd
        assert "0x00" in bd
        assert bd["0x3F"] == 5
        assert bd["0x00"] == 5

    def test_all_on_frames(self) -> None:
        """All frames 0x3F → all LEDs 100% ON."""
        rows = [_new_style_row(pattern="111111", bitmask="0x3F") for _ in range(10)]
        s = summarise(rows)
        for name in LED_NAMES:
            assert s["led_on_ratio"][name] == pytest.approx(1.0)
        assert s["bitmask_distribution"]["0x3F"] == 10

    def test_all_off_frames(self) -> None:
        """All frames 0x00 → all LEDs 0% ON."""
        rows = [_new_style_row(
            pattern="000000", bitmask="0x00",
            bits={n: 0 for n in LED_NAMES},
            means={n: 10.0 for n in LED_NAMES},
        ) for _ in range(10)]
        s = summarise(rows)
        for name in LED_NAMES:
            assert s["led_on_ratio"][name] == pytest.approx(0.0)

    def test_mixed_bitmasks(self) -> None:
        """Log with 8 distinct bitmasks → distribution correct."""
        bitmasks = ["0x00", "0x3F", "0x01", "0x02", "0x04", "0x08", "0x10", "0x20"]
        rows = []
        for bm in bitmasks:
            val = int(bm, 16)
            bits = {name: (val >> i) & 1 for i, name in enumerate(LED_NAMES)}
            rows.append(_new_style_row(
                pattern="".join(str(bits[n]) for n in LED_NAMES),
                bitmask=bm, bits=bits,
            ))
        s = summarise(rows)
        bd = s["bitmask_distribution"]
        for bm in bitmasks:
            assert bm in bd, f"bitmask {bm} missing from distribution"
            assert bd[bm] == 1

    def test_missing_led_columns_handled_gracefully(self) -> None:
        """Log may not have per-LED columns — should not crash."""
        rows = [
            {"valid": "1", "confidence": "0.9", "bitmask": "111111"},
        ]
        s = summarise(rows)
        assert s["total_frames"] == 1
        assert s["led_on_ratio"]["D0"] == 0.0  # no data → 0


# ---------------------------------------------------------------------------
# CLI --help and integration
# ---------------------------------------------------------------------------


class TestCliHelp:
    def test_help_works(self) -> None:
        script = str(
            Path(__file__).parent.parent / "tools" / "sixled_log_summary.py"
        )
        result = subprocess.run(
            [sys.executable, script, "--help"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert "CSV" in result.stdout or "JSONL" in result.stdout

    def test_no_args_shows_help_and_errors(self) -> None:
        script = str(
            Path(__file__).parent.parent / "tools" / "sixled_log_summary.py"
        )
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, timeout=15,
        )
        # Should print help and exit non-zero.
        assert "usage:" in result.stdout.lower() or "ERROR" in result.stderr

    def test_with_synthetic_csv(self) -> None:
        """Integration: create a CSV, run the tool against it."""
        rows = _sample_rows(20)
        path = _make_csv(rows, fieldnames=_NEW_CSV_FIELDNAMES)
        try:
            script = str(
                Path(__file__).parent.parent / "tools" / "sixled_log_summary.py"
            )
            result = subprocess.run(
                [sys.executable, script, path],
                capture_output=True, text=True, timeout=15,
            )
            assert result.returncode == 0, result.stderr
            assert "total_frames" in result.stdout
            assert "20" in result.stdout
            assert "LED ON ratio" in result.stdout
            assert "50.00%" in result.stdout or "0.50" in result.stdout
        finally:
            Path(path).unlink(missing_ok=True)

    def test_json_output(self) -> None:
        rows = _sample_rows(5)
        path = _make_csv(rows, fieldnames=_NEW_CSV_FIELDNAMES)
        try:
            script = str(
                Path(__file__).parent.parent / "tools" / "sixled_log_summary.py"
            )
            result = subprocess.run(
                [sys.executable, script, path, "--json"],
                capture_output=True, text=True, timeout=15,
            )
            assert result.returncode == 0
            data = json.loads(result.stdout)
            assert data["total_frames"] == 5
            assert "led_on_ratio" in data
        finally:
            Path(path).unlink(missing_ok=True)

    def test_with_jsonl(self) -> None:
        rows = _sample_rows(10)
        path = _make_jsonl(rows)
        try:
            script = str(
                Path(__file__).parent.parent / "tools" / "sixled_log_summary.py"
            )
            result = subprocess.run(
                [sys.executable, script, path],
                capture_output=True, text=True, timeout=15,
            )
            assert result.returncode == 0
            assert "total_frames" in result.stdout
        finally:
            Path(path).unlink(missing_ok=True)

    def test_with_old_broken_csv(self) -> None:
        """Integration: run summary against old-style broken CSV."""
        content = _old_broken_csv_content(20)
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            script = str(
                Path(__file__).parent.parent / "tools" / "sixled_log_summary.py"
            )
            result = subprocess.run(
                [sys.executable, script, tmp_path],
                capture_output=True, text=True, timeout=15,
            )
            assert result.returncode == 0, result.stderr
            assert "total_frames" in result.stdout
            assert "50.00%" in result.stdout or "0.50" in result.stdout
            assert "0x3F" in result.stdout
            assert "0x00" in result.stdout
        finally:
            Path(tmp_path).unlink(missing_ok=True)
