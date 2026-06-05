# R1 LED Beacon MCU Firmware

R1 LED 光码板 MCU 固件。

## 功能

接收 R1 主控通过串口发送的帧：

```
AA 55 msg_id seq brightness checksum
```

解码后控制 8 颗 LED：

```
REF D0 D1 D2 D3 D4 SEQ PAR
```

## 通信链路

```
R1 主控 (USB/UART)
  ↓  serial_frame 协议
LED MCU (本固件)
  ↓  GPIO / PWM
REF D0 D1 D2 D3 D4 SEQ PAR (LED)
```

这是 **R1 内部有线通信**，不是 R1/R2 无线通信。

## 推荐硬件

- Raspberry Pi Pico / RP2040
- STM32 (如 STM32F103C8T6)
- Arduino Nano
- ESP32 **仅在关闭 Wi-Fi / Bluetooth 时**作为普通 MCU 使用

## 编译

将 `arduino_led_beacon_mcu.ino` 复制到 Arduino IDE 或 PlatformIO 项目中，选择对应板卡编译上传。

## 串口参数

- 波特率: 115200
- 数据格式: 8N1
- 无流控
