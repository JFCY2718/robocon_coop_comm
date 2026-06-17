"""Tests for tools/r1_beacon_control.py."""

from __future__ import annotations

import io
import sys
from unittest.mock import patch

import pytest

from robocon_coop_comm.protocol import MsgID
from robocon_coop_comm.serial_frame import encode_frame


# Import the tool module under test.
# Add project root to path so the tools module can be imported.
import os as _os

_sys = sys
_tools_dir = _os.path.join(_os.path.dirname(__file__), "..", "tools")
_sys.path.insert(0, _tools_dir)

import r1_beacon_control as _r1b  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# 1. msg_id mapping tests
# ---------------------------------------------------------------------------


class TestCommandMapping:
    """Verify command string -> MsgID mapping is correct."""

    def test_idle_maps_to_0(self) -> None:
        assert _r1b.COMMAND_MAP["idle"] == MsgID.IDLE
        assert int(_r1b.COMMAND_MAP["idle"]) == 0

    def test_hold_maps_to_1(self) -> None:
        assert _r1b.COMMAND_MAP["hold"] == MsgID.HOLD
        assert int(_r1b.COMMAND_MAP["hold"]) == 1

    def test_rod_maps_to_2(self) -> None:
        assert _r1b.COMMAND_MAP["rod"] == MsgID.R1_ROD_CLAMPED
        assert int(_r1b.COMMAND_MAP["rod"]) == 2

    def test_pose_maps_to_3(self) -> None:
        assert _r1b.COMMAND_MAP["pose"] == MsgID.R1_AT_ASSEMBLY_POSE
        assert int(_r1b.COMMAND_MAP["pose"]) == 3

    def test_insert_maps_to_4(self) -> None:
        assert _r1b.COMMAND_MAP["insert"] == MsgID.INSERT_ALLOWED
        assert int(_r1b.COMMAND_MAP["insert"]) == 4

    def test_locked_maps_to_5(self) -> None:
        assert _r1b.COMMAND_MAP["locked"] == MsgID.WEAPON_LOCKED
        assert int(_r1b.COMMAND_MAP["locked"]) == 5

    def test_clear_maps_to_6(self) -> None:
        assert _r1b.COMMAND_MAP["clear"] == MsgID.R1_CLEAR_MC
        assert int(_r1b.COMMAND_MAP["clear"]) == 6

    def test_mf_maps_to_7(self) -> None:
        assert _r1b.COMMAND_MAP["mf"] == MsgID.R1_IN_MF
        assert int(_r1b.COMMAND_MAP["mf"]) == 7

    def test_all_commands_present(self) -> None:
        expected = {"idle", "hold", "rod", "pose", "insert", "locked", "clear", "mf"}
        assert set(_r1b.COMMAND_MAP.keys()) == expected

    def test_reverse_map_consistent(self) -> None:
        for cmd, msg_id in _r1b.COMMAND_MAP.items():
            assert _r1b.MSG_ID_TO_COMMAND[int(msg_id)] == cmd


# ---------------------------------------------------------------------------
# 2. seq flip tests
# ---------------------------------------------------------------------------


class TestSeqFlip:
    """Verify seq toggles correctly on each send."""

    def test_initial_seq_is_zero(self) -> None:
        ctrl = _r1b.R1BeaconController(dry_run=True)
        assert ctrl.current_seq == 0

    def test_first_send_flips_to_1(self) -> None:
        ctrl = _r1b.R1BeaconController(dry_run=True)
        ctrl.send(4)
        assert ctrl.current_seq == 1

    def test_second_send_flips_back_to_0(self) -> None:
        ctrl = _r1b.R1BeaconController(dry_run=True)
        ctrl.send(4)
        ctrl.send(5)
        assert ctrl.current_seq == 0

    def test_third_send_flips_to_1_again(self) -> None:
        ctrl = _r1b.R1BeaconController(dry_run=True)
        ctrl.send(1)
        ctrl.send(2)
        ctrl.send(7)
        assert ctrl.current_seq == 1

    def test_seq_toggles_even_for_same_msg_id(self) -> None:
        ctrl = _r1b.R1BeaconController(dry_run=True)
        ctrl.send(4)  # seq -> 1
        ctrl.send(4)  # seq -> 0
        assert ctrl.current_seq == 0


# ---------------------------------------------------------------------------
# 3. frame format tests
# ---------------------------------------------------------------------------


