# MCU Pipeline Simulation

## 目的

在没有真实硬件时，验证 R1 状态机到 LED MCU 的完整链路逻辑是否正确。

## 链路图

```
R1 FSM
  ↓
LedMcuClient
  ↓
MemorySerialTransport
  ↓
LedMcuSimulator (模拟 Arduino 固件)
  ↓
LED bits (REF D0 D1 D2 D3 D4 SEQ PAR)
```

## 说明

`LedMcuSimulator` 用 Python 实现了 `firmware/led_beacon_mcu/arduino_led_beacon_mcu.ino` 的核心逻辑：

- 从字节流中寻找帧头 `0xAA 0x55`
- 读取并校验 `msg_id`, `seq`, `brightness`, `checksum`
- 生成 LED bit 状态，规则与 `protocol.py` 完全一致

## 运行命令

```bash
# 运行完整 pipeline demo
python -m robocon_coop_comm.demo_mcu_pipeline

# 非交互式检查
./tools/demo_mcu_pipeline_check.sh

# Makefile 快捷方式
make demo-mcu
make demo-mcu-check
```

## 预期输出

输出应包含以下关键信息：

- `R1_ROD_CLAMPED`
- `R1_AT_ASSEMBLY_POSE`
- `INSERT_ALLOWED`
- `WEAPON_LOCKED`
- `R1_CLEAR_MC`
- `R1_IN_MF`
- `AA 55` (帧 hex)
- `REF`, `PAR` (LED bits)

## 与比赛规则的关系

这是 **R1 内部主控到 LED MCU 的有线链路模拟**，不是 R1/R2 无线通信。
它不会违反比赛规则。

## 下一步硬件替换

| 软件组件 | 替换为 |
|----------|--------|
| `MemorySerialTransport` | `PySerialTransport` (真实串口) |
| `LedMcuSimulator` | 真实 MCU 固件 (`arduino_led_beacon_mcu.ino`) |
| LED bits 输出 | 真实 LED 光码板 |
