"""Text-only software loop demo.

No hardware, no ROS, no OpenCV required.
"""

from __future__ import annotations

from .protocol import decode_led_bits, encode_led_bits, msg_id_to_name
from .r1_fsm import OperatorCommand, R1MissionFSM, R1Sensors
from .r2_fsm import R2MissionFSM, R2Sensors

HELP = """
Commands:
  start  : R1 start
  next   : request next guarded R1 state
  hold   : R1 hold
  reset  : reset R1 and R2
  abort  : abort current task

Sensor toggles:
  rod    : set R1 rod_clamped=true
  pose   : set R1 in_assembly_pose=true
  lock   : set R1 rod_pose_locked=true and chassis_stopped=true
  weapon : set R1 weapon_locked=true and R2 insertion_motion_done=true
  clear  : set R1 r1_clear_mc=true
  mf     : set R1 r1_in_mf=true

R2 local sensors:
  head   : set R2 head_grabbed=true
  tag    : set R2 r1_tag_visible=true
  pre    : set R2 pre_insert_pose_ok=true

Other:
  status : print sensors
  help   : show this help
  q      : quit
"""


def print_status(r1: R1MissionFSM, r1s: R1Sensors, r2: R2MissionFSM, r2s: R2Sensors) -> None:
    encoded = encode_led_bits(r1.msg_id, r1.seq)
    decoded = decode_led_bits(encoded.bits)
    r2_out = r2.update(decoded, r2s)
    print("-" * 72)
    print(f"R1 state={r1.state.name:22s} msg={int(r1.msg_id):02d}:{msg_id_to_name(r1.msg_id)} seq={r1.seq}")
    print("LED bits:", " ".join(f"{k}={v}" for k, v in encoded.bits.items()))
    print(f"R2 decoded valid={decoded.valid} msg={decoded.msg_id:02d}:{decoded.msg_name} seq={decoded.seq}")
    print(f"R2 state={r2.state.name:22s} action_hint={r2_out.action_hint} reason={r2_out.reason}")
    print(f"R1 sensors={r1s}")
    print(f"R2 sensors={r2s}")


def main() -> None:
    r1 = R1MissionFSM()
    r2 = R2MissionFSM()
    r1s = R1Sensors()
    r2s = R2Sensors()

    print(HELP)
    print_status(r1, r1s, r2, r2s)

    while True:
        cmd = input("robocon> ").strip().lower()
        if cmd in {"q", "quit", "exit"}:
            break
        if cmd == "help":
            print(HELP)
            continue
        if cmd == "status":
            print_status(r1, r1s, r2, r2s)
            continue

        if cmd == "reset":
            r1.reset()
            r2.reset()
            r1s = R1Sensors()
            r2s = R2Sensors()
        elif cmd == "start":
            r1.update(OperatorCommand.START, r1s)
        elif cmd == "next":
            r1.update(OperatorCommand.NEXT, r1s)
        elif cmd == "hold":
            r1.update(OperatorCommand.HOLD, r1s)
        elif cmd == "abort":
            r1.update(OperatorCommand.ABORT, r1s)
        elif cmd == "rod":
            r1s.rod_clamped = True
        elif cmd == "pose":
            r1s.in_assembly_pose = True
        elif cmd == "lock":
            r1s.rod_pose_locked = True
            r1s.chassis_stopped = True
        elif cmd == "weapon":
            r1s.weapon_locked = True
            r2s.insertion_motion_done = True
        elif cmd == "clear":
            r1s.r1_clear_mc = True
        elif cmd == "mf":
            r1s.r1_in_mf = True
        elif cmd == "head":
            r2s.head_grabbed = True
        elif cmd == "tag":
            r2s.r1_tag_visible = True
        elif cmd == "pre":
            r2s.pre_insert_pose_ok = True
        else:
            print(f"unknown command: {cmd}")

        print_status(r1, r1s, r2, r2s)


if __name__ == "__main__":
    main()
