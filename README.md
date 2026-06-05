# robocon_coop_comm

ROBOCON 2026「武林探秘」R1/R2 两机协作通信项目。

当前版本先实现 **无硬件软件闭环**：

```text
键盘/虚拟遥控器 -> R1 状态机 -> LED 光码协议 -> 虚拟信标/直接解码 -> R2 状态机
```

后续硬件到位后，只需要把「虚拟信标」替换为真实 `AprilTag + LED 光码板 + 摄像头解码`，上层协议和状态机保持不变。

## 核心原则

- R1/R2 之间不使用 Wi-Fi、蓝牙、Zigbee、UWB、LoRa、ESP-NOW 等无线射频通信。
- 武馆组装阶段不使用 R1/R2 直接接触式通信。
- 遥控器只向 R1 状态机发出“状态请求”，不直接控制 R2，也不直接点亮某颗 LED。
- R2 将 R1 光码视为“队友状态”，必须结合自身状态机和传感器判断后才执行动作。

## 目录

```text
robocon_coop_comm/
├── robocon_coop_comm/
│   ├── protocol.py              # msg_id、LED 编码、校验
│   ├── r1_fsm.py                # R1 任务状态机
│   ├── r2_fsm.py                # R2 简化状态机
│   ├── serial_frame.py          # MCU 串口帧编解码
│   ├── serial_transport.py      # 串口传输抽象（内存/pyserial）
│   ├── led_mcu_client.py        # LED MCU 客户端
│   ├── beacon_image.py          # 虚拟 LED 信标图像生成/解码
│   ├── demo_cli.py              # 无图形命令行闭环演示
│   ├── demo_cv.py               # OpenCV 虚拟信标窗口演示
│   └── ros_nodes/               # ROS2 Humble 可选节点
├── firmware/
│   └── led_beacon_mcu/          # LED MCU Arduino 固件骨架
├── test/                        # pytest 单元测试
├── docs/                        # 协议、架构、路线图
├── tools/                       # Ubuntu/GitHub 辅助脚本
├── AGENTS.md                    # Codex/AI coding agent 指令
└── CLAUDE.md                    # Claude Code 指令
```

## Ubuntu 22.04 快速开始

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

cd robocon_coop_comm
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev,vision]"
./tools/test.sh
```

运行命令行闭环：

```bash
python -m robocon_coop_comm.demo_cli
```

运行 OpenCV 虚拟信标窗口：

```bash
python -m robocon_coop_comm.demo_cv
```

## ROS2 Humble 可选运行

如果你已经安装 ROS2 Humble：

```bash
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
ros2 run robocon_coop_comm r1_fsm_node
```

当前 ROS2 节点用 `std_msgs/String` 传 JSON，先避免自定义 msg 增加开发负担。

## 当前开发状态

1. 已完成纯 Python 协议（`protocol.py`）
2. 已完成 R1/R2 状态机（`r1_fsm.py` / `r2_fsm.py`）
3. 已完成虚拟 LED 信标图像（`beacon_image.py`）
4. 已完成 R2 虚拟解码（`demo_cv.py`）
5. 已完成 MCU 串口帧编码/解码（`serial_frame.py`）
6. 已完成串口传输抽象层（`serial_transport.py`）
7. 已完成 LED MCU 客户端（`led_mcu_client.py`）
8. 已完成 MCU 固件骨架（`firmware/led_beacon_mcu/`）
9. 后续将接真实 LED、MCU、摄像头、遥控器

## 常用命令

```bash
# 运行全部单元测试
./tools/test.sh

# 运行 demo_cli 自动检查
./tools/demo_cli_check.sh

# 命令行闭环演示（交互式）
python -m robocon_coop_comm.demo_cli

# OpenCV 虚拟信标窗口演示
python -m robocon_coop_comm.demo_cv

# Makefile 快捷方式
make test
make demo-cli-check
make demo-cli
make demo-cv
make lint
make send-led-frame

# MCU pipeline 模拟
make demo-mcu
make demo-mcu-check

# 运行全部检查（test + demo-cli-check + demo-mcu-check）
make test-all

# 生成 LED MCU 串口帧 hex
python tools/send_led_frame.py --msg-id 4 --seq 1 --brightness 200
```

## Operator Input Pipeline

操作手输入抽象层：键盘 → OperatorSession → OperatorCommand → R1 FSM → LED MCU。
该层只向 R1 状态机发请求，不直接控制 R2，不直接控制 LED。

```bash
python -m robocon_coop_comm.demo_operator_pipeline
./tools/demo_operator_pipeline_check.sh
make demo-operator-check
```

详见 [docs/OPERATOR_INPUT.md](docs/OPERATOR_INPUT.md)。

## R2 Vision Pipeline

R2 端视觉解码 pipeline：虚拟信标图像 → BeaconDecoder → BeaconStabilizer → R2 FSM。
当前使用虚拟图像，后续替换为 USB 摄像头 + AprilTag/LED ROI，R2 FSM 保持不变。

```bash
python -m robocon_coop_comm.demo_r2_vision_pipeline
./tools/demo_r2_vision_pipeline_check.sh
make demo-r2-vision-check
```

详见 [docs/R2_VISION_PIPELINE.md](docs/R2_VISION_PIPELINE.md)。

## Dojo End-to-End Pipeline

武馆组装阶段 R1/R2 通讯的完整软件闭环：
操作手输入 → R1 FSM → LED MCU → 虚拟信标图像 → 视觉解码 → R2 FSM。
不使用无线通信，不使用接触式通信，操作手只请求 R1 状态，R2 自主决策动作。

```bash
python -m robocon_coop_comm.demo_dojo_end_to_end
./tools/demo_dojo_end_to_end_check.sh
make demo-dojo-check
```

详见 [docs/DOJO_END_TO_END.md](docs/DOJO_END_TO_END.md)。

## MCU Pipeline Simulation

在没有真实硬件时，验证 R1 FSM → LED MCU 的完整链路：

```bash
python -m robocon_coop_comm.demo_mcu_pipeline
./tools/demo_mcu_pipeline_check.sh
make demo-mcu-check
```

`LedMcuSimulator` 模拟 Arduino 固件的帧解析和 LED 输出逻辑。
后续真实硬件接入时只需替换 transport 和 MCU 固件。

详见 [docs/MCU_PIPELINE_SIM.md](docs/MCU_PIPELINE_SIM.md)。

## Performance Benchmark

端到端 pipeline 延迟测量：从操作手请求到 R2 状态变化的软件链路耗时。
当前用于纯软件端到端链路，后续真实硬件接入后继续使用 TraceRecorder 对比延迟。

```bash
python -m robocon_coop_comm.demo_benchmark --iterations 100
./tools/demo_benchmark_check.sh
make benchmark-check
```

详见 [docs/PERFORMANCE_BENCHMARK.md](docs/PERFORMANCE_BENCHMARK.md)。

## GitHub 推送

方式一：GitHub CLI：

```bash
sudo apt install -y gh
gh auth login
git init
git add .
git commit -m "Initial R1/R2 coop communication project"
gh repo create robocon_coop_comm --private --source=. --remote=origin --push
```

方式二：SSH remote：

```bash
git init
git add .
git commit -m "Initial R1/R2 coop communication project"
git branch -M main
git remote add origin git@github.com:<你的用户名>/robocon_coop_comm.git
git push -u origin main
```
