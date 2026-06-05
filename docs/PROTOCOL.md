# R1/R2 光学事件通信协议 V0.1

## 1. 设计目标

该协议用于 ROBOCON 2026「武林探秘」中 R1/R2 的事件级协作通信。它不是实时遥控链路，只传递关键状态，例如：

- R1 已夹住长杆
- R1 已到组装位
- R1 长杆姿态锁定，允许 R2 插入
- R1 检测到兵器锁定
- R1 已完全离开武馆
- R1 已完全进入梅林

## 2. LED 排列

```text
REF D0 D1 D2 D3 D4 SEQ PAR
```

| LED | 作用 |
|---|---|
| REF | 常亮参考灯，用于视觉阈值估计 |
| D0-D4 | 5 位消息编号，D0 为最低位 |
| SEQ | 事件序号位，新事件翻转一次 |
| PAR | 偶校验位 |

校验规则：

```text
D0 ^ D1 ^ D2 ^ D3 ^ D4 ^ SEQ ^ PAR == 0
```

## 3. 消息表

| msg_id | 名称 | 含义 |
|---:|---|---|
| 0 | IDLE | 空闲 |
| 1 | HOLD | 保持，不要执行新动作 |
| 2 | R1_ROD_CLAMPED | R1 已夹住长杆 |
| 3 | R1_AT_ASSEMBLY_POSE | R1 已到组装位 |
| 4 | INSERT_ALLOWED | R1 长杆姿态锁定，允许 R2 插入 |
| 5 | WEAPON_LOCKED | R1 检测到兵器组装完成 |
| 6 | R1_CLEAR_MC | R1 已完全离开武馆 |
| 7 | R1_IN_MF | R1 已完全进入梅林 |
| 8 | R1_ATTACK_READY | R1 已到对抗区协作位 |
| 9 | R1_WAIT_R2 | R1 等待 R2 |
| 10 | LIFT_DOCK_READY | R1 举升平台准备好 |
| 11 | R2_ON_LIFT_DETECTED | R1 检测到 R2 已上平台 |
| 12 | TOP_RELEASE_ALLOWED | 顶层释放允许 |
| 13 | DESCEND_ALLOWED | 下降/撤离允许 |
| 14 | ABORT_CURRENT_TASK | 放弃当前动作 |
| 15 | RETRY_RESET | 重试流程 |
| 20-28 | GRID_TARGET_1~9 | 九宫格目标格 |
| 29 | DEBUG | 调试 |
| 30 | ERROR | 错误，R2 安全等待 |
| 31 | TEST | 测试 |

## 4. 接收端判定

R2 只有在以下条件同时满足时才接受消息：

1. AprilTag 已识别为己方 R1。
2. LED ROI 完整可见。
3. REF 灯有效。
4. PAR 校验通过。
5. 连续 3~5 帧一致。
6. R2 当前状态允许响应该消息。
7. R2 本地传感器条件满足。

## 5. 遥控器关系

遥控器不直接控制 LED，也不直接控制 R2。遥控器只向 R1 状态机发送请求，例如 `NEXT`、`HOLD`。R1 状态机根据传感器条件决定是否输出对应 `msg_id`。
