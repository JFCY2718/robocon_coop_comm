"""Tests for sixled_serial_sequence.py — no real serial port required."""

from __future__ import annotations

import csv
import io
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from robocon_coop_comm.sixled_log import (
    bitmask_to_hex_str,
    bitmask_to_pattern,
    parse_bitmask_str,
)


# ---------------------------------------------------------------------------
# CLI --help (must work without serial port)
# ---------------------------------------------------------------------------


class TestCliHelp:
    def test_help_works(self) -> None:
        script = str(Path(__file__).parent.parent / "tools" / "sixled_serial_sequence.py")
        result = subprocess.run(
            [sys.executable, script, "--help"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert "STM32" in result.stdout or "bitmask" in result.stdout


# ---------------------------------------------------------------------------
# Value parsing (via --values arg)
# ---------------------------------------------------------------------------


class TestValueParsing:
    def test_default_values_parse_correctly(self) -> None:
        """The default --values '0,63,1,2,4,8,16,32' must all be valid 0-63."""
        default = "0,63,1,2,4,8,16,32"
        values = [int(s.strip()) for s in default.split(",")]
        assert len(values) == 8
        for v in values:
            assert 0 <= v <= 63

    def test_single_value_ok(self) -> None:
        values = [0]
        assert all(0 <= v <= 63 for v in values)

    def test_values_out_of_range_rejected(self) -> None:
        script = str(Path(__file__).parent.parent / "tools" / "sixled_serial_sequence.py")
        # Use --values with an out-of-range value — should fail before opening serial.
        result = subprocess.run(
            [sys.executable, script, "--values", "64", "--port", "/dev/NONEXISTENT"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# Bitmask to pattern correctness
# ---------------------------------------------------------------------------


class TestBitmaskPatternMapping:
    @pytest.mark.parametrize("val, pattern, hex_str", [
        (0, "000000", "0x00"),
        (63, "111111", "0x3F"),
        (1, "100000", "0x01"),
        (2, "010000", "0x02"),
        (4, "001000", "0x04"),
        (8, "000100", "0x08"),
        (16, "000010", "0x10"),
        (32, "000001", "0x20"),
    ])
    def test_pattern_and_hex(self, val: int, pattern: str, hex_str: str) -> None:
        assert bitmask_to_pattern(val) == pattern
        assert bitmask_to_hex_str(val) == hex_str


# ---------------------------------------------------------------------------
# Expected CSV format
# ---------------------------------------------------------------------------


class TestExpectedCsvFormat:
    def test_expected_csv_fields(self) -> None:
        """Expected CSV must have all 6 required fields."""
        expected_fields = ["start_ts", "end_ts", "value", "bitmask", "pattern", "label"]
        row = {
            "start_ts": "1782119000.000000",
            "end_ts": "1782119005.000000",
            "value": "0",
            "bitmask": "0x00",
            "pattern": "000000",
            "label": "all_off",
        }
        for f in expected_fields:
            assert f in row

    def test_read_expected_csv(self) -> None:
        """Expected CSV can be read by csv.DictReader."""
        content = (
            "start_ts,end_ts,value,bitmask,pattern,label\n"
            "1000.0,1005.0,0,0x00,000000,all_off\n"
            "1005.0,1010.0,63,0x3F,111111,all_on\n"
        )
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["bitmask"] == "0x00"
        assert rows[1]["bitmask"] == "0x3F"
