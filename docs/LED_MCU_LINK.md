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

## 推荐硬件

| 硬件 | 说明 |
|------|------|
| Raspberry Pi Pico / RP2040 | 低成本，USB CDC，多 PWM 引脚 |
| STM32F103C8T6 (Blue Pill) | 工业级，丰富外设 |
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
