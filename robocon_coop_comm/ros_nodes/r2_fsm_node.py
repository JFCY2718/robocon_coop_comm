"""ROS2 node for R2 FSM simulation.

Topics:
  Subscribes:
    /r1/beacon_json       std_msgs/String from r1_fsm_node
    /r2/sensors_json      std_msgs/String, JSON matching R2Sensors fields
  Publishes:
    /r2/status_json       std_msgs/String

In this software-only phase it directly consumes R1 beacon JSON instead of camera images.
After hardware arrives, replace /r1/beacon_json with /r2/decoded_beacon_json from the
camera decoder node.
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

from ..protocol import decode_led_bits
from ..r2_fsm import R2MissionFSM, R2Sensors


class R2FSMNode(Node):
    def __init__(self) -> None:
        super().__init__("r2_fsm_node")
        self.fsm = R2MissionFSM()
        self.sensors = R2Sensors()
        self.pub = self.create_publisher(String, "/r2/status_json", 10)
        self.create_subscription(String, "/r1/beacon_json", self.on_beacon_json, 10)
        self.create_subscription(String, "/r2/sensors_json", self.on_sensors, 10)
        self.get_logger().info("r2_fsm_node started")

    def on_sensors(self, msg: String) -> None:
        try:
            data = json.loads(msg.data)
            for key, value in data.items():
                if hasattr(self.sensors, key):
                    setattr(self.sensors, key, bool(value))
                else:
                    self.get_logger().warn(f"unknown R2 sensor key: {key}")
        except Exception as exc:
            self.get_logger().error(f"bad r2 sensors_json: {exc}")

    def on_beacon_json(self, msg: String) -> None:
        try:
            data = json.loads(msg.data)
            bits = data["bits"]
            decoded = decode_led_bits(bits)
            out = self.fsm.update(decoded, self.sensors)
            payload = {
                "state": self.fsm.state.name,
                "action_hint": out.action_hint,
                "reason": out.reason,
                "decoded": {
                    "msg_id": decoded.msg_id,
                    "msg_name": decoded.msg_name,
                    "seq": decoded.seq,
                    "valid": decoded.valid,
                },
                "sensors": asdict(self.sensors),
            }
            ros_msg = String()
            ros_msg.data = json.dumps(payload, ensure_ascii=False)
            self.pub.publish(ros_msg)
        except Exception as exc:
            self.get_logger().error(f"bad beacon_json: {exc}")


def main() -> None:
    if rclpy is None:
        raise RuntimeError("ROS2 rclpy is not available. Source ROS2 or run non-ROS demos.")
    rclpy.init()
    node = R2FSMNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
