"""Dojo end-to-end pipeline: OperatorSession -> R1 FSM -> LED MCU -> Vision -> R2 FSM.

Encapsulates the full dojo assembly phase communication loop in software.
No real hardware, no real camera, no real MCU required.

This is NOT R1/R2 wireless communication.
This is optical event communication simulation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .beacon_decoder import BeaconDecoder
from .beacon_frame_provider import VirtualBeaconFrameProvider
from .beacon_stabilizer import BeaconStabilizer
from .beacon_types import DecodedBeacon, msg_name_from_id
from .led_mcu_client import LedMcuClient
from .led_mcu_simulator import LedMcuSimulator, LedMcuUpdate
from .operator_command import request_to_r1_command
from .operator_session import OperatorSession
from .protocol import DecodedBeacon as ProtocolDecodedBeacon
from .r1_fsm import OperatorCommand as R1OperatorCommand
from .r1_fsm import R1MissionFSM, R1Sensors
from .r2_fsm import R2MissionFSM, R2Sensors
from .serial_transport import MemorySerialTransport

_R1_CMD_MAP: dict[str, R1OperatorCommand] = {
    "start": R1OperatorCommand.START,
    "next": R1OperatorCommand.NEXT,
    "hold": R1OperatorCommand.HOLD,
    "abort": R1OperatorCommand.ABORT,
    "reset": R1OperatorCommand.RESET,
}


@dataclass
class DojoStepResult:
    """Result of one step in the dojo end-to-end pipeline."""

    label: str
    operator_key: str | None = None
    sensor_event: str | None = None
    r1_state: str = ""
    r1_msg_id: int = 0
    r1_msg_name: str = ""
    seq: int = 0
    frame_hex: str = ""
    mcu_led_bits: dict[str, int] = field(default_factory=dict)
    decoded_msg_id: int = 0
    decoded_msg_name: str = ""
    decoded_valid: bool = False
    stable_valid: bool = False
    stable_reason: str = ""
    r2_state: str = ""
    r2_action_hint: str = ""


class DojoEndToEndPipeline:
    """Full dojo communication pipeline.

    Holds all pipeline stages and provides methods to execute
    operator key presses and sensor events.
    """

    def __init__(self, min_stable_frames: int = 3) -> None:
        self.session = OperatorSession()
        self.r1 = R1MissionFSM()
        self.r1_sensors = R1Sensors()
        self.transport = MemorySerialTransport()
        self.client = LedMcuClient(self.transport)
        self.mcu_sim = LedMcuSimulator()
        self.provider = VirtualBeaconFrameProvider()
        self.decoder = BeaconDecoder()
        self.stabilizer = BeaconStabilizer(min_stable_frames=min_stable_frames)
        self.r2 = R2MissionFSM()
        self.r2_sensors = R2Sensors()

    def _run_pipeline(self, label: str, key: str | None, sensor: str | None) -> DojoStepResult:
        """Run the vision pipeline on the current R1 msg_id/seq and feed R2 FSM."""
        msg_id = int(self.r1.msg_id)
        seq = self.r1.seq

        # 1. Encode and send via MCU
        frame = self.client.send(msg_id, seq)
        frame_hex = " ".join(f"{b:02X}" for b in frame)

        # 2. MCU simulator
        mcu_results = self.mcu_sim.feed(self.transport.get_written_data())
        self.transport.clear_written_data()
        mcu_led_bits: dict[str, int] = {}
        for r in mcu_results:
            if isinstance(r, LedMcuUpdate):
                mcu_led_bits = r.led_bits

        # 3. Generate virtual beacon image and decode through vision pipeline
        self.provider.update(msg_id, seq)
        last_decoded: DecodedBeacon | None = None
        for _ in range(self.stabilizer.min_stable_frames):
            beacon_frame = self.provider.get_frame()
            decoded = self.decoder.decode(beacon_frame)
            last_decoded = self.stabilizer.update(decoded)

        # 4. Feed to R2 FSM
        r2_action = ""
        r2_state = self.r2.state.name
        if last_decoded is not None and last_decoded.valid:
            protocol_beacon = ProtocolDecodedBeacon(
                msg_id=last_decoded.msg_id,
                seq=last_decoded.seq,
                valid=last_decoded.valid,
                bits=last_decoded.raw_bits or {},
            )
            r2_out = self.r2.update(protocol_beacon, self.r2_sensors)
            r2_state = self.r2.state.name
            r2_action = r2_out.action_hint

        return DojoStepResult(
            label=label,
            operator_key=key,
            sensor_event=sensor,
            r1_state=self.r1.state.name,
            r1_msg_id=msg_id,
            r1_msg_name=msg_name_from_id(msg_id),
            seq=seq,
            frame_hex=frame_hex,
            mcu_led_bits=mcu_led_bits,
            decoded_msg_id=last_decoded.msg_id if last_decoded else 0,
            decoded_msg_name=last_decoded.msg_name if last_decoded else "",
            decoded_valid=last_decoded.valid if last_decoded else False,
            stable_valid=last_decoded.valid if last_decoded else False,
            stable_reason=last_decoded.reason if last_decoded else "",
            r2_state=r2_state,
            r2_action_hint=r2_action,
        )

    def execute_key(self, label: str, key: str) -> DojoStepResult:
        """Execute an operator key press through the full pipeline."""
        cmd = self.session.handle_key(key)
        r1_cmd_str = request_to_r1_command(cmd)
        r1_cmd = _R1_CMD_MAP.get(r1_cmd_str, R1OperatorCommand.NONE)
        self.r1.update(r1_cmd, self.r1_sensors)
        return self._run_pipeline(label, key=key, sensor=None)

    def set_r1_sensor(self, **kwargs: bool) -> None:
        """Set R1 sensor values."""
        for k, v in kwargs.items():
            setattr(self.r1_sensors, k, v)

    def set_r2_sensor(self, **kwargs: bool) -> None:
        """Set R2 sensor values."""
        for k, v in kwargs.items():
            setattr(self.r2_sensors, k, v)
