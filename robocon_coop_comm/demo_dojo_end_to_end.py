"""Demo: Full dojo end-to-end communication pipeline.

OperatorSession -> R1 FSM -> LedMcuClient -> LedMcuSimulator -> LED bits
    -> VirtualBeaconFrameProvider -> BeaconDecoder -> BeaconStabilizer -> R2 FSM

Software-only simulation.  No real hardware, no real camera, no real MCU.
"""

from __future__ import annotations

from .dojo_end_to_end import DojoEndToEndPipeline, DojoStepResult


def _print_step(r: DojoStepResult) -> None:
    led_str = " ".join(f"{k}={v}" for k, v in r.mcu_led_bits.items())
    print(f"[{r.label}]")
    if r.operator_key:
        print(f"  OperatorCommand: key='{r.operator_key}'")
    if r.sensor_event:
        print(f"  sensor event   : {r.sensor_event}")
    print(f"  R1 state       : {r.r1_state}")
    print(f"  R1 msg_id      : {r.r1_msg_id:02d} ({r.r1_msg_name})")
    print(f"  seq            : {r.seq}")
    print(f"  frame hex      : {r.frame_hex}")
    print(f"  MCU LED bits   : {led_str}")
    print(f"  decoded        : msg={r.decoded_msg_id:02d} ({r.decoded_msg_name}) valid={r.decoded_valid}")
    print(f"  stable         : valid={r.stable_valid} reason={r.stable_reason}")
    print(f"  R2 state       : {r.r2_state}")
    print(f"  action_hint    : {r.r2_action_hint}")
    print()


def main() -> None:
    p = DojoEndToEndPipeline()

    print("=" * 60)
    print("Dojo End-to-End Communication Pipeline")
    print("=" * 60)
    print()

    # 1. Operator presses START
    _print_step(p.execute_key("START", "s"))

    # 2. R1 sensor: rod clamped
    p.set_r1_sensor(rod_clamped=True)
    print("  [sensor] R1 rod_clamped = True")

    # 3. Operator presses NEXT -> R1_ROD_CLAMPED
    _print_step(p.execute_key("R1_ROD_CLAMPED", "n"))

    # 4. R1 sensor: at assembly pose
    p.set_r1_sensor(in_assembly_pose=True)
    print("  [sensor] R1 in_assembly_pose = True")

    # 5. Operator presses NEXT -> R1_AT_ASSEMBLY_POSE
    _print_step(p.execute_key("R1_AT_ASSEMBLY_POSE", "n"))

    # 6. R1 sensors: pose locked + chassis stopped
    p.set_r1_sensor(rod_pose_locked=True, chassis_stopped=True)
    print("  [sensor] R1 rod_pose_locked=True, chassis_stopped=True")

    # 7. R2 local sensors: ready for insertion
    p.set_r2_sensor(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
    print("  [sensor] R2 head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True")

    # 8. Operator presses NEXT -> INSERT_ALLOWED
    _print_step(p.execute_key("INSERT_ALLOWED", "n"))

    # 9. R1 + R2 sensors: weapon locked, insertion done
    p.set_r1_sensor(weapon_locked=True)
    p.set_r2_sensor(insertion_motion_done=True)
    print("  [sensor] R1 weapon_locked=True, R2 insertion_motion_done=True")

    # 10. Operator presses NEXT -> WEAPON_LOCKED
    _print_step(p.execute_key("WEAPON_LOCKED", "n"))

    # 11. R1 sensor: clear MC
    p.set_r1_sensor(r1_clear_mc=True)
    print("  [sensor] R1 r1_clear_mc=True")

    # 12. Operator presses NEXT -> R1_CLEAR_MC
    _print_step(p.execute_key("R1_CLEAR_MC", "n"))

    # 13. R1 sensor: in MF
    p.set_r1_sensor(r1_in_mf=True)
    print("  [sensor] R1 r1_in_mf=True")

    # 14. Operator presses NEXT -> R1_IN_MF
    _print_step(p.execute_key("R1_IN_MF", "n"))

    print("=" * 60)
    print("Dojo end-to-end pipeline complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
