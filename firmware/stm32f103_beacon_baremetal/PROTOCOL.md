# STM32F103 LED Beacon 串口协议

## 请求帧（R1 主控 → MCU）

```
Byte:  0     1     2       3    4          5
     ┌─────┬─────┬───────┬─────┬──────────┬──────────┐
     │ AA  │ 55  │msg_id │ seq │brightness│ checksum │
     └─────┴─────┴───────┴─────┴──────────┴──────────┘
```

| 字节 | 字段 | 值域 | 说明 |
|------|------|------|------|
| 0 | Header | `0xAA` | 帧头第一字节 |
| 1 | Header | `0x55` | 帧头第二字节 |
| 2 | msg_id | 0–7 (当前用) | 事件 ID，对应 `protocol.MsgID` |
| 3 | seq | 0 或 1 | 事件翻转位，R1 状态机每次切换事件时翻转 |
| 4 | brightness | 0–255 | LED 亮度。**当前固件不做 PWM，仅保留协议兼容** |
| 5 | checksum | 0–255 | `checksum = msg_id ^ seq ^ brightness` (XOR) |

帧总长：**6 字节**。

## ACK 帧（MCU → R1 主控）

```
Byte:  0     1       2
     ┌─────┬───────┬─────┐
     │ CC  │msg_id │ seq │
     └─────┴───────┴─────┘
```

| 字节 | 字段 | 说明 |
|------|------|------|
| 0 | `0xCC` | ACK 标识 |
| 1 | msg_id | 回显收到的 msg_id |
| 2 | seq | 回显收到的 seq |

ACK 仅在 **帧格式正确 + checksum 校验通过** 时回复。

## 事件表

| msg_id | 枚举名 | 含义 | D2 D1 D0 |
|--------|--------|------|----------|
| 0 | `IDLE` | 空闲 | 0 0 0 |
| 1 | `HOLD` | 暂停 | 0 0 1 |
| 2 | `R1_ROD_CLAMPED` | 杆已夹紧 | 0 1 0 |
| 3 | `R1_AT_ASSEMBLY_POSE` | 到达装配位姿 | 0 1 1 |
| 4 | `INSERT_ALLOWED` | 允许插杆 | 1 0 0 |
| 5 | `WEAPON_LOCKED` | 武器已锁定 | 1 0 1 |
| 6 | `R1_CLEAR_MC` | R1 清场完成 | 1 1 0 |
| 7 | `R1_IN_MF` | R1 进入武馆 | 1 1 1 |

## LED 显示逻辑

六灯全部定义，当前三灯模式仅接 D0/D1/D2。

```
D0  = (msg_id >> 0) & 1    # msg_id 最低位
D1  = (msg_id >> 1) & 1    # msg_id 第1位
D2  = (msg_id >> 2) & 1    # msg_id 第2位
REF = 1                     # 参考灯，常亮
SEQ = seq & 1               # 序列位
PAR = D0 ^ D1 ^ D2 ^ SEQ    # 偶校验
```

- **三灯模式（当前已验证）**：D0/D1/D2 接 LED，REF/SEQ/PAR 不接任何外设。
- **六灯模式（下一阶段）**：全部六灯接齐，R2 通过摄像头解码完整的 6-bit 帧。

## Checksum 校验

```
checksum == (msg_id ^ seq ^ brightness)
```

- 校验通过 → 更新 LED + 回复 ACK
- 校验失败 → **不更新 LED，不回复 ACK**，丢弃帧

## 示例

### 例 1：INSERT_ALLOWED

```
请求帧: AA 55 04 01 C8 CD
        checksum = 4 ^ 1 ^ 200 = 205 (0xCD) ✓

ACK:    CC 04 01

LED:    msg_id=4 → D2=1 D1=0 D0=0 → D2 亮
        seq=1 → SEQ=1
        PAR = 1^0^0^1 = 0
```

### 例 2：HOLD

```
请求帧: AA 55 01 00 C8 C9
        checksum = 1 ^ 0 ^ 200 = 201 (0xC9) ✓

ACK:    CC 01 00

LED:    D0 亮，D1/D2 灭
```

### 例 3：checksum 错误

```
请求帧: AA 55 04 01 C8 00    ← checksum 错误

→ 无 ACK，LED 保持不变
```
