"""ROS2 node for R1 FSM.

Topics:
  Subscribes:
    /r1/operator_command  std_msgs/String, values: start,next,hold,reset,abort
    /r1/sensors_json      std_msgs/String, JSON matching R1Sensors fields
  Publishes:
    /r1/beacon_json       std_msgs/String, JSON with msg_id, msg_name, seq, bits, state

This intentionally uses std_msgs/String JSON in the first prototype to avoid custom message
build friction. Replace with custom messages after the protocol stabilizes.
"""

from __future__ import annotations

import json
from dataclasses import asdict

try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String
except Exception:  # pragma: no cover
    rclpy = None
    Node = object
    String = None

from ..protocol import encode_led_bits, msg_id_to_name
from ..r1_fsm import OperatorCommand, R1MissionFSM, R1Sensors

COMMAND_MAP = {
    "none": OperatorCommand.NONE,
    "start": OperatorCommand.START,
    "next": OperatorCommand.NEXT,
    "hold": OperatorCommand.HOLD,
    "reset": OperatorCommand.RESET,
    "abort": OperatorCommand.ABORT,
}


class R1FSMNode(Node):
    def __init__(self) -> None:
        super().__init__("r1_fsm_node")
        self.fsm = R1MissionFSM()
        self.sensors = R1Sensors()
        self.pub = self.create_publisher(String, "/r1/beacon_json", 10)
        self.create_subscription(String, "/r1/operator_command", self.on_command, 10)
        self.create_subscription(String, "/r1/sensors_json", self.on_sensors, 10)
        self.timer = self.create_timer(0.1, self.publish_current)
        self.get_logger().info("r1_fsm_node started")

    def on_command(self, msg: String) -> None:
        raw = msg.data.strip().lower()
        cmd = COMMAND_MAP.get(raw)
        if cmd is None:
            self.get_logger().warn(f"unknown operator command: {raw}")
            return
        out = self.fsm.update(cmd, self.sensors)
        self.get_logger().info(f"R1 transition: {out.reason} -> {out.state.name} msg={out.msg_id.name}")
        self.publish_current()

    def on_sensors(self, msg: String) -> None:
        try:
            data = json.loads(msg.data)
            for key, value in data.items():
                if hasattr(self.sensors, key):
                    setattr(self.sensors, key, bool(value))
                else:
                    self.get_logger().warn(f"unknown R1 sensor key: {key}")
        except Exception as exc:
            self.get_logger().error(f"bad sensors_json: {exc}")

    def publish_current(self) -> None:
        encoded = encode_led_bits(self.fsm.msg_id, self.fsm.seq)
        payload = {
            "state": self.fsm.state.name,
            "msg_id": int(self.fsm.msg_id),
            "msg_name": msg_id_to_name(int(self.fsm.msg_id)),
            "seq": self.fsm.seq,
            "bits": encoded.bits,
            "sensors": asdict(self.sensors),
        }
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self.pub.publish(msg)


def main() -> None:
    if rclpy is None:
        raise RuntimeError("ROS2 rclpy is not available. Source ROS2 or run non-ROS demos.")
    rclpy.init()
    node = R1FSMNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
