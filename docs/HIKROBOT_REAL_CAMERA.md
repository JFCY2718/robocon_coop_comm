# Hikrobot 真实相机调试

## 前置条件

### 硬件

- Hikrobot USB3.0 / GigE 工业相机（已测试型号：MV-CA050-20UC）
- 相机连接到运行 Ubuntu 22.04 的 PC
- STM32F103 三灯信标板（D0/D1/D2）已烧录固件并上电

### 软件依赖

```bash
# 1. 安装 Hikrobot MVS SDK
#    从 Hikrobot 官网下载 Linux 版 MVS，解压到 /opt/MVS
tar -xzf MVS-*.tar.gz -C /opt/

# 2. 安装 Python 依赖
source .venv/bin/activate
pip install -e ".[vision]"

# 3. 设置环境变量
export MVCAM_COMMON_RUNENV=/opt/MVS/lib
export PYTHONPATH=/opt/MVS/Samples/64/Python/MvImport:$PYTHONPATH
export LD_LIBRARY_PATH=/opt/MVS/lib/64:/opt/MVS/bin:$LD_LIBRARY_PATH
```

建议将环境变量写入 `.envrc` 或 `.venv/bin/activate` 尾部。

## 运行命令

### 交互式三灯解码（推荐调试入口）

```bash
python tools/hikrobot_3led_live.py
```

### 带参数运行

```bash
# 调整阈值和 ROI 大小
python tools/hikrobot_3led_live.py --threshold 100 --roi-size 20

# 调整曝光和增益
python tools/hikrobot_3led_live.py --exposure 8000 --gain 3.0

# 输出调试日志
python tools/hikrobot_3led_live.py --log /tmp/beacon_log.csv
python tools/hikrobot_3led_live.py --log /tmp/beacon_log.jsonl --log-format jsonl
```

### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--threshold` | 120 | 亮度阈值 (0-255)，高于此值判定 LED 亮 |
| `--roi-size` | 24 | ROI 采样方框边长 (px) |
| `--exposure` | 10000 | 曝光时间 (µs) |
| `--gain` | 5.0 | 模拟增益 |
| `--timeout` | 1000 | 帧抓取超时 (ms) |
| `--log` | (无) | 日志输出路径，以 `.csv` 或 `.jsonl` 结尾 |
| `--log-format` | csv | 日志格式：`csv` 或 `jsonl` |

### 键盘操作

| 按键 | 功能 |
|------|------|
| 鼠标左键点击 | 依次设定 D0 → D1 → D2 LED 中心位置 |
| `+` / `=` | 阈值 +5 |
| `-` | 阈值 -5 |
| `r` | 重置 LED 选点和 SEQ 跟踪 |
| `q` | 退出 |

## 操作步骤

1. 确认 STM32 信标板已上电，LED 按当前 msg_id 点亮。
2. 启动脚本：
   ```bash
   python tools/hikrobot_3led_live.py
   ```
3. 依次点击图像中 D0、D1、D2 LED 的中心位置。
4. 观察终端输出的解码结果和窗口中的 ROI 叠加。
5. 使用 `+`/`-` 调整阈值直到 D0/D1/D2 判定准确。
6. 可通过 Hikrobot MVS 客户端预先调整曝光/增益/白平衡。
7. 如需记录数据，加 `--log` 参数：
   ```bash
   python tools/hikrobot_3led_live.py --log /tmp/test.csv
   ```

## 日志格式

### CSV

```csv
timestamp,msg_id,seq,valid,confidence,latency_ms,D0,D1,D2,b_D0,b_D1,b_D2
1720000000.123456,4,1,1,1.0000,12.345,0,0,1,15.2,18.1,210.5
```

### JSONL

```json
{"timestamp": 1720000000.123456, "msg_id": 4, "seq": 1, "valid": true, "confidence": 1.0, "latency_ms": 12.345, "D0": 0, "D1": 0, "D2": 1, "b_D0": "15.2", "b_D1": "18.1", "b_D2": "210.5"}
```

## 误码测试方法

### 静态误码测试

1. 固定 STM32 发送单一 msg_id（如 `HOLD` / msg_id=1）。
2. 运行 100 帧以上，记录日志：
   ```bash
   python tools/hikrobot_3led_live.py --log /tmp/static_test.csv
   ```
3. 分析日志：
   ```bash
   # 统计误码帧数
   grep -v timestamp /tmp/static_test.csv | awk -F, '$4==0' | wc -l
   ```

### 动态误码测试

1. 使用 `r1_beacon_control.py` 每 2 秒切换一次 msg_id：
   ```bash
   while true; do
     for cmd in hold rod insert mf; do
       python tools/r1_beacon_control.py --port /dev/ttyACM0 --command $cmd
       sleep 2
     done
   done
   ```
2. 同时运行解码器记录日志：
   ```bash
   python tools/hikrobot_3led_live.py --log /tmp/dynamic_test.csv
   ```
3. 分析解码稳定性：
   ```bash
   # 统计每次切换后的稳定帧数（valid=1 的连续帧数）
   python -c "
   import csv
   with open('/tmp/dynamic_test.csv') as f:
       reader = csv.DictReader(f)
       valid_count = sum(1 for row in reader if row['valid'] == '1')
   print(f'Valid frames: {valid_count}')
   "
   ```

### 验收标准 (M3)

- 1.5m 距离、±45° 角度
- 100 次 msg_id 切换
- 误码率为 0（稳定后无错误解码）

## 无 SDK 环境运行

如果当前环境没有 Hikrobot SDK，以下组件仍可正常运行：

```bash
# 单元测试（含 FakeFrameProvider 测试）
./tools/test.sh

# 纯软件 demo
python -m robocon_coop_comm.demo_cli
python -m robocon_coop_comm.demo_r2_vision_pipeline
python -m robocon_coop_comm.demo_cv
```

仅在 `import HikrobotFrameProvider` 或调用 `provider.open()` 时才会尝试加载 MVS SDK。

## 模块架构

```
HikrobotFrameProvider (hikrobot_frame_provider.py)
  ├── 相机枚举 / 打开 / 启停 / 关闭
  ├── 帧抓取 → BeaconFrame
  │
ThreeLedRoiDecoder (hikrobot_frame_provider.py)
  ├── 3-LED ROI 采样
  ├── SEQ 跟踪（msg_id 变化时翻转）
  ├── REF/SEQ/PAR 合成（兼容 8-LED 协议）
  └── 输出 DecodedBeacon → BeaconStabilizer → R2 FSM

FakeFrameProvider (fake_frame_provider.py)
  └── 测试用合成帧，无需相机

FrameLogger (frame_logger.py)
  └── CSV / JSONL 调试日志
```

### 3-LED 解码说明

当前硬件仅使用 D0/D1/D2 三颗 LED，缺少专用的 REF、SEQ、PAR LED。`ThreeLedRoiDecoder` 通过以下策略兼容 8-LED 协议：

- **REF**: 合成设为 1。
- **SEQ**: 检测 msg_id 变化时自动翻转。
- **PAR**: 根据数据位和 SEQ 自动计算。
- **D3/D4**: 设为 0（msg_id 限制在 0-7）。

此策略可无缝接入现有 `BeaconStabilizer` → `R2MissionFSM` pipeline。

下一阶段升级到 6-LED 硬件后，REF/SEQ/PAR 将直接从图像采样，不再需要合成。
