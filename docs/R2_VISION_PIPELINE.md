# R2 Vision Pipeline

## 目的

在没有真实摄像头时，验证 R2 端视觉解码和状态机链路。

## 链路图

```
VirtualBeaconFrameProvider (虚拟信标图像)
  ↓
BeaconDecoder (图像 -> LED bits -> DecodedBeacon)
  ↓
BeaconStabilizer (连续 N 帧一致才接受)
  ↓
DecodedBeacon (msg_id, seq, valid, confidence)
  ↓
R2 FSM (结合本地传感器决策)
```

## 说明

- 当前使用虚拟信标图像（`beacon_image.draw_virtual_beacon`）；
- 后续真实摄像头只替换 `FrameProvider`；
- 后续 AprilTag 定位只替换 ROI 定位部分；
- R2 FSM 不应因为图像来源变化而改变。

## 稳定判定

`BeaconStabilizer` 默认要求连续 3 帧相同 `msg_id` 和 `seq` 才输出 `valid=True`。
这模拟了真实视觉中的噪声过滤。

## 安全说明

- 这是**视觉事件解码**，不是无线通信；
- R2 看到 `msg_id` 后仍必须根据自身传感器和状态机决定动作；
- `msg_id` 不能被理解成遥控器直接控制 R2 的命令。

## 运行命令

```bash
python -m robocon_coop_comm.demo_r2_vision_pipeline
./tools/demo_r2_vision_pipeline_check.sh
make demo-r2-vision-check
```

## 预期输出

输出应包含：
- `R1_ROD_CLAMPED`, `R1_AT_ASSEMBLY_POSE`, `INSERT_ALLOWED`, `WEAPON_LOCKED`, `R1_CLEAR_MC`, `R1_IN_MF`
- `stable` (稳定判定结果)
- `R2 state`, `action_hint` (R2 FSM 状态和动作提示)

## 后续硬件替换

| 软件组件 | 替换为 |
|----------|--------|
| `VirtualBeaconFrameProvider` | 真实 USB 摄像头 FrameProvider |
| 固定 ROI 解码 | AprilTag 检测 + 透视变换 + LED ROI 采样 |
| `BeaconStabilizer` | 保持不变 |
| `R2 FSM` | 保持不变 |
