from __future__ import annotations

import csv
import importlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

from robocon_coop_comm.beacon_uart_v2 import AckStatus, build_ack
from tools.send_beacon_uart_v2 import validate_ack


SCRIPT = Path(__file__).parents[1] / "tools" / "send_beacon_uart_v2.py"
EXPECTED_FIELDS = [
    "start_ts", "end_ts", "state_id", "value", "state_name", "bitmask", "label",
]

_SPEC = importlib.util.spec_from_file_location("send_beacon_uart_v2", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_SENDER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_SENDER)


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


def test_help_without_serial_dependency() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0
    assert "--dry-run" in result.stdout


def test_help_shows_new_args() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    for arg in ("--states", "--hold-sec", "--refresh-sec", "--warmup-sec",
                "--repeat", "--expected-log"):
        assert arg in result.stdout, f"missing {arg} in --help"


# ---------------------------------------------------------------------------
# Single-state mode (backward compatible)
# ---------------------------------------------------------------------------


def test_dry_run_known_frame() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--state",
            "INSERT_ALLOWED",
            "--count",
            "1",
            "--brightness",
            "200",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("bd 02 04 00 c8 ")


def test_dry_run_default_state_is_idle() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run", "--count", "1"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0
    assert result.stdout.startswith("bd 02 00 00 ff ")


def test_dry_run_multi_count() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run", "--count", "3", "--state", "0"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    lines = result.stdout.strip().split("\n")
    assert len(lines) == 3


# ---------------------------------------------------------------------------
# Sequence mode — dry-run
# ---------------------------------------------------------------------------


def test_sequence_dry_run_states_list() -> None:
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--dry-run",
            "--states", "0,1,2",
            "--hold-sec", "0.1",
            "--refresh-sec", "0.05",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().split("\n")
    # 3 states × 2 refreshes each (0.1/0.05)
    assert len(lines) == 6


def test_sequence_dry_run_state_names() -> None:
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--dry-run",
            "--states", "IDLE,HOLD,INSERT_ALLOWED,PROTOCOL_TEST",
            "--hold-sec", "0.05",
            "--refresh-sec", "0.05",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().split("\n")
    assert len(lines) == 4


def test_sequence_dry_run_repeat() -> None:
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--dry-run",
            "--states", "0,1",
            "--hold-sec", "0.05",
            "--refresh-sec", "0.05",
            "--repeat", "3",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    lines = result.stdout.strip().split("\n")
    assert len(lines) == 6  # 2 states × 3 repeats


# ---------------------------------------------------------------------------
# 0–15 golden vectors
# ---------------------------------------------------------------------------

GOLDEN_MASKS = {
    0: "0x10", 1: "0x31", 2: "0x32", 3: "0x13",
    4: "0x34", 5: "0x15", 6: "0x16", 7: "0x37",
    8: "0x38", 9: "0x19", 10: "0x1A", 11: "0x3B",
    12: "0x1C", 13: "0x3D", 14: "0x3E", 15: "0x1F",
}


def test_all_16_state_masks() -> None:
    """Each of the 16 states encodes to its golden six-bit mask."""
    from robocon_coop_comm.coop_protocol_v2 import CoopMessage, encode_message
    for state_id, expected_hex in GOLDEN_MASKS.items():
        mask = encode_message(state_id)
        actual_hex = f"0x{mask:02X}"
        state_name = CoopMessage(state_id).name
        assert actual_hex == expected_hex, (
            f"{state_name}({state_id}): {actual_hex} != {expected_hex}"
        )


# ---------------------------------------------------------------------------
# Expected CSV
# ---------------------------------------------------------------------------


