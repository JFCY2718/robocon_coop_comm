"""Tests for sixled_expected_observed_check.py — no real hardware required."""

from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tools.sixled_expected_observed_check import check as _check
from robocon_coop_comm.sixled_log import LED_NAMES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_obs_row(
    timestamp: float,
    bitmask: str = "0x3F",
    valid: str = "1",
    confidence: str = "0.95",
    bits: dict[str, int] | None = None,
) -> dict:
    """Build a new-style observed CSV row."""
    if bits is None:
        bits = {n: 1 for n in LED_NAMES}
    return {
        "timestamp": f"{timestamp:.6f}",
        "msg_id": "0",
        "seq": "0",
        "valid": valid,
        "confidence": confidence,
        "latency_ms": "5.0",
        "pattern": "".join(str(bits[n]) for n in LED_NAMES),
        "bitmask": bitmask,
        **{n: str(bits[n]) for n in LED_NAMES},
        **{f"{n}_mean": "200.0" for n in LED_NAMES},
    }


def _new_exp_row(start: float, end: float, value: int, bitmask: str, label: str) -> dict:
    return {
        "start_ts": f"{start:.6f}",
        "end_ts": f"{end:.6f}",
        "value": str(value),
        "bitmask": bitmask,
        "pattern": "000000",
        "label": label,
    }


def _make_csv(rows: list[dict], fieldnames: list[str] | None = None) -> str:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="")
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


# Fixed expected fields for the checker.
_EXPECTED_FIELDNAMES = ["start_ts", "end_ts", "value", "bitmask", "pattern", "label"]


# ---------------------------------------------------------------------------
# CLI --help
# ---------------------------------------------------------------------------


