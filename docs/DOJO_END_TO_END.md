# Dojo End-to-End Pipeline

## 目的

在没有真实硬件时，验证武馆阶段 R1/R2 协作通信完整闭环。

## 链路图

```
OperatorSession
  ↓
OperatorCommand
  ↓
R1 FSM
  ↓
LedMcuClient
  ↓
LedMcuSimulator
  ↓
LED bits
  ↓
VirtualBeaconFrameProvider
  ↓
BeaconDecoder
  ↓
BeaconStabilizer
  ↓
R2 FSM
```

## 说明

- `OperatorCommand` 不直接控制 R2，不直接控制 LED；
- R1 FSM 输出 `msg_id`；
- R2 视觉解码 `msg_id`；
- R2 结合本地传感器和状态机决定动作。

## 武馆阶段流程

| 步骤 | R1 msg_id | R2 预期状态 |
|------|-----------|-------------|
| R1_ROD_CLAMPED | 2 | PREPARE_HEAD |
| R1_AT_ASSEMBLY_POSE | 3 | SEARCH_R1_TAG |
| INSERT_ALLOWED | 4 | INSERTING |
| WEAPON_LOCKED | 5 | HEAD_RELEASED |
| R1_CLEAR_MC | 6 | READY_TO_LEAVE_MC |
| R1_IN_MF | 7 | READY_TO_ENTER_MF |

## 运行命令

```bash
python -m robocon_coop_comm.demo_dojo_end_to_end
./tools/demo_dojo_end_to_end_check.sh
make demo-dojo-check
```

## 验收关键输出

- `AA 55` (串口帧)
- `REF`, `PAR` (LED bits)
- `stable` (视觉稳定判定)
- `R2 state`, `action_hint` (R2 FSM)

## 安全说明

- 这**不是** R1/R2 无线通信；
- 这**不是**武馆组装阶段接触式通信；
- 这是光学事件通信的软件闭环模拟。

## 后续硬件替换

| 软件组件 | 替换为 |
|----------|--------|
| `MemorySerialTransport` | `PySerialTransport` |
| `LedMcuSimulator` | 真实 LED MCU 固件 |
| `VirtualBeaconFrameProvider` | `UsbCameraFrameProvider` + AprilTag ROI |
| 虚拟 LED 图像 | 真实 LED 光码板 |
