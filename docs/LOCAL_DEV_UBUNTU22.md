# Ubuntu 22.04 本地开发指南

## 项目路径

```
/home/jfcy/rc/robocon_coop_comm
```

## 激活虚拟环境

```bash
cd /home/jfcy/rc/robocon_coop_comm
source .venv/bin/activate
```

## 安装依赖

```bash
pip install -e ".[dev,vision]"
```

## 运行测试

```bash
./tools/test.sh
```

或：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
```

### 为什么不要直接运行 `pytest -q`

本机安装了 ROS Humble，直接运行 `pytest -q` 会自动加载 `launch_testing` pytest 插件，可能导致 `yaml`/`lark` 等依赖错误。

`./tools/test.sh` 已自动设置 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 来避免此问题。

## 运行命令行 demo

```bash
python -m robocon_coop_comm.demo_cli
```

**注意：** 进入 `robocon>` 提示符后，不能输入 `python -m robocon_coop_comm.demo_cv`，这会被当作 demo 内部命令解析。必须先输入 `q` 退出 `robocon>`，回到 shell 后再运行 `demo_cv`。

## 运行 OpenCV 虚拟信标板 demo

```bash
python -m robocon_coop_comm.demo_cv
```

## demo_cli 推荐测试流程

```
start
rod
next
pose
next
lock
head
tag
pre
next
weapon
next
clear
next
mf
next
q
```

## 运行 demo_cli 自动检查

```bash
./tools/demo_cli_check.sh
```

## 当前开发路线

1. **纯 Python 软件闭环** — 已完成
2. **虚拟 LED 光码** — 已完成
3. **R2 图像解码** — 已完成
4. **MCU 串口帧协议** — 已完成
5. **后续** — 替换为真实 LED、摄像头、MCU、遥控器
