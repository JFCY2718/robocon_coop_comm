# robocon_coop_comm

ROBOCON 2026「武林探秘」R1/R2 两机协作通信项目。

**通信方案：AprilTag 定位 + LED 二进制光码。**
R1 通过 LED 光码板发出状态信号，R2 通过摄像头 + AprilTag 检测解码。

> 📌 **当前状态（2026-06-17）**：
> - ✅ 软件协议与状态机已完成
> - ✅ STM32F103 + 三灯串口闭环已实机验证通过，ACK 正常
> - ✅ Hikrobot 三灯识别脚本已有
> - 🔜 六灯 REF/SEQ/PAR 为下一阶段扩展（代码已预留，固件已定义）
> 纯软件闭环可以直接跑，真实硬件替换上层接口不变。
>
> 仓库包含两部分：
> - 🐍 **Python 上位机** — R1/R2 状态机、协议编解码、操作手输入、虚拟信标、benchmark
> - 🔌 **STM32F103 C 固件** — LED 光码板 MCU 裸寄存器固件（USART1 串口帧 → LED + ACK）

---

## 仓库构成

| 部分 | 位置 | 说明 |
|------|------|------|
| Python 控制端 | `robocon_coop_comm/` `tools/` | R1 逻辑、状态机、协议、串口帧发送 |
| STM32 固件 | `firmware/stm32f103_beacon_baremetal/` | LED Beacon MCU 裸寄存器 C 固件 |
| Arduino 固件骨架 | `firmware/led_beacon_mcu/` | Arduino 参考实现 |

### 快速测试（完整链路）

```bash
# 1. 烧录固件到 STM32F103（用 STM32CubeProgrammer 或 OpenOCD）
#    固件路径: firmware/stm32f103_beacon_baremetal/main.c

# 2. 激活 Python 环境
source .venv/bin/activate

# 3. 发一帧验证
python tools/r1_beacon_control.py --port /dev/ttyACM0 --command insert
# 期望: ack=CC 04 01, STM32 上 D2 LED 亮
```

---

## 核心原则

- ❌ R1/R2 之间**不使用** Wi-Fi、蓝牙、Zigbee、UWB、LoRa、ESP-NOW 等无线射频通信。
- ❌ 武馆组装阶段**不使用** R1/R2 直接接触式通信。
- ✅ 遥控器只向 R1 状态机发出"状态请求"，不直接控制 R2，也不直接点亮某颗 LED。
- ✅ R2 将 R1 光码视为"队友状态"，必须结合自身状态机和传感器判断后才执行动作。
- ✅ 所有危险事件（如 `INSERT_ALLOWED`）必须由 R1 本地传感器条件守卫。

---

## 给新同事：10 分钟上手

### 1. 克隆仓库

```bash
git clone https://github.com/JFCY2718/robocon_coop_comm.git
cd robocon_coop_comm
```

### 2. 创建虚拟环境并安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev,vision]"
```

### 3. 跑测试确认环境正常

```bash
./tools/test.sh
# 期望：188+ passed
```

### 4. 跑一个 demo 看看效果

```bash
# 命令行闭环演示（不需要硬件）
python -m robocon_coop_comm.demo_cli

# OpenCV 虚拟信标窗口（需要图形界面）
python -m robocon_coop_comm.demo_cv
```

### 5. （如果有硬件）发送一帧到 STM32

```bash
# 需要先接好 ST-LINK 和 STM32，安装 pyserial
pip install pyserial

# dry-run 先验证帧格式
python tools/r1_beacon_control.py --dry-run --command insert

