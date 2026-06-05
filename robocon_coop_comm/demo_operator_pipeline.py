"""Demo: Keyboard -> OperatorSession -> OperatorCommand -> R1 FSM -> LED MCU pipeline.

Software-only simulation.  No real hardware, no OpenCV, no ROS.

Shows that operator input ONLY requests R1 state changes, never
directly controls R2 or LEDs.
"""

from __future__ import annotations

from .led_mcu_client import LedMcuClient
from .led_mcu_simulator import LedMcuSimulator, LedMcuUpdate
from .operator_command import request_to_r1_command
from .operator_session import OperatorSession
from .protocol import msg_id_to_name
from .r1_fsm import OperatorCommand as R1OperatorCommand, R1MissionFSM, R1Sensors
from .serial_transport import MemorySerialTransport


_R1_CMD_MAP: dict[str, R1OperatorCommand] = {
    "start": R1OperatorCommand.START,
    "next": R1OperatorCommand.NEXT,
    "hold": R1OperatorCommand.HOLD,
    "abort": R1OperatorCommand.ABORT,
    "reset": R1OperatorCommand.RESET,
}


def _process(
    label: str,
    key: str,
    session: OperatorSession,
    r1: R1MissionFSM,
    sensors: R1Sensors,
    client: LedMcuClient,
    transport: MemorySerialTransport,
    sim: LedMcuSimulator,
) -> None:
    """Process one key through the full pipeline."""
    cmd = session.handle_key(key)
    r1_cmd_str = request_to_r1_command(cmd)
    r1_cmd = _R1_CMD_MAP.get(r1_cmd_str, R1OperatorCommand.NONE)

    r1.update(r1_cmd, sensors)
    frame = client.send(int(r1.msg_id), r1.seq)

    mcu_results = sim.feed(transport.get_written_data())
    transport.clear_written_data()

    for result in mcu_results:
        if isinstance(result, LedMcuUpdate):
            hex_str = " ".join(f"{b:02X}" for b in frame)
            led_str = " ".join(f"{k}={v}" for k, v in result.led_bits.items())
            print(f"[{label}] key='{key}'")
            print(f"  OperatorCommand : mode={cmd.mode.name} request={cmd.request.name}")
            print(f"  R1 command      : {r1_cmd_str}")
            print(f"  R1 state        : {r1.state.name}")
            print(f"  msg_id          : {int(r1.msg_id):02d} ({msg_id_to_name(r1.msg_id)})")
            print(f"  frame hex       : {hex_str}")
            print(f"  MCU LED bits    : {led_str}")
            print()
        else:
            print(f"[{label}] MCU ERROR: {result.reason}")


def _set_sensor(label: str) -> None:
    print(f"  [sensor] {label}")


def main() -> None:
    session = OperatorSession()
    r1 = R1MissionFSM()
    sensors = R1Sensors()
    transport = MemorySerialTransport()
    client = LedMcuClient(transport)
    sim = LedMcuSimulator()

    print("=" * 60)
    print("Operator Input -> R1 FSM -> LED MCU Pipeline")
    print("=" * 60)
    print()

    # Start
    _process("START", "s", session, r1, sensors, client, transport, sim)

    # Rod clamped
    sensors.rod_clamped = True
    _set_sensor("rod_clamped = True")
    _process("ROD_CLAMPED", "n", session, r1, sensors, client, transport, sim)

    # At assembly pose
    sensors.in_assembly_pose = True
    _set_sensor("in_assembly_pose = True")
    _process("AT_ASSEMBLY_POSE", "n", session, r1, sensors, client, transport, sim)

    # Insert allowed
    sensors.rod_pose_locked = True
    sensors.chassis_stopped = True
    _set_sensor("rod_pose_locked = True, chassis_stopped = True")
    _process("INSERT_ALLOWED", "n", session, r1, sensors, client, transport, sim)

    # Weapon locked
    sensors.weapon_locked = True
    _set_sensor("weapon_locked = True")
    _process("WEAPON_LOCKED", "n", session, r1, sensors, client, transport, sim)

    # R1 clear MC
    sensors.r1_clear_mc = True
    _set_sensor("r1_clear_mc = True")
    _process("R1_CLEAR_MC", "n", session, r1, sensors, client, transport, sim)

    # R1 in MF
    sensors.r1_in_mf = True
    _set_sensor("r1_in_mf = True")
    _process("R1_IN_MF", "n", session, r1, sensors, client, transport, sim)

    print("=" * 60)
    print("Operator pipeline simulation complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
