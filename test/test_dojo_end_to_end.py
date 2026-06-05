"""Tests for dojo end-to-end pipeline."""

from __future__ import annotations

import pytest

from robocon_coop_comm.dojo_end_to_end import DojoEndToEndPipeline, DojoStepResult

cv2 = pytest.importorskip("cv2")


def _setup_pipeline(min_stable_frames: int = 3) -> DojoEndToEndPipeline:
    return DojoEndToEndPipeline(min_stable_frames=min_stable_frames)


class TestDojoEndToEndPipeline:
    def test_init(self) -> None:
        p = _setup_pipeline()
        assert p.r1 is not None
        assert p.r2 is not None

    def test_execute_to_rod_clamped(self) -> None:
        p = _setup_pipeline()
        p.execute_key("START", "s")
        p.set_r1_sensor(rod_clamped=True)
        r = p.execute_key("R1_ROD_CLAMPED", "n")

        assert isinstance(r, DojoStepResult)
        assert r.r1_msg_id == 2
        assert r.r1_msg_name == "R1_ROD_CLAMPED"
        assert r.stable_valid is True

    def test_execute_to_assembly_pose(self) -> None:
        p = _setup_pipeline()
        p.execute_key("START", "s")
        p.set_r1_sensor(rod_clamped=True)
        p.execute_key("R1_ROD_CLAMPED", "n")
        p.set_r1_sensor(in_assembly_pose=True)
        r = p.execute_key("R1_AT_ASSEMBLY_POSE", "n")

        assert r.r1_msg_id == 3
        assert r.stable_valid is True

    def test_insert_allowed_without_r2_sensors(self) -> None:
        """Without R2 local sensors, R2 should NOT enter INSERTING."""
        p = _setup_pipeline()
        p.execute_key("START", "s")
        p.set_r1_sensor(rod_clamped=True)
        p.execute_key("R1_ROD_CLAMPED", "n")
        p.set_r1_sensor(in_assembly_pose=True)
        p.execute_key("R1_AT_ASSEMBLY_POSE", "n")
        p.set_r1_sensor(rod_pose_locked=True, chassis_stopped=True)
        # Do NOT set R2 sensors
        r = p.execute_key("INSERT_ALLOWED", "n")

        assert r.r1_msg_id == 4
        # R2 should not be in INSERTING without local sensors ready
        assert r.r2_state != "INSERTING"

    def test_insert_allowed_with_r2_sensors(self) -> None:
        """With R2 local sensors ready, INSERT_ALLOWED should move R2 toward insertion."""
        p = _setup_pipeline()
        p.execute_key("START", "s")
        p.set_r1_sensor(rod_clamped=True)
        p.execute_key("R1_ROD_CLAMPED", "n")
        p.set_r1_sensor(in_assembly_pose=True)
        p.execute_key("R1_AT_ASSEMBLY_POSE", "n")
        p.set_r1_sensor(rod_pose_locked=True, chassis_stopped=True)
        p.set_r2_sensor(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        r = p.execute_key("INSERT_ALLOWED", "n")

        assert r.r1_msg_id == 4
        assert r.r2_state == "INSERTING"

    def test_weapon_locked_releases(self) -> None:
        """WEAPON_LOCKED should move R2 to HEAD_RELEASED."""
        p = _setup_pipeline()
        p.execute_key("START", "s")
        p.set_r1_sensor(rod_clamped=True)
        p.execute_key("R1_ROD_CLAMPED", "n")
        p.set_r1_sensor(in_assembly_pose=True)
        p.execute_key("R1_AT_ASSEMBLY_POSE", "n")
        p.set_r1_sensor(rod_pose_locked=True, chassis_stopped=True)
        p.set_r2_sensor(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        p.execute_key("INSERT_ALLOWED", "n")
        p.set_r1_sensor(weapon_locked=True)
        p.set_r2_sensor(insertion_motion_done=True)
        r = p.execute_key("WEAPON_LOCKED", "n")

        assert r.r1_msg_id == 5
        assert r.r2_state == "HEAD_RELEASED"

    def test_clear_mc_leaves(self) -> None:
        """R1_CLEAR_MC should move R2 to READY_TO_LEAVE_MC."""
        p = _setup_pipeline()
        p.execute_key("START", "s")
        p.set_r1_sensor(rod_clamped=True)
        p.execute_key("R1_ROD_CLAMPED", "n")
        p.set_r1_sensor(in_assembly_pose=True)
        p.execute_key("R1_AT_ASSEMBLY_POSE", "n")
        p.set_r1_sensor(rod_pose_locked=True, chassis_stopped=True)
        p.set_r2_sensor(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        p.execute_key("INSERT_ALLOWED", "n")
        p.set_r1_sensor(weapon_locked=True)
        p.set_r2_sensor(insertion_motion_done=True)
        p.execute_key("WEAPON_LOCKED", "n")
        p.set_r1_sensor(r1_clear_mc=True)
        r = p.execute_key("R1_CLEAR_MC", "n")

        assert r.r1_msg_id == 6
        assert r.r2_state == "READY_TO_LEAVE_MC"

    def test_in_mf_enters(self) -> None:
        """R1_IN_MF should move R2 to READY_TO_ENTER_MF."""
        p = _setup_pipeline()
        p.execute_key("START", "s")
        p.set_r1_sensor(rod_clamped=True)
        p.execute_key("R1_ROD_CLAMPED", "n")
        p.set_r1_sensor(in_assembly_pose=True)
        p.execute_key("R1_AT_ASSEMBLY_POSE", "n")
        p.set_r1_sensor(rod_pose_locked=True, chassis_stopped=True)
        p.set_r2_sensor(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
        p.execute_key("INSERT_ALLOWED", "n")
        p.set_r1_sensor(weapon_locked=True)
        p.set_r2_sensor(insertion_motion_done=True)
        p.execute_key("WEAPON_LOCKED", "n")
        p.set_r1_sensor(r1_clear_mc=True)
        p.execute_key("R1_CLEAR_MC", "n")
        p.set_r1_sensor(r1_in_mf=True)
        r = p.execute_key("R1_IN_MF", "n")

        assert r.r1_msg_id == 7
        assert r.r2_state == "READY_TO_ENTER_MF"

    def test_mcu_led_bits_match_beacon_decoder(self) -> None:
        """MCU LED bits must match what the vision decoder sees."""
        p = _setup_pipeline()
        p.execute_key("START", "s")
        p.set_r1_sensor(rod_clamped=True)
        r = p.execute_key("R1_ROD_CLAMPED", "n")

        # MCU LED bits should have REF=1 and correct data bits
        assert r.mcu_led_bits["REF"] == 1
        assert r.mcu_led_bits["D1"] == 1  # msg_id=2, bit 1
        assert r.mcu_led_bits["SEQ"] == 1

    def test_frame_hex_contains_aa55(self) -> None:
        """Every frame hex must contain AA 55 header."""
        p = _setup_pipeline()
        p.execute_key("START", "s")
        p.set_r1_sensor(rod_clamped=True)
        r = p.execute_key("R1_ROD_CLAMPED", "n")

        assert "AA 55" in r.frame_hex

    def test_stable_valid_after_enough_frames(self) -> None:
        """stable_valid should be True after min_stable_frames."""
        p = _setup_pipeline(min_stable_frames=3)
        p.execute_key("START", "s")
        p.set_r1_sensor(rod_clamped=True)
        r = p.execute_key("R1_ROD_CLAMPED", "n")

        assert r.stable_valid is True
        assert r.stable_reason == "stable"

    def test_operator_command_no_msg_id(self) -> None:
        """OperatorCommand from session must not contain msg_id."""
        p = _setup_pipeline()
        cmd = p.session.handle_key("n")
        assert not hasattr(cmd, "msg_id")
        assert not hasattr(cmd, "led_bits")
