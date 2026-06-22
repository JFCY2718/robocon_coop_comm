# 交接文档 — 下一轮 CC Session 接手指南

> **轮次**: Round FSM-A → Next
> **日期**: 2026-06-22
> **当前状态**: FSM safety hardening 完成，pytest 556 passed

---

## 1. 快速启动

```bash
cd /home/jfcy/rc/robocon_coop_comm
source .venv/bin/activate
git status
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
python tools/hikrobot_6led_live.py --help
python tools/sixled_log_summary.py --help
```

## 2. 当前仓库状态

### 已完成

- ✅ 软件协议与状态机基础 (556 tests passed)
- ✅ STM32F103 + 六灯全部可点亮 (PA0-PA5)
- ✅ M3-1: Hikrobot 三灯识别工程化
- ✅ M3-2: AprilTag 检测 + 透视矫正 + LED ROI（软件）
- ✅ M3-3: R2 FSM HOLD/ERROR 安全门控
- ✅ M3-5: 六灯 ROI 识别 + PatternMapper + 实时工具（软件）
- ✅ **Round FSM-A**: R1/R2 FSM safety hardening
  - R2 FSM: confidence/staleness/low_confidence guard 新增
  - R2 FSM: local_estop 新增
  - R2 FSM: RETRY_RESET 恢复从 HOLD/ERROR
  - R1 FSM: ABORT 状态新增
  - R1 FSM: local_estop 新增
  - R1 FSM: RETRY 恢复从 ABORT
  - R1 FSM: 46 安全测试
  - R2 FSM: 151 安全测试
  - BeaconEvent 中间层（视觉→FSM 桥接）
  - ActionIntent 枚举（FSM 输出意图，不直接驱动硬件）
  - FSM 安全仿真 demo（26 场景全绿）

### 尚未完成

- ⚠️ **面包板测试阶段**，非最终灯板结构
- ⚠️ 真实相机六灯 bitmask 稳定验收尚未完成
- ⚠️ M3 整体不能打勾
- ⚠️ 不能把 mock/replay/synthetic 结果当真实结果

## 3. FSM 安全架构提醒

```text
当前 FSM 只是软件安全壳。
当前 FSM 不直接控制真实动作。
视觉消息只是输入事件，不是动作命令。
所有关键状态转移都需要 local guard。
ESTOP > ABORT > HOLD > ERROR > RETRY > normal mission event。
```

### R1MissionFSM
- 11 个状态（含 ABORT）
- 输入: `OperatorCommand` + `R1Sensors`
- 输出: `R1Output` (state, msg_id, seq, reason)
- 操作手→R1 FSM→MsgID→LED 编码

### R2MissionFSM
- 11 个状态
- 输入: `DecodedBeacon` / `BeaconEvent` + `R2Sensors`
- 输出: `R2Output` (state, action_hint, reason)
- 视觉→Decoder→Stabilizer→BeaconEvent→R2 FSM

## 4. 重要文件路径

| 文件 | 说明 |
|------|------|
| `robocon_coop_comm/r1_fsm.py` | R1 任务状态机 |
| `robocon_coop_comm/r2_fsm.py` | R2 任务状态机 |
| `robocon_coop_comm/beacon_types.py` | BeaconEvent, ActionIntent |
| `robocon_coop_comm/beacon_stabilizer.py` | 信标稳定化 |
| `robocon_coop_comm/pattern_mapper.py` | LED 模式映射器 |
| `test/test_r1_fsm.py` | R1 FSM 测试 (46 tests) |
| `test/test_r2_fsm.py` | R2 FSM 测试 (151 tests) |
| `docs/FSM_SAFETY_DESIGN.md` | FSM 安全设计文档 |
| `docs/R1_R2_MISSION_FSM.md` | R1/R2 FSM 详细文档 |
| `docs/ROADMAP.md` | 开发路线图 |
| `robocon_coop_comm/demo_fsm_safety.py` | FSM 安全仿真 demo |

## 5. 硬件调试提醒

```text
当前 STM32 串口默认：/dev/ttyACM0
当前临时 ROI：data/sixled/configs/breadboard_roi.json
breadboard_roi.json 不应提交为最终标定
data/sixled/logs/ 和 data/sixled/frames/ 应保持 ignored
```

### Hikrobot 相机环境

```bash
export MVCAM_COMMON_RUNENV=/opt/MVS/lib
export PYTHONPATH=/opt/MVS/Samples/64/Python/MvImport:$PYTHONPATH
export LD_LIBRARY_PATH=/opt/MVS/lib/64:/opt/MVS/bin:$LD_LIBRARY_PATH
```

## 6. 下一轮建议任务

1. **继续 Round 4A**: 真实相机六灯 bitmask 稳定性测试（0x00→0x3F 全覆盖）
2. **确定最终六灯比赛语义**: 当前 bitmask 语义仅作测试/示例
3. **BeaconEvent 集成到视觉 pipeline**: 当前视觉 pipeline 用 `protocol.DecodedBeacon`，需要中间适配到 `BeaconEvent`
4. **R2 FSM timeout 检测**: 长时间无消息应进入 HOLD
5. **R2 FSM PRE_INSERT_READY 状态**: 定义但未使用，需决策是否保留
6. **扩大 R2 FSM 状态覆盖**: MF（梅林）和 Battle（对抗区）阶段
7. **R1 FSM 扩大状态覆盖**: 当前只有 MC/MF 基础状态

## 7. 禁止事项（本轮及之后）

```text
不接真实电机。
不接真实机械臂。
不接 ROS2。
不接 AprilTag（除非明确进入对应阶段）。
不改 Hikrobot 相机主链路（除非只是文档引用）。
不改 STM32 固件。
不锁死最终六灯比赛语义。
不把 bitmask 直接映射为危险动作。
不把视觉消息直接变成电机控制。
不宣称 M3 完成。
不宣称真实比赛可用。
```