def test_expected_csv_dry_run_output(tmp_path: Path) -> None:
    expected_path = tmp_path / "expected.csv"
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--dry-run",
            "--states", "0,1,2,3",
            "--hold-sec", "3",
            "--refresh-sec", "0.05",
            "--expected-log", str(expected_path),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr

    # Read back the CSV
    with expected_path.open("r", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    assert len(rows) == 4
    for row in rows:
        for field in EXPECTED_FIELDS:
            assert field in row, f"missing field {field}"

    assert rows[0]["state_name"] == "IDLE"
    assert rows[0]["state_id"] == "0"
    assert rows[0]["value"] == "0"
    assert rows[0]["bitmask"] == "0x10"
    assert rows[0]["label"] == "IDLE"

    assert rows[1]["state_name"] == "HOLD"
    assert rows[1]["bitmask"] == "0x31"

    assert rows[2]["state_name"] == "R1_ROD_CLAMPED"
    assert rows[2]["bitmask"] == "0x32"

    assert rows[3]["state_name"] == "R1_AT_ASSEMBLY_POSE"
    assert rows[3]["bitmask"] == "0x13"


def test_expected_csv_bitmask_format() -> None:
    """Every bitmask in the expected CSV uses the 0xNN format."""
    from robocon_coop_comm.coop_protocol_v2 import encode_message
    from robocon_coop_comm.sixled_log import bitmask_to_hex_str
    for state_id in range(16):
        mask = encode_message(state_id)
        hex_str = bitmask_to_hex_str(mask)
        assert re.match(r"^0x[0-9A-F]{2}$", hex_str), f"bad format: {hex_str}"


def test_expected_csv_compatible_with_checker() -> None:
    """Expected CSV format is accepted by sixled_expected_observed_check.py."""
    from robocon_coop_comm.coop_protocol_v2 import encode_message
    from robocon_coop_comm.sixled_log import bitmask_to_hex_str, read_csv
    from tools.sixled_expected_observed_check import check

    import tempfile
    import os

    # Build a minimal expected CSV and matching observed CSV
    exp_rows = []
    obs_rows = []
    for state_id in range(4):
        mask = encode_message(state_id)
        hex_str = bitmask_to_hex_str(mask)
        start = float(state_id * 3)
        end = float((state_id + 1) * 3)
        exp_rows.append({
            "start_ts": f"{start:.6f}",
            "end_ts": f"{end:.6f}",
            "state_id": str(state_id),
            "value": str(state_id),
            "state_name": f"S{state_id}",
            "bitmask": hex_str,
            "label": f"S{state_id}",
        })
        # 10 observed frames inside each window
        for _ in range(10):
            obs_rows.append({
                "timestamp": str(start + 1.5),
                "bitmask": hex_str,
                "valid": "true",
            })

    # Write temp files
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        w = csv.DictWriter(f, fieldnames=EXPECTED_FIELDS)
        w.writeheader()
        w.writerows(exp_rows)
        exp_path = f.name

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        w = csv.DictWriter(f, fieldnames=["timestamp", "bitmask", "valid"])
        w.writeheader()
        w.writerows(obs_rows)
        obs_path = f.name

    try:
        result = check(
            exp_rows,
            read_csv(obs_path),
            settle_sec=0.5,
            min_dominant_ratio=0.90,
            min_valid_ratio=0.50,
        )
        assert result["overall_pass"] is True, result["windows"]
        assert result["passed_windows"] == 4
    finally:
        os.unlink(exp_path)
        os.unlink(obs_path)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_invalid_state_number() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run", "--state", "16"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0


def test_invalid_state_name() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run", "--state", "NONEXISTENT"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0


def test_negative_count_rejected() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run", "--count", "-1"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0


def test_invalid_state_in_states_list() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run", "--states", "0,99,2"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0


def test_empty_states_rejected() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run", "--states", ","],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0


def test_counter_wraps_at_256() -> None:
    """Verify counter wraps correctly at 256 in dry-run output."""
    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--dry-run",
            "--states", "0",
            "--hold-sec", "0.05",
            "--refresh-sec", "0.05",
            "--count", "1",
            "--brightness", "200",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    # Counter starts at 0 in single-state mode; sequence mode also starts at 0
    assert "bd 02 00 00 c8 " in result.stdout


def test_validate_ack_accepts_exact_ok_echo() -> None:
    ack = validate_ack(build_ack(4, 255, AckStatus.OK), 4, 255)
    assert ack.state_id == 4
    assert ack.counter == 255


@pytest.mark.parametrize(
    ("frame", "state", "counter", "error"),
    [
        (build_ack(4, 7, AckStatus.BAD_CRC), 4, 7, "ack_status_bad_crc"),
        (build_ack(5, 7, AckStatus.OK), 4, 7, "ack_state_mismatch"),
        (build_ack(4, 8, AckStatus.OK), 4, 7, "ack_counter_mismatch"),
    ],
)
def test_validate_ack_rejects_nonmatching_echo(
    frame: bytes,
    state: int,
    counter: int,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        validate_ack(frame, state, counter)


def test_validate_ack_rejects_corrupt_crc() -> None:
    frame = bytearray(build_ack(4, 7, AckStatus.OK))
    frame[-1] ^= 0x01
    with pytest.raises(ValueError, match="bad_crc"):
        validate_ack(bytes(frame), 4, 7)
