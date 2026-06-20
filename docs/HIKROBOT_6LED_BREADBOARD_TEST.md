# Round 4A: Hikrobot 真实相机六灯面包板 Bitmask Smoke/Stability Test

> **当前阶段**: 面包板临时搭建，非最终灯板结构。
> **当前目标**: 验证 STM32 六灯亮灭 → Hikrobot 相机 → OpenCV ROI 采样 → Python bitmask 输出。
> **当前不接** R2 FSM、比赛语义、ROS2、AprilTag、远距离/大角度测试。
> **当前不宣称** M3 完成或实机链路最终通过。

---

## 硬件状态

| 项目 | 状态 |
|------|------|
| STM32 六灯 | ✅ 全部可点亮 |
| Hikrobot 相机 | ✅ MVS SDK import OK |
| OpenCV ROI 窗口 | ✅ 可打开 |
| LED 结构 | 面包板（非最终灯板） |
| ROI 标定文件 | `data/sixled/configs/breadboard_roi.json`（临时） |

## Pin Map

```
D0  -> PA0 / bit0 / 0x01
D1  -> PA1 / bit1 / 0x02
D2  -> PA2 / bit2 / 0x04
REF -> PA3 / bit3 / 0x08
SEQ -> PA4 / bit4 / 0x10
PAR -> PA5 / bit5 / 0x20
```

**D0 是最低位 bit0，PAR 是最高位 bit5。**

## 基础测试 Bitmask

| 值 | 含义 | Hex | 六位二进制 |
|----|------|-----|-----------|
| 0 | 全灭 | `0x00` | `000000` |
| 63 | 全亮 | `0x3F` | `111111` |
| 1 | D0 | `0x01` | `000001` |
| 2 | D1 | `0x02` | `000010` |
| 4 | D2 | `0x04` | `000100` |
| 8 | REF | `0x08` | `001000` |
| 16 | SEQ | `0x10` | `010000` |
| 32 | PAR | `0x20` | `100000` |

---

## MVS SDK 环境配置

每次新终端运行 Hikrobot Python 工具前：

```bash
cd /home/jfcy/rc/robocon_coop_comm
source .venv/bin/activate

export MVCAM_COMMON_RUNENV=/opt/MVS/lib
export PYTHONPATH=/opt/MVS/Samples/64/Python/MvImport:$PYTHONPATH
export LD_LIBRARY_PATH=/opt/MVS/lib/64:/opt/MVS/bin:$LD_LIBRARY_PATH
```

验证 SDK 导入：

```bash
python - <<'PY'
from MvCameraControl_class import *
print("MVS Python SDK import OK")
PY
```

期望输出：`MVS Python SDK import OK`

---

## ROI 标定

### 首次标定（面包板）

```bash
pkill -f MVS
pkill -f hikrobot_6led_live.py

cd /home/jfcy/rc/robocon_coop_comm
source .venv/bin/activate

mkdir -p data/sixled/configs data/sixled/logs data/sixled/frames

export MVCAM_COMMON_RUNENV=/opt/MVS/lib
export PYTHONPATH=/opt/MVS/Samples/64/Python/MvImport:$PYTHONPATH
export LD_LIBRARY_PATH=/opt/MVS/lib/64:/opt/MVS/bin:$LD_LIBRARY_PATH

rm -f data/sixled/configs/breadboard_roi.json

python tools/hikrobot_6led_live.py \
  --save-roi data/sixled/configs/breadboard_roi.json \
  --threshold 40 \
  --exposure 12000 \
  --gain 0 \
  --timeout 5000
```

### OpenCV 窗口操作

| 操作 | 按键 |
|------|------|
| 按顺序点击 LED 中心 | 鼠标左键 (D0 → D1 → D2 → REF → SEQ → PAR) |
| 保存 ROI | `s` |
| 重置选点 | `r` |
| 提高 threshold | `+` / `=` |
| 降低 threshold | `-` |
| 退出 | `q` |