class TestCliHelp:
    def test_help_works(self) -> None:
        script = str(Path(__file__).parent.parent / "tools" / "sixled_expected_observed_check.py")
        result = subprocess.run(
            [sys.executable, script, "--help"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert "expected" in result.stdout.lower()

    def test_missing_required_args_reports_error(self) -> None:
        script = str(Path(__file__).parent.parent / "tools" / "sixled_expected_observed_check.py")
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# Dominant bitmask matching
# ---------------------------------------------------------------------------


class TestDominantMatching:
    def test_perfect_match_passes(self) -> None:
        """8 windows of 100 all-matching frames each — all PASS."""
        exp_rows = []
        obs_rows = []

        for i in range(8):
            start = 1000.0 + i * 5.0
            end = start + 5.0
            bm = "0x00" if i % 2 == 0 else "0x3F"
            exp_rows.append(_new_exp_row(start, end, i, bm, f"label_{i}"))
            # 100 frames in each window
            for j in range(100):
                ts = start + 0.01 + j * 0.01  # skip settle_sec
                obs_rows.append(_new_obs_row(ts, bitmask=bm))

        result = _check(exp_rows, obs_rows, settle_sec=0.01, min_dominant_ratio=0.90)
        assert result["overall_pass"] is True
        assert result["passed_windows"] == 8

    def test_dominant_mismatch_fails(self) -> None:
        """One window with wrong dominant bitmask → overall FAIL."""
        exp_rows = [
            _new_exp_row(1000.0, 1005.0, 0, "0x00", "all_off"),
            _new_exp_row(1005.0, 1010.0, 63, "0x3F", "all_on"),
        ]
        obs_rows = []
        # window 1: all 0x00 — matches
        for j in range(50):
            obs_rows.append(_new_obs_row(1000.5 + j * 0.01, bitmask="0x00"))
        # window 2: most 0x00 but expected 0x3F
        for j in range(50):
            obs_rows.append(_new_obs_row(1005.5 + j * 0.01, bitmask="0x00"))

        result = _check(exp_rows, obs_rows, settle_sec=0.01, min_dominant_ratio=0.80)
        assert result["overall_pass"] is False
        assert result["windows"][1]["result"] == "FAIL"

    def test_ratio_below_threshold_fails(self) -> None:
        """Dominant matches but ratio below threshold → FAIL."""
        exp_rows = [_new_exp_row(1000.0, 1005.0, 63, "0x3F", "all_on")]
        obs_rows = []
        # 50 frames 0x3F, 50 frames 0x00 → dominant 0x3F at 50%
        for j in range(50):
            obs_rows.append(_new_obs_row(1000.5 + j * 0.01, bitmask="0x3F"))
        for j in range(50):
            obs_rows.append(_new_obs_row(1000.5 + 0.5 + j * 0.01, bitmask="0x00"))

        result = _check(exp_rows, obs_rows, settle_sec=0.01, min_dominant_ratio=0.90)
        assert result["overall_pass"] is False
        assert result["windows"][0]["result"] == "FAIL"


# ---------------------------------------------------------------------------
# settle_sec trimming
# ---------------------------------------------------------------------------


class TestSettleSec:
    def test_settle_sec_excludes_boundary_frames(self) -> None:
        """Frames within settle_sec of start are excluded."""
        exp_rows = [_new_exp_row(1000.0, 1005.0, 63, "0x3F", "all_on")]
        obs_rows = [
            _new_obs_row(1000.0, bitmask="0x00"),   # at boundary, excluded
            _new_obs_row(1000.2, bitmask="0x00"),   # within settle_sec=0.5, excluded
            _new_obs_row(1000.6, bitmask="0x3F"),   # after settle_sec, included
            _new_obs_row(1001.0, bitmask="0x3F"),
            _new_obs_row(1002.0, bitmask="0x3F"),
        ]
        result = _check(exp_rows, obs_rows, settle_sec=0.5, min_dominant_ratio=0.90)
        # After settle_sec, 3 frames of 0x3F → dominant=0x3F, ratio=1.0 → PASS
        assert result["windows"][0]["result"] == "PASS"
        assert result["windows"][0]["frames"] == 3


# ---------------------------------------------------------------------------
# Old broken CSV compatibility
# ---------------------------------------------------------------------------


class TestOldBrokenCsv:
    def test_old_csv_with_row_none_works(self) -> None:
        """Old broken CSV where extra fields are in row[None]."""
        exp_rows = [_new_exp_row(1000.0, 1005.0, 63, "0x3F", "all_on")]
        obs_rows = []
        for j in range(10):
            # old-style: 6 base fields, 14 extras in row[None]
            obs_rows.append({
                "timestamp": f"{1000.5 + j * 0.01:.6f}",
                "msg_id": "0", "seq": "0", "valid": "1",
                "confidence": "0.95", "latency_ms": "5.0",
                None: ["111111", "0x3F", "1", "1", "1", "1", "1", "1",
                        "50.0", "52.0", "72.0", "78.0", "41.0", "60.0"],
            })
        result = _check(exp_rows, obs_rows, settle_sec=0.01, min_dominant_ratio=0.80)
        assert result["windows"][0]["result"] == "PASS"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_observed_graceful(self) -> None:
        """No observed frames → per-window FAIL, overall FAIL."""
        exp_rows = [_new_exp_row(1000.0, 1005.0, 63, "0x3F", "all_on")]
        result = _check(exp_rows, [], settle_sec=0.01)
        assert result["overall_pass"] is False
        assert "no observed frames" in result["windows"][0]["reason"]

    def test_window_no_matching_frames(self) -> None:
        """Observed frames exist but none in this time window."""
        exp_rows = [_new_exp_row(1000.0, 1005.0, 63, "0x3F", "all_on")]
        obs_rows = [_new_obs_row(2000.0, bitmask="0x3F")]  # outside window
        result = _check(exp_rows, obs_rows, settle_sec=0.01)
        assert result["overall_pass"] is False
        assert "no observed frames" in result["windows"][0]["reason"]

    def test_valid_ratio_below_min_fails(self) -> None:
        """Too few valid frames → FAIL."""
        exp_rows = [_new_exp_row(1000.0, 1005.0, 63, "0x3F", "all_on")]
        obs_rows = []
        for j in range(10):
            obs_rows.append(_new_obs_row(1000.5 + j * 0.01, bitmask="0x3F", valid="0"))
        result = _check(exp_rows, obs_rows, settle_sec=0.01, min_valid_ratio=0.50)
        assert result["windows"][0]["result"] == "FAIL"

    def test_no_expected_windows(self) -> None:
        """If expected rows have no parsable timestamps, result is empty."""
        # Row without proper start_ts → _is_valid_window returns False
        result = _check([{"garbage": "x"}], [_new_obs_row(1000.0)], settle_sec=0.01)
        assert result["total_windows"] == 0
        assert result["overall_pass"] is True  # vacuously true

    def test_json_output(self) -> None:
        """JSON output mode produces valid JSON."""
        exp_rows = [_new_exp_row(1000.0, 1005.0, 63, "0x3F", "all_on")]
        obs_rows = [_new_obs_row(1001.0, bitmask="0x3F") for _ in range(10)]

        script = str(Path(__file__).parent.parent / "tools" / "sixled_expected_observed_check.py")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as ef:
            writer = csv.DictWriter(ef, fieldnames=_EXPECTED_FIELDNAMES)
            writer.writeheader()
            for r in exp_rows:
                writer.writerow(r)
            exp_path = ef.name
        obs_path = _make_csv(obs_rows)

        try:
            result = subprocess.run(
                [sys.executable, script, "--expected", exp_path, "--observed", obs_path, "--json"],
                capture_output=True, text=True, timeout=15,
            )
            assert result.returncode == 0
            data = json.loads(result.stdout)
            assert data["overall_pass"] is True
            assert data["total_windows"] == 1
        finally:
            Path(exp_path).unlink(missing_ok=True)
            Path(obs_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# check function with explicit tests (no CLI subprocess)
# ---------------------------------------------------------------------------


class TestCheckFunction:
    def test_check_returns_structured_result(self) -> None:
        exp_rows = [_new_exp_row(1000.0, 1005.0, 63, "0x3F", "all_on")]
        obs_rows = [_new_obs_row(1001.0, bitmask="0x3F") for _ in range(10)]
        result = _check(exp_rows, obs_rows, settle_sec=0.5)
        assert "windows" in result
        assert "overall_pass" in result
        assert "total_windows" in result
        assert "passed_windows" in result
        assert "failed_windows" in result

    def test_check_with_settle_sec_zero(self) -> None:
        """settle_sec=0 includes all frames from start of window."""
        exp_rows = [_new_exp_row(1000.0, 1005.0, 63, "0x3F", "all_on")]
        obs_rows = [_new_obs_row(1000.0, bitmask="0x3F") for _ in range(10)]
        result = _check(exp_rows, obs_rows, settle_sec=0.0)
        assert result["windows"][0]["frames"] == 10