# 实机发送
python tools/r1_beacon_control.py --port /dev/ttyACM0 --command insert
# 期望看到: ack=CC 04 01
```

---

## 硬件环境（✅ 已验证）

### 已验证设备

| 硬件 | 用途 |
|------|------|
| STM32F103C8T6 (Blue Pill) | LED 光码 MCU，接收 USART1 串口帧 |
| ST-LINK/V2.1 | 烧录器 + USB 虚拟串口 (VCP)，系统枚举为 `/dev/ttyACM0` |
| 3× 高亮 LED + 限流电阻 | D0/D1/D2 **三灯信标（✅ 已实机验证）** |
| 3× LED（REF/SEQ/PAR） | **六灯模式下一阶段扩展**（引脚 PA3/PA4/PA5 已预留） |
| Hikrobot 相机 | 三灯识别测试脚本已有（`tools/hikrobot_3led_live.py`） |

### 引脚接线

**三灯：**

| STM32 GPIO | 连接 |
|------------|------|
| PA0 | → 电阻 → D0 LED 长脚，短脚 → GND |
| PA1 | → 电阻 → D1 LED 长脚，短脚 → GND |
| PA2 | → 电阻 → D2 LED 长脚，短脚 → GND |
| PA3 | REF，预留 |
| PA4 | SEQ，预留 |
| PA5 | PAR，预留 |

**串口（ST-LINK ↔ STM32）：**

| ST-LINK | STM32 |
|---------|-------|
| TX | PA10 / USART1_RX |
| RX | PA9 / USART1_TX |
| GND | GND |

**串口参数：** 115200 baud / 8N1 / 无流控

### 串口帧格式

```
AA 55 msg_id seq brightness checksum
```

| 字节 | 字段 | 说明 |
|------|------|------|
| 0-1 | Header | 固定 `AA 55` |
| 2 | msg_id | 0~31，对应 `protocol.MsgID` |
| 3 | seq | 0 或 1，事件切换时翻转 |
| 4 | brightness | 0~255 LED 亮度 |
| 5 | checksum | `msg_id ^ seq ^ brightness` |

**ACK 格式：** `CC msg_id seq`（3 字节）

### 已验证命令

| 命令 | msg_id | 帧 | ACK |
|------|--------|-----|-----|
| `hold` | 1 | `AA 55 01 00 C8 C9` | `CC 01 00` |
| `rod` | 2 | `AA 55 02 01 C8 CB` | `CC 02 01` |
| `insert` | 4 | `AA 55 04 01 C8 CD` | `CC 04 01` |
| `mf` | 7 | `AA 55 07 00 C8 CF` | `CC 07 00` |

---

## 项目结构

```text
robocon_coop_comm/
├── robocon_coop_comm/           # Python 包（核心代码）
│   ├── protocol.py              # msg_id 定义、LED 编码/解码、校验
│   ├── r1_fsm.py                # R1 任务状态机
│   ├── r2_fsm.py                # R2 任务状态机
│   ├── serial_frame.py          # MCU 串口帧编解码 (AA 55 ...)
│   ├── serial_transport.py      # 串口传输抽象（内存假串口 / pyserial）
│   ├── led_mcu_client.py        # LED MCU 高层客户端
│   ├── led_mcu_simulator.py     # MCU 固件模拟器（无硬件时使用）
│   ├── beacon_image.py          # 虚拟 LED 信标图像生成/解码
│   ├── beacon_decoder.py        # 信标图像解码
│   ├── beacon_stabilizer.py     # 解码结果稳定化
│   ├── beacon_frame_provider.py # 帧提供器抽象
│   ├── beacon_types.py          # 信标类型定义
│   ├── operator_command.py      # 操作手命令抽象层
│   ├── operator_session.py      # 操作手会话管理
│   ├── keyboard_operator.py     # 键盘操作手输入
│   ├── trace_events.py          # 链路追踪事件
│   ├── trace_export.py          # Chrome Trace 导出
│   ├── dojo_end_to_end.py       # 武馆端到端 pipeline
│   ├── pipeline_benchmark.py    # 性能 benchmark
│   ├── demo_cli.py              # 命令行闭环演示
│   ├── demo_cv.py               # OpenCV 虚拟信标窗口
│   ├── demo_mcu_pipeline.py     # MCU pipeline 模拟
│   ├── demo_operator_pipeline.py # 操作手 pipeline
│   ├── demo_r2_vision_pipeline.py # R2 视觉 pipeline
│   ├── demo_dojo_end_to_end.py  # 武馆端到端演示
│   ├── demo_benchmark.py        # benchmark 入口
│   └── ros_nodes/               # ROS2 Humble 可选节点
├── firmware/
│   ├── stm32f103_beacon_baremetal/  # ✅ STM32F103 裸寄存器 C 固件（已实机验证）
│   │   ├── main.c                   #   固件源码
│   │   ├── README.md                #   烧录/接线说明
│   │   └── PROTOCOL.md              #   串口协议文档
│   └── led_beacon_mcu/              # Arduino MCU 固件骨架（参考实现）
├── test/                        # pytest 单元测试 (188+)
├── docs/                        # 协议、架构、硬件文档
├── tools/                       # 开发/调试辅助脚本
├── .github/workflows/           # GitHub Actions CI
├── pyproject.toml               # Python 项目配置
└── Makefile                     # 常用命令快捷方式
```

---

## 常用命令速查

### 测试

```bash
./tools/test.sh                  # 全部单元测试
make test-all                    # test + demo-cli-check + demo-mcu-check
make lint                        # ruff 代码检查
```

### Demo（无需硬件）

```bash
python -m robocon_coop_comm.demo_cli               # 命令行闭环
python -m robocon_coop_comm.demo_cv                # OpenCV 虚拟信标窗口
python -m robocon_coop_comm.demo_mcu_pipeline       # MCU pipeline 模拟
python -m robocon_coop_comm.demo_operator_pipeline  # 操作手 pipeline
python -m robocon_coop_comm.demo_r2_vision_pipeline # R2 视觉 pipeline
python -m robocon_coop_comm.demo_dojo_end_to_end    # 武馆端到端
python -m robocon_coop_comm.demo_benchmark          # 性能 benchmark
```

### 硬件调试

```bash
# R1 Beacon 交互控制台
python tools/r1_beacon_control.py --port /dev/ttyACM0

