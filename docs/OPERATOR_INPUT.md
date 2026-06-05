# Operator Input Abstraction

## 目的

把键盘、手柄、串口遥控器等输入统一抽象为 `OperatorCommand`，
再由 R1 状态机处理。

## 安全保证

- `OperatorCommand` **不是** R2 控制命令。
- `OperatorCommand` **不包含** msg_id。
- `OperatorCommand` **不包含** LED bits。
- `OperatorCommand` **只请求** R1 状态机改变状态。

## 链路图

```
Keyboard / Controller
  ↓
OperatorSession
  ↓
OperatorCommand (mode, request, target_grid, arm_enabled)
  ↓
request_to_r1_command()
  ↓
R1 FSM (sensors guard transitions)
  ↓
msg_id
  ↓
LedMcuClient -> LED MCU -> LED bits
```

## 当前键盘映射

| 按键 | 请求 |
|------|------|
| `s` | START |
| `n` | NEXT |
| `h` | HOLD |
| `a` | ABORT |
| `r` | RESET |
| `c` | CONFIRM |
| `[` | TARGET_PREV |
| `]` | TARGET_NEXT |
| `e` | ARM_ENABLE |
| `d` | ARM_DISABLE |
| `?` | STATUS (mode cycle) |

## 小按键遥控器建议

| 按钮 | 功能 |
|------|------|
| A | NEXT |
| B | HOLD |
| C | MODE |
| D | TARGET+ |
| E | TARGET- |
| F | ARM |

## 安全原则

1. **危险动作需要 ARM**：ATTACK_ZONE、LIFT_TOP 模式的 CONFIRM 需要 arm_enabled=True。
2. **传感器守卫**：操作手请求必须经过 R1 状态机传感器条件检查。
3. **不直接控制 LED**：操作手不能绕过 R1 状态机直接点亮 LED。
4. **不直接控制 R2**：操作手输入只影响 R1，R2 根据光码和自身状态自主决策。

## 运行命令

```bash
python -m robocon_coop_comm.demo_operator_pipeline
./tools/demo_operator_pipeline_check.sh
make demo-operator-check
```
