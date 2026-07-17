from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "tools" / "send_beacon_uart_v2.py"


def test_help_without_serial_dependency() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0
    assert "--dry-run" in result.stdout


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