# R1 Beacon 单次发送
python tools/r1_beacon_control.py --port /dev/ttyACM0 --command insert
python tools/r1_beacon_control.py --dry-run --command insert   # 只打印不发送

# 低层串口帧发送
python tools/send_3led_msg.py --port /dev/ttyACM0 --msg-id 4 --seq 1 --brightness 200

# 仅生成帧 hex（不开串口）
python tools/send_led_frame.py --msg-id 4 --seq 1 --brightness 200

# 关闭 LED
python tools/send_3led_msg.py --port /dev/ttyACM0 --msg-id 0 --seq 0 --brightness 0
```

### 交互控制台命令

```
> hold      # 发送 HOLD (msg_id=1)
> rod       # 发送 R1_ROD_CLAMPED (msg_id=2)
> pose      # 发送 R1_AT_ASSEMBLY_POSE (msg_id=3)
> insert    # 发送 INSERT_ALLOWED (msg_id=4)
> locked    # 发送 WEAPON_LOCKED (msg_id=5)
> clear     # 发送 R1_CLEAR_MC (msg_id=6)
> mf        # 发送 R1_IN_MF (msg_id=7)
> status    # 查看当前状态
> help      # 帮助
> q         # 退出
```

### Benchmark

```bash
python -m robocon_coop_comm.demo_benchmark --iterations 100 --warmup-iterations 1
python -m robocon_coop_comm.demo_benchmark --iterations 20 --trace-out /tmp/trace.json
make benchmark
make benchmark-check
```

---

## 开发指南

### 开发原则

1. **保持 `./tools/test.sh` 通过** — 修改代码后先跑测试。
2. **修改协议时同步更新** `docs/PROTOCOL.md` 和测试。
3. **新增硬件模块不要破坏纯软件 demo** — 硬件和软件解耦。
4. **每个状态机新增状态都要有单元测试**。

### 模块分层

```
操作手输入 (keyboard/F710/ROS2 joy)
  → OperatorSession / OperatorCommand
    → R1MissionFSM (r1_fsm.py)
      → LedMcuClient (led_mcu_client.py)
        → serial_frame.encode_frame()
          → PySerialTransport / MemorySerialTransport
            → STM32 USART1
              → LED 光码板 (PA0/PA1/PA2)
                → R2 摄像头 + AprilTag
                  → BeaconDecoder → R2MissionFSM
