# FSM 安全设计文档

> **状态**: 软件安全壳（本轮不接真实电机/机构）
> **最后更新**: 2026-06-22
> **轮次**: Round FSM-A — Mission FSM safety hardening

---

## 1. 设计目标

R1MissionFSM 和 R2MissionFSM 是**纯软件安全壳**，核心职责：

```text
视觉消息不能绕过本地安全条件。
非法消息、重复消息、未知消息、低置信度消息不能触发危险动作。
R2 自动行为必须经过 R2MissionFSM guard。
FSM 输出只能是 ActionIntent / 决策意图，不直接驱动电机、机构或危险动作。
```

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────┐
│  操作手输入                                              │
│  (keyboard / gamepad / ROS2 joy)                         │
│    → OperatorCommand                                     │
│      → R1MissionFSM.update(command, sensors) → R1Output  │
│        → MsgID (LED 编码 → STM32 → LED 光码板)           │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  R2 视觉 Pipeline                                        │
│  相机 → AprilTag/ROI → LED 采样 → PatternMapper          │
│    → BeaconDecoder → (DecodedBeacon)                     │
│      → BeaconStabilizer → (稳定的 DecodedBeacon)          │
│        → BeaconEvent 中间层 ←──── NEW                     │
│          → R2MissionFSM.update(event, sensors) → R2Output │
└─────────────────────────────────────────────────────────┘
```

**关键边界**：
- 操作手 **不能** 直接控制 R2
- 操作手 **不能** 直接点灯
- 视觉消息只是事件/观测，不是动作命令
- FSM 输出只是决策意图（ActionIntent），不直接驱动硬件

## 3. 输入分类

FSM 输入分三类，优先级递减：

### A. 安全/系统事件（最高优先级）
```text
ESTOP        — 紧急停止，最高优先，不可被任何消息覆盖
ABORT        — 终止当前任务
HOLD         — 暂停，保持当前位置
ERROR        — 错误状态
RESET/RETRY  — 恢复请求
TIMEOUT      — 超时
CLEAR_ERROR  — 清除错误
```

优先级链：
```text
ESTOP > ABORT > HOLD > ERROR > RETRY > normal mission event
```

### B. 视觉/光码输入（中等优先级，必须经 guard）
```text
msg_id / seq / valid / confidence / timestamp / source
raw_bitmask / mapped_event
```
- 视觉输入**只能**作为候选事件，不能直接触发危险动作
- `PatternMapper` 可输出 `mapped_event`，但 FSM **仍需** guard
- 当前 bitmask 语义仅作测试/示例，非最终比赛协议

### C. 本地传感器/机构 guard（与视觉输入配合使用）
```text
r1_in_start_zone / r1_left_mc / r1_fully_entered_mf
r1_has_weapon / weapon_assembled / weapon_locked
r2_in_start_zone / r2_has_end_effector / r2_ready_to_assemble
r2_has_kfs / r2_in_entry_zone / r2_in_forest / r2_at_exit_zone
r2_in_battle_zone
mechanism_safe / lift_ready / placer_ready / local_estop
```

## 4. 输出边界：ActionIntent

FSM 输出**只能**是 `ActionIntent`（决策意图）：

```python
class ActionIntent(Enum):
    NOOP = auto()                # 无操作
    HOLD_POSITION = auto()       # 保持位置
    ALLOW_NEXT_STAGE = auto()    # 允许进入下一阶段
    REQUEST_RETRY = auto()       # 请求重试
    START_ASSEMBLY_ALIGN = auto() # 开始装配对准
    START_INSERTION = auto()     # 开始插入
    LOCK_WEAPON = auto()         # 锁定兵器
    ENTER_MF = auto()            # 进入梅林
    SEARCH_KFS = auto()          # 搜索 KFS
    ENTER_BATTLE = auto()        # 进入对抗区
    PLACE_KFS = auto()           # 放置 KFS
    ABORT_MOTION = auto()        # 终止运动
    ESTOP_STOP = auto()          # 紧急停止
    REPORT_ERROR = auto()        # 报告错误
