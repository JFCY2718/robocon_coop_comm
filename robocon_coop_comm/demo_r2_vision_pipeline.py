"""Demo: R1 msg_id -> VirtualBeaconFrameProvider -> BeaconDecoder -> BeaconStabilizer -> R2 FSM.

Software-only simulation.  No real hardware, no real camera, no AprilTag.

Shows the full R2 vision pipeline from virtual beacon image to R2 FSM state transitions.
"""

from __future__ import annotations

from .beacon_decoder import BeaconDecoder
from .beacon_frame_provider import VirtualBeaconFrameProvider
from .beacon_stabilizer import BeaconStabilizer
from .protocol import MsgID
from .r2_fsm import R2MissionFSM, R2Sensors


def _send_and_stabilize(
    label: str,
    msg_id: int,
    seq: int,
    provider: VirtualBeaconFrameProvider,
    decoder: BeaconDecoder,
    stabilizer: BeaconStabilizer,
    r2: R2MissionFSM,
    sensors: R2Sensors,
    num_frames: int = 4,
) -> None:
    """Send msg_id through the vision pipeline with multiple frames."""
    provider.update(msg_id, seq)

    last_stable = None
    for i in range(num_frames):
        frame = provider.get_frame()
        raw_decoded = decoder.decode(frame)
        stable_decoded = stabilizer.update(raw_decoded)

        if i == 0:
            print(f"[{label}] msg_id={msg_id} ({raw_decoded.msg_name}) seq={seq}")
            print(
                f"  frame {frame.frame_id}: raw valid={raw_decoded.valid} "
                f"conf={raw_decoded.confidence:.2f} -> "
                f"stable valid={stable_decoded.valid} reason={stable_decoded.reason}"
            )

        last_stable = stable_decoded

    # Feed stable result to R2 FSM
    if last_stable is not None and last_stable.valid:
        from .protocol import DecodedBeacon as ProtocolDecodedBeacon

        protocol_beacon = ProtocolDecodedBeacon(
            msg_id=last_stable.msg_id,
            seq=last_stable.seq,
            valid=last_stable.valid,
            bits=last_stable.raw_bits or {},
        )
        r2_out = r2.update(protocol_beacon, sensors)
        print(f"  R2 state  : {r2.state.name}")
        print(f"  action_hint: {r2_out.action_hint}")
        print(f"  reason     : {r2_out.reason}")
    elif last_stable is not None:
        print(f"  R2: not fed (stable valid={last_stable.valid})")
    print()


def main() -> None:
    provider = VirtualBeaconFrameProvider()
    decoder = BeaconDecoder()
    stabilizer = BeaconStabilizer(min_stable_frames=3)
    r2 = R2MissionFSM()
    sensors = R2Sensors()

    print("=" * 60)
    print("R2 Vision Pipeline: Virtual Beacon -> R2 FSM")
    print("=" * 60)
    print()

    # R1_ROD_CLAMPED
    _send_and_stabilize(
        "R1_ROD_CLAMPED", MsgID.R1_ROD_CLAMPED, 1,
        provider, decoder, stabilizer, r2, sensors,
    )

    # R1_AT_ASSEMBLY_POSE
    _send_and_stabilize(
        "R1_AT_ASSEMBLY_POSE", MsgID.R1_AT_ASSEMBLY_POSE, 0,
        provider, decoder, stabilizer, r2, sensors,
    )

    # INSERT_ALLOWED - set R2 local sensors for insertion
    sensors.head_grabbed = True
    sensors.r1_tag_visible = True
    sensors.pre_insert_pose_ok = True
    _send_and_stabilize(
        "INSERT_ALLOWED", MsgID.INSERT_ALLOWED, 1,
        provider, decoder, stabilizer, r2, sensors,
    )

    # WEAPON_LOCKED
    sensors.insertion_motion_done = True
    _send_and_stabilize(
        "WEAPON_LOCKED", MsgID.WEAPON_LOCKED, 0,
        provider, decoder, stabilizer, r2, sensors,
    )

    # R1_CLEAR_MC
    _send_and_stabilize(
        "R1_CLEAR_MC", MsgID.R1_CLEAR_MC, 1,
        provider, decoder, stabilizer, r2, sensors,
    )

    # R1_IN_MF
    _send_and_stabilize(
        "R1_IN_MF", MsgID.R1_IN_MF, 0,
        provider, decoder, stabilizer, r2, sensors,
    )

    print("=" * 60)
    print("R2 vision pipeline simulation complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
