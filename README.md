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
│   ├── beacon_image.py          # 虚拟 LED 信标图像生成/解码
│   ├── demo_cli.py              # 无图形命令行闭环演示
│   ├── demo_cv.py               # OpenCV 虚拟信标窗口演示
│   └── ros_nodes/               # ROS2 Humble 可选节点
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
pytest -q
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