### 检查标定结果

```bash
cat data/sixled/configs/breadboard_roi.json
```

> **breadboard_roi.json 是本地临时标定文件。换正式灯板、固定结构、改变相机位置后必须重新标定。**

---

## 实时识别

### 推荐稳定参数

```bash
python tools/hikrobot_6led_live.py \
  --roi-file data/sixled/configs/breadboard_roi.json \
  --threshold 40 \
  --exposure 12000 \
  --gain 0 \
  --timeout 5000 \
  --log data/sixled/logs/round4a_t40_e12000.csv \
  --protocol
```

### LED 较暗时

```bash
python tools/hikrobot_6led_live.py \
  --roi-file data/sixled/configs/breadboard_roi.json \
  --threshold 30 \
  --exposure 12000 \
  --gain 0 \
  --timeout 5000 \
  --log data/sixled/logs/round4a_t30_e12000.csv \
  --protocol
```

### 全灭误判亮时 (threshold 太低或 exposure 太高)

```bash
python tools/hikrobot_6led_live.py \
  --roi-file data/sixled/configs/breadboard_roi.json \
  --threshold 60 \
  --exposure 8000 \
  --gain 0 \
  --timeout 5000 \
  --log data/sixled/logs/round4a_t60_e8000.csv \
  --protocol
```

### 日志汇总

```bash
python tools/sixled_log_summary.py data/sixled/logs/round4a_t40_e12000.csv
```

---

## Threshold 调参原则

`--threshold` 含义：ROI 灰度值 > threshold → LED = ON。threshold 应放在"背景最大亮度"和"LED 最小亮度"之间。

调参优先级：

1. **ROI 点准** — 最重要
2. **降 threshold**：60 → 40 → 30
3. **提高 exposure**：8000 → 12000
4. **gain 保持 0**，必要时最多试 1~2
5. **timeout 用 5000**

> 不要一开始就加大 gain，gain 会放大背景噪声，可能导致全灭误判亮。

当前面包板建议范围：

```
threshold: 30 ~ 60
exposure:  8000 ~ 12000
gain:      0 优先
timeout:   5000
```

---

## 相机打不开 / 掉线排查

### 1. MVS Python SDK 找不到

```
ModuleNotFoundError: No module named 'MvCameraControl_class'
```

处理：

```bash
export MVCAM_COMMON_RUNENV=/opt/MVS/lib
export PYTHONPATH=/opt/MVS/Samples/64/Python/MvImport:$PYTHONPATH
export LD_LIBRARY_PATH=/opt/MVS/lib/64:/opt/MVS/bin:$LD_LIBRARY_PATH

find /opt/MVS -name "MvCameraControl_class.py" 2>/dev/null
```

### 2. SDK import OK 但 OpenDevice failed

```
MV_CC_OpenDevice failed, ret=0x80000203
```

常见原因：相机被 MVS 客户端或其他进程占用，或 Linux 设备权限不足。

处理：

```bash
pkill -f MVS
pkill -f hikrobot_6led_live.py
```

如果 kill 失败：

```bash
ps -fp <PID>
sudo kill -9 <PID>
```

重新插拔相机。

必要时用 sudo env 方式运行：

```bash
sudo env \
  MVCAM_COMMON_RUNENV=/opt/MVS/lib \
  PYTHONPATH=/opt/MVS/Samples/64/Python/MvImport \
  LD_LIBRARY_PATH=/opt/MVS/lib/64:/opt/MVS/bin \
  /home/jfcy/rc/robocon_coop_comm/.venv/bin/python \
  tools/hikrobot_6led_live.py \
  --save-roi data/sixled/configs/breadboard_roi.json \
  --threshold 40 \
  --exposure 12000 \
  --gain 0 \
  --timeout 5000
```

### 3. No Hikrobot camera found

