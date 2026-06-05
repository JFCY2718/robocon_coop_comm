# MCU 串口帧协议

## 用途

`serial_frame.py` 实现 R1 主控板发送给 LED MCU 的串口帧编码与解码。

它用于 R1 主控 → LED 光码板的**内部有线通信**，不涉及 R1/R2 之间的无线通信。

## 帧格式

```
AA 55 msg_id seq brightness checksum
```

| 字段 | 长度 | 范围 | 说明 |
|------|------|------|------|
| Header | 2 bytes | 固定 `AA 55` | 帧头 |
| msg_id | 1 byte | 0~31 | 对应 `protocol.MsgID` |
| seq | 1 byte | 0 或 1 | 序列位 |
| brightness | 1 byte | 0~255 | LED 亮度 |
| checksum | 1 byte | 0~255 | XOR 校验 |

## Checksum 计算

```
checksum = msg_id ^ seq ^ brightness
```

## 示例

编码 `msg_id=4, seq=1, brightness=200`：

```
checksum = 4 ^ 1 ^ 200 = 205 (0xCD)
帧: AA 55 04 01 C8 CD
```

## 系统位置

```
R1 状态机
  ↓
BeaconCommand / msg_id
  ↓
serial_frame.encode_frame()
  ↓
UART / USB CDC / CAN转串口
  ↓
LED MCU
  ↓
真实 LED 光码板
```

## 与 R1/R2 通信规则的关系

`serial_frame.py` **不是** R1/R2 通信协议本身。

它是 R1 主控到 R1 自身 LED MCU 的内部有线通信协议，用于将状态机输出的 `msg_id` 通过串口帧发送给 LED 控制板。

这不违反 R1/R2 不得无线通信的规则。
