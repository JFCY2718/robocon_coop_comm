"""OpenCV virtual beacon demo.

Keyboard:
  n: R1 NEXT
  s: START
  h: HOLD
  r: RESET
  1: rod_clamped
  2: in_assembly_pose
  3: rod_pose_locked + chassis_stopped
  4: weapon_locked
  5: r1_clear_mc
  6: r1_in_mf
  q: quit
"""

from __future__ import annotations

from .beacon_image import cv2, decode_virtual_beacon_image, draw_virtual_beacon, require_vision
from .protocol import msg_id_to_name
from .r1_fsm import OperatorCommand, R1MissionFSM, R1Sensors


def main() -> None:
    require_vision()
    r1 = R1MissionFSM()
    sensors = R1Sensors()

    while True:
        img = draw_virtual_beacon(int(r1.msg_id), r1.seq)
        decoded, confidence = decode_virtual_beacon_image(img)

        lines = [
            "Keys: s=start n=next h=hold r=reset 1=rod 2=pose 3=lock 4=weapon 5=clear 6=mf q=quit",
            f"R1 state={r1.state.name} msg={int(r1.msg_id)}:{msg_id_to_name(r1.msg_id)} seq={r1.seq}",
            f"R2 decode valid={decoded.valid} msg={decoded.msg_id}:{decoded.msg_name} seq={decoded.seq} conf={confidence:.2f}",
        ]
        for i, text in enumerate(lines):
            cv2.putText(img, text, (18, 24 + i * 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1)

        cv2.imshow("ROBOCON Virtual R1 Beacon", img)
        key = cv2.waitKey(50) & 0xFF
        if key == ord("q"):
            break
        if key == ord("s"):
            r1.update(OperatorCommand.START, sensors)
        elif key == ord("n"):
            r1.update(OperatorCommand.NEXT, sensors)
        elif key == ord("h"):
            r1.update(OperatorCommand.HOLD, sensors)
        elif key == ord("r"):
            r1.reset()
            sensors = R1Sensors()
        elif key == ord("1"):
            sensors.rod_clamped = True
        elif key == ord("2"):
            sensors.in_assembly_pose = True
        elif key == ord("3"):
            sensors.rod_pose_locked = True
            sensors.chassis_stopped = True
        elif key == ord("4"):
            sensors.weapon_locked = True
        elif key == ord("5"):
            sensors.r1_clear_mc = True
        elif key == ord("6"):
            sensors.r1_in_mf = True

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