```
ERROR: Cannot open Hikrobot camera.
No Hikrobot camera found.
```

处理顺序：

```bash
ps -ef | grep -Ei "MVS|Mv|hikrobot|camera|hikrobot_6led|python" | grep -v grep
lsusb
dmesg | tail -80
```

重新插拔相机：

1. 拔掉 Hikrobot 相机 USB / 网线
2. 等 5 秒
3. 重新插上
4. 等 10 秒

SDK 枚举脚本：

```bash
python - <<'PY'
from ctypes import *
from MvCameraControl_class import *

device_list = MV_CC_DEVICE_INFO_LIST()
tlayer_type = MV_GIGE_DEVICE | MV_USB_DEVICE

ret = MvCamera.MV_CC_EnumDevices(tlayer_type, device_list)
print(f"Enum ret = 0x{ret & 0xffffffff:08x}")
print(f"Device count = {device_list.nDeviceNum}")
PY
```

如果 `Device count = 0`：优先检查 USB/网线/供电/相机占用/权限。

USB 相机建议：

- 不要接 USB Hub
- 换短一点的数据线
- 插主板后置 USB 口
- 优先 USB3 口
- 不要和大功率设备共用 Hub

观察掉线：

```bash
sudo dmesg -w
```

如果 dmesg 出现 USB reset/disconnect → 硬件链路问题，不是识别算法问题。

---

## 已发现代码问题 / 已修状态

### `ctypes has no attribute MV_FRAME_OUT_INFO_EX` — FIXED

`MV_FRAME_OUT_INFO_EX` 是 `MvCameraControl_class.py` 中的结构体，不是 Python `ctypes` 的属性。

修复（已完成）：
- `open()` 从 SDK 导入 `MV_FRAME_OUT_INFO_EX`，存为 `self._MV_FRAME_OUT_INFO_EX`
- `get_frame()` 使用 `self._MV_FRAME_OUT_INFO_EX` 而非 `self._ctypes.MV_FRAME_OUT_INFO_EX`

### `UnboundLocalError: selector` — FIXED

`selector = LedSelector6()` 移到 `try` 块之前，新增 `except RuntimeError` 捕获 SDK 错误。

---

## Round 4A 验收标准

| # | 项目 | 状态 |
|---|------|------|
| 1 | MVS SDK import OK | ⬜ |
| 2 | Hikrobot camera enumerated by SDK | ⬜ |
| 3 | OpenCV ROI window opens | ⬜ |
| 4 | breadboard_roi.json saved | ⬜ |
| 5 | Realtime 6-led decode runs via --roi-file | ⬜ |
| 6 | 全灭 → 0x00 | ⬜ |
| 7 | 全亮 → 0x3F | ⬜ |
| 8 | D0 → 0x01 | ⬜ |
| 9 | D1 → 0x02 | ⬜ |
| 10 | D2 → 0x04 | ⬜ |
| 11 | REF → 0x08 | ⬜ |
| 12 | SEQ → 0x10 | ⬜ |
| 13 | PAR → 0x20 | ⬜ |
| 14 | sixled_log_summary.py summarizes logs | ⬜ |

**当前不能宣称通过，直到真实日志验证完成。**

---

## 下一步计划

```
Step 1:  确认相机枚举稳定，No camera found 可排查
Step 2:  重新标定 breadboard_roi.json
Step 3:  使用 threshold 40 / exposure 12000 / gain 0 / timeout 5000 跑实测
Step 4:  依次输出 0, 63, 1, 2, 4, 8, 16, 32
Step 5:  每个状态保持 3~5 秒
Step 6:  保存 round4a 日志
Step 7:  sixled_log_summary.py 汇总
Step 8:  根据日志调整 threshold/exposure
Step 9:  如果掉线严重，做最小稳定性增强:
        - consecutive frame error count
        - frame timeout diagnostic
        - optional max-frame-errors
        - optional reopen-on-error
```
