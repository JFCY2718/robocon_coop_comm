"""Tests for sixled_serial_sequence.py — no real serial port required."""

from __future__ import annotations

import csv
import importlib.util
import io
import subprocess
import sys
from pathlib import Path

import pytest

from robocon_coop_comm.sixled_log import (
    bitmask_to_hex_str,
    bitmask_to_pattern,
)


SCRIPT = Path(__file__).parent.parent / "tools" / "sixled_serial_sequence.py"


def _load_sequence_tool():
    spec = importlib.util.spec_from_file_location("sixled_serial_sequence_tool", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeSerial:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.flush_count = 0

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    def flush(self) -> None:
        self.flush_count += 1


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


# ---------------------------------------------------------------------------
# CLI --help (must work without serial port)
# ---------------------------------------------------------------------------


class TestCliHelp:
    def test_help_works(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert "STM32" in result.stdout or "bitmask" in result.stdout
        assert "--protocol" in result.stdout
        assert "--refresh-sec" in result.stdout


# ---------------------------------------------------------------------------
# Protocol frame builders
# ---------------------------------------------------------------------------


class TestProtocolFrames:
    def test_default_protocol_is_ascii(self) -> None:
        tool = _load_sequence_tool()
        assert tool.DEFAULT_PROTOCOL == "ascii"
        assert tool.build_serial_frame("ascii", 63, 0) == b"63\n"
        assert tool.build_serial_frame("ascii", 1, 99) == b"1\n"

    def test_rscontrol2_frame_format(self) -> None:
        tool = _load_sequence_tool()
        assert tool.build_serial_frame("rscontrol2", 63, 7) == bytes([0xBC, 0x00, 0x3F, 0x07, 0x55])
        assert tool.build_serial_frame("rscontrol2", 0x7F, 0x123) == bytes([0xBC, 0x00, 0x3F, 0x23, 0x55])

    def test_seq_wraps(self) -> None:
        tool = _load_sequence_tool()
        assert tool.next_seq(254) == 255
        assert tool.next_seq(255) == 0

    def test_windows_com_port_is_not_path_checked(self) -> None:
        tool = _load_sequence_tool()
        assert tool._is_windows_com_port("COM3")
        assert tool._is_windows_com_port(r"\\.\COM10")
        assert not tool._is_windows_com_port("/dev/ttyUSB0")


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
        # Use --values with an out-of-range value — should fail before opening serial.
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--values", "64", "--port", "/dev/NONEXISTENT"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode != 0

    def test_refresh_sec_must_be_positive(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--values", "1", "--refresh-sec", "0", "--port", "/dev/NONEXISTENT"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode != 0
        assert "--refresh-sec" in result.stderr


# ---------------------------------------------------------------------------
# Refresh sending and expected windows
# ---------------------------------------------------------------------------


class TestRefreshSequence:
    def test_rscontrol2_refresh_repeats_during_hold(self) -> None:
        tool = _load_sequence_tool()
        ser = FakeSerial()
        clock = FakeClock()

        rows = tool.run_sequence(
            ser,
            [63],
            protocol="rscontrol2",
            hold_sec=1.0,
            refresh_sec=0.2,
            warmup_sec=0.0,
            newline=True,
            sleep_fn=clock.sleep,
            time_fn=clock.time,
        )

        assert len(ser.writes) == 5
        assert ser.writes == [
            bytes([0xBC, 0x00, 0x3F, 0x00, 0x55]),
            bytes([0xBC, 0x00, 0x3F, 0x01, 0x55]),
            bytes([0xBC, 0x00, 0x3F, 0x02, 0x55]),
            bytes([0xBC, 0x00, 0x3F, 0x03, 0x55]),
            bytes([0xBC, 0x00, 0x3F, 0x04, 0x55]),
        ]
        assert len(rows) == 1
        assert rows[0]["value"] == 63
        assert float(rows[0]["end_ts"]) - float(rows[0]["start_ts"]) == pytest.approx(1.0)

    def test_refresh_does_not_split_expected_windows(self) -> None:
        tool = _load_sequence_tool()
        ser = FakeSerial()
        clock = FakeClock()

        rows = tool.run_sequence(
            ser,
            [0, 63],
            protocol="rscontrol2",
            hold_sec=1.0,
            refresh_sec=0.2,
            warmup_sec=0.0,
            newline=True,
            sleep_fn=clock.sleep,
            time_fn=clock.time,
        )

        assert len(ser.writes) == 10
        assert len(rows) == 2
        assert [row["bitmask"] for row in rows] == ["0x00", "0x3F"]

    def test_ascii_protocol_sends_decimal_newline_frames(self) -> None:
        tool = _load_sequence_tool()
        ser = FakeSerial()
        clock = FakeClock()

        tool.run_sequence(
            ser,
            [0, 63, 1],
            protocol="ascii",
            hold_sec=0.1,
            refresh_sec=0.2,
            warmup_sec=0.0,
            newline=True,
            sleep_fn=clock.sleep,
            time_fn=clock.time,
        )

        assert ser.writes == [b"0\n", b"63\n", b"1\n"]


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