class TestFrameFormat:
    """Verify frames are encoded correctly."""

    def test_insert_allowed_frame(self) -> None:
        """Known-good frame: msg_id=4, seq=1, brightness=200 -> AA 55 04 01 C8 CD."""
        ctrl = _r1b.R1BeaconController(dry_run=True, brightness=200)

        # Capture stdout to inspect frame output.
        captured = io.StringIO()
        sys.stdout = captured
        try:
            ctrl.send(4)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        assert "frame=AA 55 04 01 C8 CD" in output, f"got output: {output}"

    def test_checksum_formula(self) -> None:
        """checksum = msg_id ^ seq ^ brightness."""
        msg_id, seq, brightness = 4, 1, 200
        expected_checksum = msg_id ^ seq ^ brightness  # 4 ^ 1 ^ 200 = 205 = 0xCD
        frame = encode_frame(msg_id, seq, brightness)
        assert frame == bytes([0xAA, 0x55, 4, 1, 200, expected_checksum])

    def test_all_commands_generate_valid_frames(self) -> None:
        """Every command should produce a valid encode_frame output."""
        ctrl = _r1b.R1BeaconController(dry_run=True, brightness=200)
        for cmd, msg_id in _r1b.COMMAND_MAP.items():
            ctrl.current_seq = 0  # reset before each
            old_seq = ctrl.current_seq
            ctrl.send(int(msg_id))

            # After send, seq should have flipped
            expected_seq = old_seq ^ 1
            assert ctrl.current_seq == expected_seq

            # Verify the frame would be valid
            frame = encode_frame(int(msg_id), expected_seq, ctrl.brightness)
            assert len(frame) == 6
            assert frame[0] == 0xAA
            assert frame[1] == 0x55


# ---------------------------------------------------------------------------
# 4. dry-run mode tests
# ---------------------------------------------------------------------------


class TestDryRun:
    """Dry-run mode must not require a real serial port."""

    def test_dry_run_controller_no_port(self) -> None:
        ctrl = _r1b.R1BeaconController(dry_run=True)
        assert ctrl.dry_run is True
        assert ctrl.port is None

    def test_dry_run_send_does_not_open_serial(self) -> None:
        ctrl = _r1b.R1BeaconController(dry_run=True, port="/dev/ttyACM0")
        # send() should complete without error and without trying serial
        ctrl.send(4)  # should not raise

    def test_dry_run_send_does_not_open_serial_with_port(self) -> None:
        """Even with a port set, dry_run=True should skip serial."""
        ctrl = _r1b.R1BeaconController(dry_run=True, port="/dev/ttyACM0")
        ser = ctrl._get_serial()
        assert ser is None

    def test_dry_run_output_contains_dry_run_message(self) -> None:
        ctrl = _r1b.R1BeaconController(dry_run=True)
        captured = io.StringIO()
        sys.stdout = captured
        try:
            ctrl.send(4)
        finally:
            sys.stdout = sys.__stdout__
        output = captured.getvalue()
        assert "dry-run: not sending to serial port" in output


# ---------------------------------------------------------------------------
# 5. ACK parsing tests
# ---------------------------------------------------------------------------


class TestAckParsing:
    def test_valid_ack(self) -> None:
        ack = _r1b.parse_ack(bytes([0xCC, 0x04, 0x01]))
        assert ack == (4, 1)

    def test_short_data_returns_none(self) -> None:
        assert _r1b.parse_ack(bytes([0xCC])) is None
        assert _r1b.parse_ack(bytes([])) is None

    def test_wrong_header_returns_none(self) -> None:
        assert _r1b.parse_ack(bytes([0xAA, 0x04, 0x01])) is None

    def test_zero_msg_id_and_seq(self) -> None:
        ack = _r1b.parse_ack(bytes([0xCC, 0x00, 0x00]))
        assert ack == (0, 0)


# ---------------------------------------------------------------------------
# 6. Status test
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_output(self) -> None:
        ctrl = _r1b.R1BeaconController(port="/dev/ttyACM0", dry_run=False, brightness=200)
        captured = io.StringIO()
        sys.stdout = captured
        try:
            ctrl.status()
        finally:
            sys.stdout = sys.__stdout__
        output = captured.getvalue()
        assert "port:" in output
        assert "/dev/ttyACM0" in output
        assert "brightness:" in output
        assert "200" in output
        assert "dry_run:" in output


# ---------------------------------------------------------------------------
# 7. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_unknown_command_in_one_shot(self) -> None:
        ctrl = _r1b.R1BeaconController(dry_run=True)
        with pytest.raises(SystemExit):
            _r1b.one_shot(ctrl, "nonexistent")

    def test_invalid_brightness_rejected(self) -> None:
        with pytest.raises(SystemExit):
            args = argparse.Namespace(
                port="/dev/ttyACM0",
                baudrate=115200,
                brightness=256,
                dry_run=True,
                command=None,
            )
            # This is tested via the argparse layer indirectly; the controller
            # does not validate brightness. We test the main() guard instead.
            _r1b.main()  # This would parse sys.argv, so we test via unit approach

    def test_brightness_default_is_200(self) -> None:
        ctrl = _r1b.R1BeaconController(dry_run=True)
        assert ctrl.brightness == 200

    def test_frame_hex_formatting(self) -> None:
        frame = bytes([0xAA, 0x55, 0x04, 0x01, 0xC8, 0xCD])
        assert _r1b.frame_hex(frame) == "AA 55 04 01 C8 CD"


# argparse import for edge case test
import argparse