```

**注意**：ActionIntent 只是上层决策意图。本轮**不能**接电机、电磁阀、机械臂、ROS2 action 或真实运动控制。

## 5. R1MissionFSM 安全规则

### 5.1 状态列表

| 状态 | 说明 |
|------|------|
| `INIT` | 初始化，等待操作手 START |
| `READY_IN_START_ZONE` | 在启动区就绪 |
| `MC_ASSEMBLING` | 武馆组装中 |
| `WEAPON_ASSEMBLED` | 兵器已组装 |
| `WAIT_R2_ASSEMBLY_DONE` | 等待 R2 完成装配 |
| `READY_TO_LEAVE_MC` | 可以离开武馆 |
| `IN_MF_COLLECTING_R1_KFS` | 在梅林收集 R1 KFS |
| `MF_DONE` | 梅林任务完成 |
| `READY_FOR_BATTLE` | 准备进入对抗 |
| `IN_BATTLE` | 对抗中 |
| `USED_WEAPON_HANDLING` | 已用兵器处理中 |
| `HOLD` | 暂停 |
| `RETRY` | 重试 |
| `ABORT` | 终止 |
| `ESTOP` | 紧急停止 |
| `ERROR` | 错误 |

> 注意：当前 R1 FSM 实际状态为 `WAIT_START, PICK_ROD, ROD_CLAMPED, AT_ASSEMBLY_POSE, INSERT_ALLOWED, WEAPON_LOCKED, R1_CLEAR_MC, R1_IN_MF, HOLD, ERROR`。
> 以上为建议的目标状态，本次仅对现有状态做安全增强，不做大规模重构。

### 5.2 核心 Guard

```text
1. 未组装兵器时，不允许第一次离开武馆。
2. R2 未完成相关协作时，不允许提前进入下一阶段。
3. 已用兵器未处理时，不允许再次使用兵器。
4. 收到未知/非法视觉消息，不改变危险状态。
5. HOLD 状态下普通任务消息不能触发危险动作。
6. ABORT 后只能 reset/retry。
7. ESTOP 最高优先级，进入后普通消息不能恢复。
```

### 5.3 当前 Guard 实现状态

| Guard | R1 FSM | 备注 |
|-------|--------|------|
| ESTOP 最高优先级 | ✅ | 在所有逻辑之前检查 |
| HOLD 阻止普通消息 | ✅ | `hold_requires_reset` |
| ERROR 阻止普通消息 | ✅ | `error_requires_reset` |
| ABORT 有专用状态 | ⚠️ | 当前 ABORT → HOLD，建议增加 ABORT 状态 |
| sensor guard on NEXT | ✅ | 每步均检查本地传感器 |
| 非法传感器不改变状态 | ✅ | 传感器不满足 → HOLD |
| 未知命令忽略 | ✅ | 非 START/NEXT/HOLD/RESET/ABORT → noop |
| RESET 恢复 | ✅ | 回到 WAIT_START |
| 超时处理 | ❌ | 缺少 |
| stale timestamp | ❌ | 缺少 |

## 6. R2MissionFSM 安全规则

### 6.1 状态列表

| 状态 | 说明 |
|------|------|
| `WAIT_R1` | 等待 R1 信号 |
| `PREPARE_HEAD` | 准备抓取头部 |
| `SEARCH_R1_TAG` | 搜索 R1 AprilTag |
| `PRE_INSERT_READY` | 预插入就绪（定义但未使用） |
| `INSERTING` | 插入中 |
| `HEAD_RELEASED` | 头部已释放 |
| `WAIT_R1_CLEAR_MC` | 等待 R1 离开武馆 |
| `READY_TO_LEAVE_MC` | 可以离开武馆 |
| `READY_TO_ENTER_MF` | 可以进入梅林 |
| `HOLD` | 暂停 |
| `ERROR` | 错误 |

### 6.2 必须满足的安全规则

```text
1.  ESTOP 永远最高优先级。
2.  ABORT / HOLD 高于普通视觉消息。
3.  invalid beacon 不改变危险状态。
4.  unknown msg 不改变危险状态。
5.  duplicate seq 不重复触发动作。
6.  confidence 不足不触发状态转移。           ← 本次新增
7.  stale timestamp / 过期消息不触发状态转移。  ← 本次新增
8.  视觉消息只能形成 candidate/event，不直接变成动作。
9.  所有关键动作必须同时满足 local guard。
10. HOLD / ERROR 状态下普通消息不能唤醒危险动作。
11. 只能通过明确 reset/retry/clear_error 恢复。  ← 本次增强
```

### 6.3 当前 Guard 实现状态

| Guard | R2 FSM | 备注 |
|-------|--------|------|
| ESTOP 最高优先级 | ✅ | sensor.estop 在所有逻辑之前 |
| invalid beacon reject | ✅ | `beacon.valid` 检查 |
| unknown msg reject | ✅ | `MsgID(msg_id)` ValueError catch |
| HOLD/ERROR/ABORT override | ✅ | 在 safety gate 之前处理 |
| HOLD/ERROR safety gate | ✅ | 阻止正常消息逃离 HOLD/ERROR |
| INSERT_ALLOWED local sensor gating | ✅ | 所有三个传感器必须就绪 |
| WEAPON_LOCKED timing gating | ✅ | 必须在插入完成后 |
| R1_CLEAR_MC sequence gating | ✅ | 必须在 HEAD_RELEASED 或 WAIT_R1_CLEAR_MC |
| R1_IN_MF sequence gating | ✅ | 必须在 READY_TO_LEAVE_MC |
| Duplicate seq debounce | ✅ | `is_new_event` 检查 |
| confidence 检查 | ❌ | 新增 |
| stale timestamp 检查 | ❌ | 新增 |
| local_estop 检查 | ❌ | 新增 |
| RETRY_RESET 恢复 | ❌ | 被 safety gate 阻止 |
| 超时处理 | ❌ | 缺少 |

## 7. BeaconEvent 中间层

为桥接视觉 Pipeline 和 FSM，新增 `BeaconEvent` 类型：

```python
@dataclass(frozen=True)
class BeaconEvent:
    msg_id: int
    seq: int | None
    valid: bool
    confidence: float
    timestamp: float | None = None
    source: str = "unknown"
    raw_bitmask: int | None = None
    mapped_event: str | None = None
