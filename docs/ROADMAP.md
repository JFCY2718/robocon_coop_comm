# 开发路线图

## M0：纯软件闭环

验收：

```bash
pytest -q
python -m robocon_coop_comm.demo_cli
```

目标：

- 协议 0~31 round-trip 正确。
- R1 状态机可以拦截危险状态。
- R2 只有本地条件满足才响应 `INSERT_ALLOWED`。

## M1：虚拟信标图像

验收：

```bash
pip install -e ".[vision]"
python -m robocon_coop_comm.demo_cv
```

目标：

- OpenCV 窗口能显示虚拟 AprilTag + LED 光码板。
- 固定 ROI 解码正确。

## M2：真实 LED 光码板

硬件：

- 8 颗高亮白光/绿光 LED。
- MCU：Pico / STM32 / Arduino Nano。
- 串口协议：`AA 55 msg_id seq brightness checksum`。

目标：

- R1 主控发送 `msg_id`，MCU 点亮 LED。
- 肉眼和摄像头都能确认编码正确。

## M3：真实摄像头解码

目标：

- R2 摄像头识别 AprilTag。
- 根据 Tag 姿态做透视矫正。
- 在矫正图中读取 LED ROI。
- 1.5m、±45°、100 次切换误码为 0。

### M3-1：真实相机 provider 抽取 / 可测试 pipeline ✅

- ✅ `HikrobotFrameProvider` — 从 `tools/hikrobot_3led_live.py` 抽取相机生命周期管理
- ✅ `ThreeLedRoiDecoder` — 3-LED ROI 采样 + SEQ 跟踪 + 8-LED 协议兼容
- ✅ `FakeFrameProvider` — 无 SDK 测试用假帧提供器
- ✅ `FrameLogger` — CSV/JSONL 调试日志输出
- ✅ `tools/hikrobot_3led_live.py` 保留为薄 CLI wrapper
- ✅ pipeline：HikrobotFrameProvider → ThreeLedRoiDecoder → BeaconStabilizer → R2 FSM
- ✅ 测试覆盖 roi_mean、decode_3led_from_frame、FakeFrameProvider、ThreeLedRoiDecoder、FrameLogger

## M4：ROS2 集成

目标：

- R1 遥控器 -> R1 状态机 -> LED MCU。
- R2 摄像头 -> beacon_decoder -> R2 状态机。
- 武馆组装流程跑通。

## M5：对抗区扩展

增加：

- 九宫格目标 1~9。
- 举升平台准备。
- 顶层释放允许。
- R2 释放完成反馈。
