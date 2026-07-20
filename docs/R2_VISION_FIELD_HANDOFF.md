# R2 Vision Field Verification — Complete Handoff Guide

> **最后更新**: 2026-07-20  
> **当前阶段**: Phase 0-2 完成，Phase 3 等待信标板就位  
> **接手者**: 任何需要继续实机验证的人

---

## 目录

1. [概述](#1-概述)
2. [硬件清单](#2-硬件清单)
3. [一键环境搭建](#3-一键环境搭建)
4. [关键发现与避坑](#4-关键发现与避坑)
5. [阶段执行指南](#5-阶段执行指南)
6. [架构速查](#6-架构速查)
7. [故障排查](#7-故障排查)
8. [安全规则](#8-安全规则)

---

## 1. 概述

### 项目是什么

ROBOCON 2026 R1/R2 协作**光通信**系统。R1 通过 LED 光码板发送 16 种状态（4 数据位 + REF + PAR），R2 通过 **Hikrobot 工业相机** 拍摄并解码。

### 视觉管道

```text
R1 受保护状态机
  → F407 专用 UART → STM32F103 Beacon 板
  → D0/D1/D2/D3/REF/PAR (6 颗常亮 LED)
  → Hikrobot 全局快门相机
  → AprilTag ID 0 检测 → 单应性变换 → 动态 ROI 投影
  → 分位数采样 → 阈值 → 协议校验 → 时间门控
  → BeaconEvent → R2MissionFSM + 本地传感器
  → dry-run ActionIntent（不驱动真实执行器）
```

### 仓库信息

| 仓库 | 分支 | 用途 |
|------|------|------|
| `JFCY2718/robocon_coop_comm` | `feature/four-light-optical` | R2 视觉管道 + 协议 + FSM |
| `JFCY2718/Rscontrol2` | `feature/beacon-uart-v2` | R1 F407 固件（发送端） |
| `JFCY2718/robstride_driver_r2` | `feature/four-light-state-machine` | R2 电机控制（**不在此验证范围内**） |

### 核心不变项

- **Beacon 板**：280×220 mm 哑光黑
- **AprilTag**：tag36h11, ID 0, 黑边名义 150mm（实测填入）
- **Tag 中心**：(-55, 0) mm（板中心坐标系）
- **LED 位置**：
  - 上行 D0(40,70) D1(80,70) D2(120,70)
  - 下行 D3(40,20) REF(80,20) PAR(120,20)
- **灯帽直径**：22.4mm
- **固定比特序**：D0=bit0 … PAR=bit5（不可交换）
- **PAR 算法**：D0⊕D1⊕D2⊕D3 异或

---

## 2. 硬件清单

| 设备 | 型号/规格 | 备注 |
|------|-----------|------|
| 相机 | **Hikrobot MV-CS016-10UC** | USB3 Vision, 1440×1080, 全局快门 |
| SDK | MVS (Linux x86_64) | 安装路径 `/opt/MVS` |
| Beacon 板 | 280×220mm, 6 颗 LED + tag36h11 ID 0 | 不可重新设计 |
| LED 驱动 | STM32F103, PA0-PA5 → D0-PAR | 3.3V UART |
| 串口 | `/dev/ttyACM0`（以实际为准） | 115200 baud |

---

## 3. 一键环境搭建

### 首次搭建（全新 Ubuntu 22.04）

```bash
# 1. 克隆仓库
mkdir -p ~/rc && cd ~/rc
git clone https://github.com/JFCY2718/robocon_coop_comm.git
cd robocon_coop_comm
git switch feature/four-light-optical
git pull --ff-only origin feature/four-light-optical

# 2. Python 环境
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e '.[dev,vision,apriltag]' pyserial

# 3. 验证软件基线
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q  # 应 ≥ 736 passed
python -m ruff check .  # 应无错误

# 4. 设置 MVS SDK 环境变量（每次新终端都需要）
export MVCAM_COMMON_RUNENV=/opt/MVS/lib
export PYTHONPATH=/opt/MVS/Samples/64/Python/MvImport:$PYTHONPATH
export LD_LIBRARY_PATH=/opt/MVS/lib/64:/opt/MVS/bin:$LD_LIBRARY_PATH

# 5. 验证 MVS SDK
python -c "from MvCameraControl_class import MvCamera; print('MVS_OK')"

# 6. 检查相机枚举
python tools/hikrobot_device_check.py --open
```

### 每次恢复工作的命令

```bash
cd ~/rc/robocon_coop_comm && source .venv/bin/activate
git pull --ff-only origin feature/four-light-optical
export MVCAM_COMMON_RUNENV=/opt/MVS/lib
export PYTHONPATH=/opt/MVS/Samples/64/Python/MvImport:$PYTHONPATH
export LD_LIBRARY_PATH=/opt/MVS/lib/64:/opt/MVS/bin:$LD_LIBRARY_PATH
python tools/hikrobot_device_check.py --open
```

---

## 4. 关键发现与避坑

### 4.1 相机型号

**实际相机是 MV-CS016-10UC**（1.6MP USB3），不是文档中假设的 MV-CA050-20UC（5MP）。分辨率 1440×1080 Mono8。

### 4.2 MVS SDK USB 枚举

**MV_USB_DEVICE 常量值是 4，不是 2！**

```python
# 正确用法
from CameraParams_const import MV_USB_DEVICE  # = 4
dl = MV_CC_DEVICE_INFO_LIST()
MvCamera.MV_CC_EnumDevices(MV_USB_DEVICE, dl)  # 只用 USB (4)
```

错误用法 `2` 或 `MV_GIGE_DEVICE | MV_USB_DEVICE`（=5）都会返回 `0x80000004` 且 count=0。

已提供诊断工具：`python tools/hikrobot_device_check.py --open`

### 4.3 曝光设置

MV-CS016-10UC 增益上限较低。**Gain > 15 会报错 `0x80000102`**。建议起步值：

| 距离 | Exposure | Gain | 备注 |
|------|----------|------|------|
| 0.5-1m | 5000µs | 0 | 竞赛推荐起点 |
| 1-2m | 10000-15000µs | 3-5 | 室内灯光 |
| 暗环境 | 20000-40000µs | 5-10 | 逐步增加 |

### 4.4 USB 权限

相机 USB 设备需要 udev 规则：

```bash
sudo sh -c 'echo "SUBSYSTEM==\"usb\", ATTR{idVendor}==\"2bdf\", MODE=\"0666\"" > /etc/udev/rules.d/99-hikrobot.rules'
sudo udevadm control --reload-rules && sudo udevadm trigger
# 重新插拔相机 USB
```

### 4.5 测试 ≠ 实机验收

- pytest 737 passed = 软件正常
- mock/单元测试/dry-run ≠ 实机通过
- 只有真实相机 + 真实灯板 + expected-vs-observed checker 输出才算实机数据
- 不提交真实日志、帧、ROI、增益文件

---

## 5. 阶段执行指南

### 阶段 0：仓库安全检查 ✅

```bash
cd ~/rc/robocon_coop_comm
git status -sb                    # 应显示 feature/four-light-optical
git merge-base --is-ancestor 4d234ec703d35a25cd912d866b570bdd1c6fbbba HEAD
echo $?                           # 应为 0
git rev-parse HEAD
```

### 阶段 1：软件环境 ✅

```bash
source .venv/bin/activate
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q   # ≥ 736 passed
python -m ruff check .                                   # 无错误
python tools/hikrobot_6led_live.py --help                # 返回 0
python tools/hikrobot_apriltag_smoke.py --help           # 返回 0
python tools/sixled_log_summary.py --help                # 返回 0
python tools/sixled_serial_sequence.py --help            # 返回 0
python tools/sixled_expected_observed_check.py --help    # 返回 0
python tools/send_beacon_uart_v2.py --help               # 返回 0
python tools/send_beacon_uart_v2.py --dry-run --state INSERT_ALLOWED --count 1
```

### 阶段 2：MVS 环境 ✅

```bash
export MVCAM_COMMON_RUNENV=/opt/MVS/lib
export PYTHONPATH=/opt/MVS/Samples/64/Python/MvImport:$PYTHONPATH
export LD_LIBRARY_PATH=/opt/MVS/lib/64:/opt/MVS/bin:$LD_LIBRARY_PATH
python -c "from MvCameraControl_class import MvCamera; print('MVS_IMPORT_OK')"
python -m serial.tools.list_ports  # 记下实际串口设备
```

### 阶段 3：AprilTag 单独验证 ⚠️ 当前

**前提**：Beacon 板（带 tag36h11 ID 0）放在相机前方 0.5-1m，灯光充足。

```bash
mkdir -p /tmp/robocon_r2/logs /tmp/robocon_r2/frames

# 纯终端模式（推荐先用这个确认检测到 tag）
python tools/hikrobot_apriltag_smoke.py \
  --family tag36h11 \
  --tag-id 0 \
  --exposure 5000 \
  --gain 0 \
  --log-jsonl /tmp/robocon_r2/logs/tag_smoke.jsonl

# GUI 模式（需要在有显示器的环境）
python tools/hikrobot_apriltag_smoke.py \
  --family tag36h11 \
  --tag-id 0 \
  --display \
  --exposure 5000 \
  --gain 0 \
  --log-jsonl /tmp/robocon_r2/logs/tag_smoke.jsonl
```

**观察记录**（每个距离/角度组合）：

| 条件 | Tag ID | Decision Margin | Tag 像素边长 | FPS |
|------|--------|-----------------|-------------|-----|
| 1m 正视 | | | | |
| 1.5m 正视 | | | | |
| 3m 正视 | | | | |
| 最大距离 | | | | |
| +30° | | | | |
| -30° | | | | |
| +45° | | | | |
| -45° | | | | |
| 遮挡测试 | (none) | — | — | — |

**若 Tag 检测不到**：
1. 确认 tag36h11 ID 0 在视野内且清晰
2. 逐步提高 exposure（5000→8000→12000→15000），gain 保持 0
3. 检查镜头焦距和对焦环
4. 避免强反光/阴影遮挡 Tag 黑边
5. 用 `python tools/hikrobot_device_check.py --open` 确认相机基本工作

### 阶段 4：固定 ROI 基准

**必须在 AprilTag 动态 ROI 之前通过。**

```bash
python tools/hikrobot_6led_live.py \
  --roi-mode fixed \
  --save-roi /tmp/robocon_r2/site_roi.json \
  --threshold 60 \
  --exposure 5000 \
  --gain 0 \
  --timeout 100 \
  --protocol \
  --protocol-mode four-light \
  --log /tmp/robocon_r2/logs/fixed_observed.csv
```

**点击顺序**：D0 → D1 → D2 → D3 → REF → PAR

**键盘操作**：
- 左键：选择下一灯中心
- `r`：重选全部
- `s`：保存 ROI
- `+`/`-`：调阈值
- `q`：退出

**验证项**：
- [ ] 六个 ROI 都在对应灯面内部
- [ ] D0~PAR 顺序正确
- [ ] 亮灯和灭灯亮度区间不重叠
- [ ] REF 关闭时输出 invalid
- [ ] PAR 错误时输出 invalid
- [ ] exposure/gain 为手动值（非自动）

**日志分析**：
```bash
python tools/sixled_log_summary.py /tmp/robocon_r2/logs/fixed_observed.csv
```

### 阶段 5：竞赛软件方案（AprilTag 动态 ROI）

```bash
python tools/hikrobot_6led_live.py \
  --competition \
  --beacon-layout data/sixled/configs/competition_beacon_280x220.json \
  --draw-tag \
  --draw-dynamic-rois \
  --log /tmp/robocon_r2/logs/competition_observed.csv
```

**`--competition` 实际启用的特性**：
- AprilTag 动态 ROI
- 2 线程检测，每 2 帧完整检测 + 中间帧 LK 光流
- 中心 70 分位数 + 背景环 50 分位数采样
- REF 自适应阈值 + 12% 滞回 + 饱和检测
- latest-frame 单槽缓存
- 普通状态 3/5 投票
- INSERT_ALLOWED / TOP_RELEASE_ALLOWED 连续 5 帧确认
- 300ms 信号过期
- exposure 5000µs, gain 0, timeout 100ms
- Mono8, 自动曝光/增益关闭

### 阶段 6：六路 LED 增益标定

保持相机位置不变，**逐路只点亮一颗 LED**：

```bash
# 增益公式: gain_i = median(REF_on) / median(LED_i_on)
# 将结果写入 /tmp/robocon_r2/measured_led_gains.json
# 格式参考 data/sixled/configs/led_gains.example.json

# 使用增益文件重新运行
python tools/hikrobot_6led_live.py \
  --competition \
  --beacon-layout data/sixled/configs/competition_beacon_280x220.json \
  --led-gains /tmp/robocon_r2/measured_led_gains.json \
  --draw-tag \
  --draw-dynamic-rois \
  --log /tmp/robocon_r2/logs/competition_calibrated.csv
```

**注意**：任何增益超出 0.7~1.4 时，优先检查硬件而非软件补偿。

### 阶段 7：16 状态 Expected-vs-Observed

**先确认真实串口**，不得猜测 `/dev/ttyACM0`：

```bash
python -m serial.tools.list_ports
```

**终端 A（相机采集）**：
```bash
python tools/hikrobot_6led_live.py \
  --competition \
  --beacon-layout data/sixled/configs/competition_beacon_280x220.json \
  --led-gains /tmp/robocon_r2/measured_led_gains.json \
  --draw-tag --draw-dynamic-rois \
  --log /tmp/robocon_r2/logs/competition_calibrated.csv
```

**终端 B（串口发送）**：
```bash
python tools/send_beacon_uart_v2.py \
  --port <实际串口> \
  --states 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15 \
  --hold-sec 3 \
  --refresh-sec 0.05 \
  --expected-log /tmp/robocon_r2/four_light_expected.csv
```

**诊断检查**（宽松门限）：
```bash
python tools/sixled_expected_observed_check.py \
  --expected /tmp/robocon_r2/four_light_expected.csv \
  --observed /tmp/robocon_r2/logs/competition_calibrated.csv \
  --settle-sec 0.5 \
  --min-dominant-ratio 0.90 \
  --min-valid-ratio 0.50
```

**验收检查**（严格门限）：
```bash
python tools/sixled_expected_observed_check.py \
  --expected /tmp/robocon_r2/four_light_expected.csv \
  --observed /tmp/robocon_r2/logs/competition_calibrated.csv \
  --settle-sec 0.5 \
  --min-dominant-ratio 0.995 \
  --min-valid-ratio 0.95 \
  --json
```

**需在不同工况分别验证**：1m/1.5m/3m/最大距离 × 正视/±30°/±45° × 静止/移动

### 阶段 8：故障与安全测试

逐项测试并记录：

| # | 测试项 | 预期结果 |
|---|--------|---------|
| 1 | Tag 完全遮挡 | 下一帧 invalid，300ms 后不用旧状态 |
| 2 | 错误 Tag ID | invalid，不产生事件 |
| 3 | REF 关闭 | reason=reference_off, gated valid=false |
| 4 | PAR 错误 | reason=parity_error, gated valid=false |
| 5 | ROI 超出画面 | invalid，不强行夹到边界 |
| 6 | 相机断开 | 不留可执行状态，不输出旧 ActionIntent |
| 7 | 低置信/过期时间戳 | 被时间门控或 FSM 拒绝 |
| 8 | INSERT_ALLOWED < 5 帧 | gated valid=false |
| 9 | TOP_RELEASE_ALLOWED < 5 帧 | gated valid=false |
| 10 | 重复状态 | 不重复触发一次性动作 |

### 阶段 9：R2 Dry-Run 判定

**只有以下全部满足才能设置 READY_FOR_R2_VISION_DRY_RUN=YES**：

- [ ] 固定 ROI 稳定
- [ ] AprilTag 动态 ROI 稳定
- [ ] 每个工况 gated match ≥ 99.5%
- [ ] 最大距离 raw valid ≥ 95%
- [ ] 危险状态错误接受 = 0
- [ ] REF/PAR 故障 100% → invalid
- [ ] Tag 遮挡 → 下一帧 invalid
- [ ] capture age P95 ≤ 100ms
- [ ] 视觉处理时延 P95 ≤ 150ms
- [ ] 300ms 旧事件失效验证通过

**即使全部通过也必须保持**：`READY_FOR_DANGEROUS_ACTUATOR_CONNECTION=NO`

### 阶段 10：最终报告

必须包含：
1. repository, remote, branch, HEAD
2. working tree 和 push 状态
3. pytest, ruff, CLI help, dry-run 结果
4. MVS SDK 路径、相机型号和实际串口
5. 确认 Beacon 板仍为 280×220 mm
6. 实测 Tag 黑边尺寸
7. 固定 ROI 六路亮/灭范围和阈值
8. 六路 LED 增益
9. 每个距离/角度的指标数据
10. 16 状态逐状态结果
11. Tag 遮挡、错误 ID、REF、PAR、ROI 越界、相机断开、300ms 超时结果
12. 所有本地日志路径
13. OK/WARNING/BLOCKER 分类
14. READY_FOR_R2_VISION_DRY_RUN=YES/NO
15. READY_FOR_DANGEROUS_ACTUATOR_CONNECTION=NO

---

## 6. 架构速查

### 核心模块

```
robocon_coop_comm/
├── apriltag_detector.py        # pupil-apriltags 封装
├── apriltag_roi_mapper.py      # 单应性变换 LED ROI 投影
├── beacon_decoder_apriltag.py  # AprilTag 引导的 3-LED 解码
├── dynamic_sixled.py           # 动态六灯 AprilTag 检测 + ROI
├── six_led_decoder.py          # 六灯 ROI 采样 + bitmask 解码
├── temporal_beacon_validator.py # 时间门控 + 投票稳定器
├── latest_frame_provider.py    # 单槽异步取流
├── hikrobot_frame_provider.py  # 海康相机帧提供器
├── beacon_stabilizer.py        # 信标稳定化（N帧一致）
├── pattern_mapper.py           # LED 布局映射
├── beacon_types.py             # BeaconFrame, DecodedBeacon, BeaconEvent
├── protocol.py                 # LED 协议编解码
├── r1_fsm.py / r2_fsm.py       # 任务状态机
```

### 关键工具

```
tools/
├── hikrobot_6led_live.py           # 六灯实时解码（主入口）
├── hikrobot_apriltag_smoke.py      # AprilTag 冒烟测试
├── hikrobot_device_check.py        # 相机枚举诊断（NEW）
├── send_beacon_uart_v2.py          # 四灯 V2 串口发送器
├── sixled_log_summary.py           # 六灯日志汇总
├── sixled_serial_sequence.py       # 串口序列发送
├── sixled_expected_observed_check.py # Expected-vs-Observed 比对
```

### 数据与配置

```
data/sixled/
├── configs/
│   ├── competition_beacon_280x220.json  # 比赛信标板配置（锁定）
│   ├── led_gains.example.json           # LED 增益标定模板
│   └── breadboard_roi.json              # 临时面包板 ROI（不提交）
├── logs/    # 本地日志（不提交）
└── frames/  # 现场帧（不提交）
```

---

## 7. 故障排查

### 相机枚举失败

```bash
python tools/hikrobot_device_check.py --open
```

常见原因：
- 环境变量未设置 → 检查 MVCAM_COMMON_RUNENV, PYTHONPATH, LD_LIBRARY_PATH
- USB 权限问题 → 添加 udev 规则，重新插拔
- MVS SDK 版本过旧 → 更新 SDK
- 相机未上电 → 检查 USB 线缆和电源

### Tag 检测不到

1. `python tools/hikrobot_device_check.py --open` 确认相机工作
2. 确认 tag36h11 ID 0 在视野内
3. 逐步提高 exposure：5000→8000→12000→15000
4. 检查焦距、光圈、对焦
5. 避免强反光和阴影

### pytest 失败

```bash
# 如果有 ROS2 插件干扰
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q

# 如果 venv 有问题
source .venv/bin/activate
pip install -e '.[dev,vision,apriltag]' pyserial
```

### 串口无响应

```bash
python -m serial.tools.list_ports  # 确认设备存在
ls -la /dev/ttyACM*                # 检查权限
sudo chmod 666 /dev/ttyACM0        # 修复权限
```

### Gain 设置报错

MV-CS016-10UC 增益范围有限。gain > 15 会报 `0x80000102`。优先提高 exposure 而非 gain。

---

## 8. 安全规则

### 绝对禁止

1. **不得**视觉结果直接控制电机、机械臂、夹爪
2. **不得** bypass FSM 安全检查
3. **不得** force push、改写 main、删除或移动 tag
4. **不得** 提交真实日志、帧、ROI、增益文件、build 产物
5. **不得** 用 mock/单元测试/dry-run 冒充实机验收
6. **不得** 实现 R1/R2 无线通信或接触式通信
7. **不得** 重新设计 Beacon 板、改变尺寸、移动孔位、交换 LED

### 验证期间必须

- 断开或隔离电机、机械臂、夹爪动力
- 使用限流电源
- UART 用 3.3V 并共地
- 24V 灯电源不接入 MCU GPIO/UART
- 视觉输出只产生 BeaconEvent/ActionIntent
- 所有事件经过时间门控 + FSM + 本地传感器

### 关键停止点

- 未确认 F407 空闲 UART 前 → 不改 CubeMX/usart.c/main.c
- Tag 黑边尺寸未实测前 → 不填最终 tag_size_mm
- 未完成固定 ROI 验收前 → 不进动态 ROI
- 未达验收门槛前 → READY_FOR_DANGEROUS_ACTUATOR_CONNECTION=NO

---

## 相关文档索引

| 文档 | 内容 |
|------|------|
| `docs/PROJECT_RULES.md` | 仓库规则、固定 bit 序、序列化协议 |
| `docs/R2_VISION_COMPETITION_UPGRADE.md` | 竞赛预设、硬件清单、验收门槛 |
| `docs/R2_VISION_FIELD_WORKFLOW.md` | 现场工作流、双语操作指南 |
| `docs/UBUNTU_HARDWARE_HANDOFF.md` | 三仓库交接、实现基线 hash |
| `docs/APRILTAG_SIXLED_VISION.md` | AprilTag 动态 ROI 技术细节 |
| `docs/FSM_SAFETY_DESIGN.md` | FSM 安全架构 |
| `docs/HIKROBOT_REAL_CAMERA.md` | 相机 SDK 配置 + 6LED 实测 |
| `docs/HIKROBOT_6LED_BREADBOARD_TEST.md` | 面包板 bitmask 测试 |
| `docs/HANDOFF_TO_NEXT_CC_SESSION.md` | 上一轮交接文档 |
| `STATE.md` | **当前会话 checkpoint** |