```

### 添加新 msg_id

1. 在 `protocol.py` 的 `MsgID` 枚举中添加。
2. 在 `r1_fsm.py` 中添加对应的状态转换。
3. 在 `tools/r1_beacon_control.py` 的 `COMMAND_MAP` 中添加命令映射。
4. 更新 `docs/PROTOCOL.md`。
5. 添加对应单元测试。

### 添加新的 R1 Beacon 命令

编辑 `tools/r1_beacon_control.py` 中的 `COMMAND_MAP`:

```python
COMMAND_MAP: dict[str, MsgID] = {
    # ... 现有命令 ...
    "new_cmd": MsgID.SOME_NEW_MSG,
}
```

---

## Pipeline 说明

| Pipeline | 入口 | 说明 |
|----------|------|------|
| **CLI Demo** | `demo_cli.py` | 键盘 → R1 FSM → 直接解码 → R2 FSM，最简单闭环 |
| **CV Demo** | `demo_cv.py` | 同上 + OpenCV 虚拟信标图像窗口 |
| **Operator Pipeline** | `demo_operator_pipeline.py` | 操作手输入抽象层完整链路 |
| **MCU Pipeline** | `demo_mcu_pipeline.py` | R1 FSM → LED MCU Client → 模拟器 |
| **R2 Vision** | `demo_r2_vision_pipeline.py` | 信标图像 → 解码 → 稳定化 → R2 FSM |
| **Dojo E2E** | `demo_dojo_end_to_end.py` | 武馆完整闭环（操作手 → R1 → LED → 视觉 → R2） |
| **Benchmark** | `demo_benchmark.py` | 端到端延迟测量 + Chrome Trace 导出 |

详细文档见 `docs/` 目录。

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [PROTOCOL.md](docs/PROTOCOL.md) | 光码协议完整定义 |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统架构与模块边界 |
| [SERIAL_FRAME.md](docs/SERIAL_FRAME.md) | MCU 串口帧协议 |
| [LED_MCU_LINK.md](docs/LED_MCU_LINK.md) | LED MCU 链路与硬件接线 ✅ |
| [OPERATOR_INPUT.md](docs/OPERATOR_INPUT.md) | 操作手输入抽象层 |
| [R2_VISION_PIPELINE.md](docs/R2_VISION_PIPELINE.md) | R2 视觉解码 pipeline |
| [DOJO_END_TO_END.md](docs/DOJO_END_TO_END.md) | 武馆端到端 pipeline |
| [MCU_PIPELINE_SIM.md](docs/MCU_PIPELINE_SIM.md) | MCU pipeline 模拟 |
| [PERFORMANCE_BENCHMARK.md](docs/PERFORMANCE_BENCHMARK.md) | 性能 benchmark |
| [ROADMAP.md](docs/ROADMAP.md) | 项目路线图 |
| [LOCAL_DEV_UBUNTU22.md](docs/LOCAL_DEV_UBUNTU22.md) | Ubuntu 22.04 开发环境配置 |

---

## ROS2 Humble（可选）

```bash
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
ros2 run robocon_coop_comm r1_fsm_node
```

---

## CI

GitHub Actions 自动运行：

- `./tools/test.sh` — 全部单元测试
- `make demo-cli-check` — CLI demo 回归
- `make demo-mcu-check` — MCU pipeline 回归
- `make benchmark-check` — 性能基准

---

## 团队

ROBOCON 2026 战队 · 通信组

仓库：[github.com/JFCY2718/robocon_coop_comm](https://github.com/JFCY2718/robocon_coop_comm)
