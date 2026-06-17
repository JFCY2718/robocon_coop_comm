# R1 LED MCU 链路文档

## 系统位置

```
R1 状态机
  ↓
msg_id + seq
  ↓
serial_frame.encode_frame()
  ↓
LedMcuClient
  ↓
UART / USB CDC
  ↓
LED MCU
  ↓
REF D0 D1 D2 D3 D4 SEQ PAR
  ↓
R2 摄像头识别
```

## 说明

这是 **R1 内部通信**，不是 R1/R2 通信。

- `serial_frame.py` 定义帧格式（AA 55 msg_id seq brightness checksum）
- `serial_transport.py` 定义传输抽象（内存假串口 / 真实 pyserial）
- `led_mcu_client.py` 封装高层发送逻辑
- `firmware/led_beacon_mcu/` 是 MCU 端 Arduino 固件骨架

不违反 R1/R2 不得无线通信的规则。
武馆组装阶段仍然没有 R1/R2 直接接触通信。

## ✅ 已验证硬件 (2026-06-17)

以下硬件已经通过实机串口帧收发验证：

| 硬件 | 说明 |
|------|------|
| STM32F103C8T6 (Blue Pill) | MCU 端，USART1 接收帧并返回 ACK |
| ST-LINK/V2.1 | 烧录器 + USB 虚拟串口 (VCP) |
| /dev/ttyACM0 | 系统枚举的串口设备 |

### 引脚接线

**三灯接线：**

| STM32 GPIO | 连接 |
|------------|------|
| PA0 | → 电阻 → D0 LED 长脚，短脚 → GND |
| PA1 | → 电阻 → D1 LED 长脚，短脚 → GND |
| PA2 | → 电阻 → D2 LED 长脚，短脚 → GND |
| PA3 | REF，预留 |
| PA4 | SEQ，预留 |
| PA5 | PAR，预留 |

**串口接线：**

| ST-LINK | STM32 |
|---------|-------|
| TX | PA10 / USART1_RX |
| RX | PA9 / USART1_TX |
| GND | GND |

### 已验证测试命令

发送单帧并验证 ACK：

```bash
python tools/send_3led_msg.py --port /dev/ttyACM0 --msg-id 4 --seq 1 --brightness 200
```

期望输出：
```
frame=AA 55 04 01 C8 CD
ack=CC 04 01
```

### 已验证命令集

| 命令 | msg_id | 帧 | ACK |
|------|--------|-----|-----|
| `msg_id=1` | HOLD | AA 55 01 00 C8 C9 | CC 01 00 |
| `msg_id=2` | R1_ROD_CLAMPED | AA 55 02 01 C8 CB | CC 02 01 |
| `msg_id=4` | INSERT_ALLOWED | AA 55 04 01 C8 CD | CC 04 01 |
| `msg_id=7` | R1_IN_MF | AA 55 07 00 C8 CF | CC 07 00 |

### R1 Beacon 交互控制

```bash
# 交互模式
python tools/r1_beacon_control.py --port /dev/ttyACM0

# 单次发送
python tools/r1_beacon_control.py --port /dev/ttyACM0 --command insert
python tools/r1_beacon_control.py --dry-run --command insert
```

交互输入命令：`hold` `rod` `pose` `insert` `locked` `clear` `mf`

## 推荐硬件

| 硬件 | 说明 |
|------|------|
| Raspberry Pi Pico / RP2040 | 低成本，USB CDC，多 PWM 引脚 |
| STM32F103C8T6 (Blue Pill) ✅ 已验证 | 工业级，丰富外设 |
| Arduino Nano | 简单易用，USB 转串口 |
| ESP32 | **仅在关闭 Wi-Fi / Bluetooth 时**作为普通 MCU 使用 |

## 推荐串口参数

- 波特率: 115200
- 数据格式: 8N1
- 无流控

## 接线建议

```
R1 主控 (USB/UART TX) ──→ MCU (RX)
R1 主控 GND            ──→ MCU GND (必须共地)

MCU GPIO ──→ 限流电阻 ──→ LED
```

- 高亮 LED 或 LED 模块可使用 MOSFET / 三极管驱动
- R1 主控与 MCU 必须共地，除非使用隔离模块

## 调试顺序

1. **MemorySerialTransport** — 用单元测试验证帧编码/传输逻辑
2. **USB CDC loopback** — 用 `tools/send_led_frame.py --port /dev/ttyACM0` 发送，串口助手验证
3. **接 MCU** — MCU 固件解析帧并输出 LED 状态
4. **接真实 LED 光码板** — 完整链路验证

## 常用命令

```bash
# 生成一帧 hex（不开串口）
python tools/send_led_frame.py --msg-id 4 --seq 1 --brightness 200

# 发送到真实串口（需要 pyserial）
python tools/send_led_frame.py --msg-id 4 --seq 1 --brightness 200 --port /dev/ttyACM0
```
