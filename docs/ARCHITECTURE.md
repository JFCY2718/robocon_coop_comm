# 系统架构

## 1. 无硬件阶段

```text
键盘/虚拟遥控器
  -> R1MissionFSM
  -> protocol.encode_led_bits
  -> 虚拟信标图像 / 直接 bits
  -> protocol.decode_led_bits
  -> R2MissionFSM
```

## 2. 有硬件阶段

```text
遥控器接收机 / joy_node
  -> r1_operator_interface
  -> r1_mission_fsm
  -> r1_beacon_driver
  -> MCU
  -> LED 光码板 + AprilTag
  -> R2 摄像头
  -> AprilTag 检测 + LED ROI 解码
  -> r2_mission_fsm
```

## 3. 模块边界

| 模块 | 当前实现 | 后续替换 |
|---|---|---|
| R1 状态机 | `r1_fsm.py` | 保持不变，增加更多状态 |
| 协议 | `protocol.py` | 保持兼容 |
| 信标显示 | `beacon_image.py` 虚拟图像 | MCU + LED 光码板 |
| R2 解码 | 固定 ROI 读取 | AprilTag 透视矫正 + LED 读取 |
| R2 状态机 | `r2_fsm.py` | 增加运动/抓取/放置动作接口 |

## 4. ROS2 设计

第一版 ROS2 节点使用 `std_msgs/String` + JSON，避免早期频繁修改自定义消息。协议稳定后再换成自定义 msg。

- `/r1/operator_command`: `String`, values: `start,next,hold,reset,abort`
- `/r1/sensors_json`: `String`, JSON of `R1Sensors`
- `/r1/beacon_json`: `String`, encoded beacon JSON
- `/r2/sensors_json`: `String`, JSON of `R2Sensors`
- `/r2/status_json`: `String`, R2 state/action JSON
