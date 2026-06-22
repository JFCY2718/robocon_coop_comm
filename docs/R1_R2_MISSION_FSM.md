# R1/R2 Mission FSM 状态机文档

> **状态**: 软件安全壳（不接真实电机/机构）
> **最后更新**: 2026-06-22

---

## R1MissionFSM

### 状态列表

| 状态 | 枚举值 | 说明 |
|------|--------|------|
| `WAIT_START` | 1 | 等待操作手 START |
| `PICK_ROD` | 2 | 取杆 |
| `ROD_CLAMPED` | 3 | 杆已夹紧 |
| `AT_ASSEMBLY_POSE` | 4 | 在装配位置 |
| `INSERT_ALLOWED` | 5 | 允许插入（R2） |
| `WEAPON_LOCKED` | 6 | 兵器已锁定 |
| `R1_CLEAR_MC` | 7 | R1 已离开武馆 |
| `R1_IN_MF` | 8 | R1 在梅林 |
| `HOLD` | 9 | 暂停 |
| `ABORT` | 10 | 终止（需 RETRY 恢复） |
| `ERROR` | 11 | 错误（需 RESET 恢复） |

### 输入

| 输入 | 类型 | 说明 |
|------|------|------|
| `command` | `OperatorCommand` | 操作手指令：START, NEXT, HOLD, RESET, ABORT, RETRY, NONE |
| `sensors` | `R1Sensors` | 本地传感器快照 |

### 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| `R1Output` | frozen dataclass | `state`, `msg_id`, `seq`, `reason` |

### 优先级链

```
1. local_estop → ERROR, MsgID.ERROR
2. sensor.estop → ERROR, MsgID.ERROR
3. RESET → WAIT_START (任意状态)
4. RETRY → WAIT_START (仅 ABORT 状态)
5. HOLD → HOLD, MsgID.HOLD
6. ABORT → ABORT, MsgID.ABORT_CURRENT_TASK
7. HOLD/ABORT/ERROR 安全门控 → 阻止普通指令
8. START → PICK_ROD (仅 WAIT_START)
9. NEXT → sensor-gated 转移
```

### 转移表

| 当前状态 | 指令 | 传感器条件 | 下一状态 | msg_id |
|----------|------|------------|----------|--------|
| WAIT_START | START | — | PICK_ROD | IDLE |
| WAIT_START | NEXT | — | PICK_ROD | IDLE |
| PICK_ROD | NEXT | rod_clamped | ROD_CLAMPED | R1_ROD_CLAMPED |
| ROD_CLAMPED | NEXT | in_assembly_pose | AT_ASSEMBLY_POSE | R1_AT_ASSEMBLY_POSE |
| AT_ASSEMBLY_POSE | NEXT | rod_clamped + rod_pose_locked + chassis_stopped | INSERT_ALLOWED | INSERT_ALLOWED |
| INSERT_ALLOWED | NEXT | weapon_locked | WEAPON_LOCKED | WEAPON_LOCKED |
| WEAPON_LOCKED | NEXT | r1_clear_mc | R1_CLEAR_MC | R1_CLEAR_MC |
| R1_CLEAR_MC | NEXT | r1_in_mf | R1_IN_MF | R1_IN_MF |

---

## R2MissionFSM

### 状态列表

| 状态 | 枚举值 | 说明 |
|------|--------|------|
| `WAIT_R1` | 1 | 等待 R1 信号 |
| `PREPARE_HEAD` | 2 | 准备抓取头部 |
| `SEARCH_R1_TAG` | 3 | 搜索 R1 AprilTag |
| `PRE_INSERT_READY` | 4 | 预插入就绪（定义但未使用） |
| `INSERTING` | 5 | 插入中 |
| `HEAD_RELEASED` | 6 | 头部已释放 |
| `WAIT_R1_CLEAR_MC` | 7 | 等待 R1 离开武馆 |
| `READY_TO_LEAVE_MC` | 8 | 可以离开武馆 |
| `READY_TO_ENTER_MF` | 9 | 可以进入梅林 |
| `HOLD` | 10 | 暂停 |
| `ERROR` | 11 | 错误 |

### 输入

| 输入 | 类型 | 说明 |
|------|------|------|
| `beacon` | `DecodedBeacon` / `BeaconEvent` / duck-typed | R1 信标消息 |
| `sensors` | `R2Sensors` | 本地传感器快照 |

### 输出

| 输出 | 类型 | 说明 |
|------|------|------|
| `R2Output` | frozen dataclass | `state`, `action_hint`, `reason` |

### 优先级链（完整）

```
1.  local_estop → ERROR, "stop_all"
2.  sensor.estop → ERROR, "stop_all"
3.  !beacon.valid → "ignore", "invalid_beacon"
4.  unknown msg_id → "ignore", "unknown_msg"
5.  confidence < min_confidence → "ignore", "low_confidence"        ← NEW
6.  stale timestamp → "ignore", "stale_beacon"                       ← NEW
7.  HOLD/ERROR/ABORT/RETRY_RESET → safety override
8.  safety gate: HOLD/ERROR blocks normal messages
9.  normal transitions with local guard + duplicate seq debounce
```

### 安全覆盖消息

以下消息可以改变 HOLD/ERROR 状态：

| 消息 | HOLD → | ERROR → |
|------|--------|---------|
| `HOLD` | HOLD | HOLD |
| `ERROR` | ERROR | ERROR |
| `ABORT_CURRENT_TASK` | HOLD | HOLD |
| `RETRY_RESET` | WAIT_R1 | WAIT_R1 |

### 关键 Guard

| Guard | 状态 | 说明 |
|-------|------|------|
| local_estop | 所有状态 | 本地急停按钮，最高优先级 |
| confidence ≥ 0.7 | 所有状态 | 低于阈值忽略 |
| timestamp ≤ 2s | 所有状态 | 过期信标忽略 |
| HOLD/ERROR safety gate | HOLD, ERROR | 普通消息无法逃逸 |
| head_grabbed | WAIT_R1 等 | INSERT_ALLOWED 需要 |
| r1_tag_visible | WAIT_R1 等 | INSERT_ALLOWED 需要 |
| pre_insert_pose_ok | WAIT_R1 等 | INSERT_ALLOWED 需要 |
| insertion_motion_done / INSERTING | 所有 | WEAPON_LOCKED 需要 |
| HEAD_RELEASED / WAIT_R1_CLEAR_MC | — | R1_CLEAR_MC 需要 |
| READY_TO_LEAVE_MC | — | R1_IN_MF 需要 |

### 转移表

| 当前状态 | msg | 传感器条件 | 下一状态 | action_hint |
|----------|-----|------------|----------|-------------|
| WAIT_R1 | R1_ROD_CLAMPED | — | PREPARE_HEAD | grab_head |
| PREPARE_HEAD | R1_AT_ASSEMBLY_POSE | head_grabbed | SEARCH_R1_TAG | search_r1_tag |
| SEARCH_R1_TAG | INSERT_ALLOWED | head_grabbed + r1_tag_visible + pre_insert_pose_ok | INSERTING | insert_head |
| INSERTING | WEAPON_LOCKED | — | HEAD_RELEASED | release_head_and_retreat |
| HEAD_RELEASED | R1_CLEAR_MC | — | READY_TO_LEAVE_MC | leave_mc |
| WAIT_R1_CLEAR_MC | R1_CLEAR_MC | — | READY_TO_LEAVE_MC | leave_mc |
| READY_TO_LEAVE_MC | R1_IN_MF | — | READY_TO_ENTER_MF | enter_mf |