```

**FSM 消费规则**：
1. FSM 必须检查 `valid`
2. FSM 必须检查 `confidence >= MIN_CONFIDENCE`
3. FSM 必须检查 staleness（`now - timestamp < MAX_AGE`）
4. FSM 必须检查 `seq` 去重
5. `mapped_event` 仅供参考，FSM 仍需 guard

## 8. 优先级执行顺序（R2MissionFSM.update）

```text
1. local_estop → ESTOP_STOP, ERROR                     (最高优先)
2. sensor.estop → STOP_ALL, ERROR                       (R1 发出 ESTOP)
3. !beacon.valid → ignore                                (无效信标)
4. unknown msg_id → ignore                               (未知消息)
5. HOLD / ERROR / ABORT msg → safety override            (安全覆盖消息)
6. safety gate: HOLD/ERROR state → hold_active/error_active  (安全门控)
7. confidence < threshold → ignore                       (低置信度)    ← NEW
8. stale timestamp → ignore                              (过期消息)    ← NEW
9. duplicate seq → debounce                               (去重)
10. normal transitions with local guard                   (正常转移)
```

## 9. 当前六灯硬件状态

```text
⚠️ 面包板测试阶段，非最终灯板结构
⚠️ STM32 六灯全部可点亮 (PA0-PA5)
⚠️ Hikrobot 相机 SDK import OK
⚠️ OpenCV ROI 标定流程跑通
⚠️ 尚未完成真实相机六灯 bitmask 稳定验收
⚠️ 不能宣称 M3 完成
⚠️ 不能把 mock/replay/synthetic 结果当真实相机结果
⚠️ 当前不接 ROS2、AprilTag、真实电机动作
```

## 10. 后续接手者应执行

```bash
cd /home/jfcy/rc/robocon_coop_comm
source .venv/bin/activate
git status
python3 -m pytest -q
python tools/hikrobot_6led_live.py --help
python tools/sixled_log_summary.py --help
```

硬件提醒：
```text
当前 STM32 串口默认：/dev/ttyACM0
当前临时 ROI：data/sixled/configs/breadboard_roi.json
breadboard_roi.json 不应提交为最终标定
data/sixled/logs/ 和 data/sixled/frames/ 应保持 ignored
```
