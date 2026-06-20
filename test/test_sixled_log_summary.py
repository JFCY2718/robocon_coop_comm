"""Tests for sixled_log_summary — log analysis tool.

Covers:
- CSV parsing
- JSONL parsing
- Empty log
- Summary statistics correctness
- LED ON ratio calculation
- Bitmask distribution
- CLI --help
- CLI with synthetic log file (integration)
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
    _read_csv,
    _read_jsonl,
    summarise,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_csv(rows: list[dict]) -> str:
    """Write rows to a temp CSV file and return the path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    )
    if not rows:
        tmp.close()
        return tmp.name

    writer = csv.DictWriter(tmp, fieldnames=list(rows[0].keys()))
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


def _sample_rows(n: int = 10) -> list[dict]:
    """Generate synthetic 6-LED log records."""
    rows = []
    for i in range(n):
        # Alternate between all-on and all-off patterns.
        if i % 2 == 0:
            bits = {name: 1 for name in LED_NAMES}
            mask = "111111"
        else:
            bits = {name: 0 for name in LED_NAMES}
            mask = "000000"
        rows.append({
            "timestamp": f"{1720000000 + i}.123456",
            "msg_id": "0",
            "seq": "0",
            "valid": "1" if i % 2 == 0 else "0",
            "confidence": f"{0.8 + i * 0.01:.4f}",
            "latency_ms": f"{10 + i * 0.5:.3f}",
            "bitmask": mask,
            "bitmask_hex": f"0x{0x3F if i % 2 == 0 else 0x00:02X}",
            **{name: str(bits[name]) for name in LED_NAMES},
            **{f"b_{name}": f"{200.0 if bits[name] else 10.0:.1f}" for name in LED_NAMES},
        })
    return rows


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
        path = _make_csv(rows)
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


# ---------------------------------------------------------------------------
# summarise
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
        assert "111111" in bd
        assert "000000" in bd
        assert bd["111111"] == 5
        assert bd["000000"] == 5

    def test_missing_led_columns_handled(self) -> None:
        """Log may not have per-LED columns (older format)."""
        rows = [
            {"valid": "1", "confidence": "0.9", "bitmask": "111111"},
        ]
        s = summarise(rows)
        assert s["total_frames"] == 1
        assert s["led_on_ratio"]["D0"] == 0.0  # no data → 0


# ---------------------------------------------------------------------------
# CLI --help
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
        path = _make_csv(rows)
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
        path = _make_csv(rows)
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
