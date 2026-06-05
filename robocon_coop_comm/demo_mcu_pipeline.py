"""Demo: R1 FSM -> LedMcuClient -> MemorySerialTransport -> LedMcuSimulator -> LED bits.

This is a software-only simulation of the R1 main controller -> LED MCU pipeline.
No real hardware, no OpenCV, no ROS required.

This is R1 internal wired communication, NOT R1/R2 communication.
"""

from __future__ import annotations

from .led_mcu_client import LedMcuClient
from .led_mcu_simulator import LedMcuSimulator, LedMcuUpdate
from .protocol import msg_id_to_name
from .r1_fsm import OperatorCommand, R1MissionFSM, R1Sensors
from .serial_transport import MemorySerialTransport


def _step(
    label: str,
    r1: R1MissionFSM,
    sensors: R1Sensors,
    client: LedMcuClient,
    transport: MemorySerialTransport,
    sim: LedMcuSimulator,
    command: OperatorCommand = OperatorCommand.NEXT,
) -> None:
    """Advance R1 FSM, send frame, simulate MCU, print result."""
    r1.update(command, sensors)

    # Only send if msg_id actually changed (same logic as real hardware)
    frame = client.send(int(r1.msg_id), r1.seq)

    # Feed into MCU simulator
    mcu_results = sim.feed(transport.get_written_data())
    transport.clear_written_data()

    for result in mcu_results:
        if isinstance(result, LedMcuUpdate):
            hex_str = " ".join(f"{b:02X}" for b in frame)
            led_str = " ".join(
                f"{k}={v}" for k, v in result.led_bits.items()
            )
            print(f"[{label}]")
            print(f"  R1 state   : {r1.state.name}")
            print(f"  msg_id     : {int(r1.msg_id):02d} ({msg_id_to_name(r1.msg_id)})")
            print(f"  seq        : {r1.seq}")
            print(f"  frame hex  : {hex_str}")
            print(f"  MCU ack    : {result.ack}")
            print(f"  LED bits   : {led_str}")
            print()
        else:
            print(f"[{label}] MCU ERROR: {result.reason}")


def main() -> None:
    r1 = R1MissionFSM()
    sensors = R1Sensors()
    transport = MemorySerialTransport()
    client = LedMcuClient(transport)
    sim = LedMcuSimulator()

    print("=" * 60)
    print("R1 -> LED MCU Pipeline Simulation")
    print("=" * 60)
    print()

    # Start
    _step("START", r1, sensors, client, transport, sim, OperatorCommand.START)

    # Rod clamped
    sensors.rod_clamped = True
    _step("ROD_CLAMPED", r1, sensors, client, transport, sim)

    # At assembly pose
    sensors.in_assembly_pose = True
    _step("AT_ASSEMBLY_POSE", r1, sensors, client, transport, sim)

    # Insert allowed (need rod_pose_locked + chassis_stopped)
    sensors.rod_pose_locked = True
    sensors.chassis_stopped = True
    _step("INSERT_ALLOWED", r1, sensors, client, transport, sim)

    # Weapon locked
    sensors.weapon_locked = True
    _step("WEAPON_LOCKED", r1, sensors, client, transport, sim)

    # R1 clear MC
    sensors.r1_clear_mc = True
    _step("R1_CLEAR_MC", r1, sensors, client, transport, sim)

    # R1 in MF
    sensors.r1_in_mf = True
    _step("R1_IN_MF", r1, sensors, client, transport, sim)

    print("=" * 60)
    print("Pipeline simulation complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
