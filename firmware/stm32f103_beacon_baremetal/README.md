# STM32F103C8T6 LED Beacon MCU Firmware

## 概述

这是 R1 LED 光码板的 MCU 固件，运行在 **STM32F103C8T6 (Blue Pill)** 上。

- **当前版本**：裸寄存器 C（无 HAL、无 CubeMX、无 Arduino）
- **当前状态**：✅ 三灯 D0/D1/D2 已实机验证通过
- **六灯模式**（REF/SEQ/PAR）：代码已预留，下一阶段启用

## 功能

1. 通过 USART1 (PA9/PA10) 接收 R1 主控发来的 6 字节串口帧
2. 校验帧格式和 checksum
3. 驱动 3 颗 LED 显示 msg_id 的低 3 位
4. 回复 3 字节 ACK 确认帧

## 硬件要求

| 设备 | 说明 |
|------|------|
| STM32F103C8T6 (Blue Pill) | MCU 开发板 |
| ST-LINK/V2.1（或兼容烧录器） | 烧录 + USB 虚拟串口 |
| 3× LED + 3× 限流电阻 (~220Ω) | D0/D1/D2 指示灯 |

## 烧录方式

### 方法一：STM32CubeProgrammer（推荐）

```bash
# 安装 STM32CubeProgrammer（Ubuntu）
# 下载地址：https://www.st.com/en/development-tools/stm32cubeprog.html

# 连接 ST-LINK 后烧录
STM32_Programmer_CLI -c port=SWD -w beacon.hex -v -s
```

### 方法二：STM32CubeIDE

1. 新建 STM32 项目，Target 选择 STM32F103C8T6
2. 将 `main.c` 替换为仓库中的版本
3. 编译 → Run → Debug 即可烧录

### 方法三：OpenOCD + arm-none-eabi-gcc

```bash
# 编译
arm-none-eabi-gcc -mcpu=cortex-m3 -mthumb -nostartfiles \
    -T stm32f103c8.ld main.c -o beacon.elf
arm-none-eabi-objcopy -O ihex beacon.elf beacon.hex

# 烧录（需要 openocd）
openocd -f interface/stlink.cfg -f target/stm32f1x.cfg \
    -c "program beacon.hex verify reset exit"
```

### ST-LINK 接线

| ST-LINK | STM32F103 |
|---------|-----------|
| GND | GND |
| DIO / SWDIO | SWDIO / SWD |
| CLK / SWCLK | SWCLK / SWC |

## 串口接线

| ST-LINK (VCP) | STM32F103 |
|---------------|-----------|
| TX | PA10 / USART1_RX |
| RX | PA9 / USART1_TX |
| GND | GND |

> **注意**：ST-LINK 的串口引脚在烧录器侧面（GND/TX/RX 排针），**不要**和 SWD 引脚（DIO/CLK）混淆。

## LED 接线

| STM32 GPIO | 连接 |
|------------|------|
| PA0 | → 电阻 (~220Ω) → **D0** LED 长脚 (Anode)，短脚 (Cathode) → GND |
| PA1 | → 电阻 (~220Ω) → **D1** LED 长脚，短脚 → GND |
| PA2 | → 电阻 (~220Ω) → **D2** LED 长脚，短脚 → GND |
| PA3 | **REF** — 预留，下一阶段 |
| PA4 | **SEQ** — 预留，下一阶段 |
| PA5 | **PAR** — 预留，下一阶段 |

## 测试命令

从上位机（Ubuntu 22.04）发送单帧并验证 ACK：

```bash
source .venv/bin/activate

# 发送 INSERT_ALLOWED (msg_id=4)，亮度 200
python tools/send_3led_msg.py --port /dev/ttyACM0 --msg-id 4 --seq 1 --brightness 200
```

**期望输出：**

```
msg_id=4 INSERT_ALLOWED
seq=1
brightness=200
frame=AA 55 04 01 C8 CD
ack=CC 04 01
```

**期望 LED 状态：**

```
msg_id=4 → 二进制 100 → D2=1 D1=0 D0=0 → D2 亮，D1/D0 灭
```

### 全部测试命令

```bash
python tools/send_3led_msg.py --port /dev/ttyACM0 --msg-id 0 --seq 0 --brightness 200  # IDLE, 全灭
python tools/send_3led_msg.py --port /dev/ttyACM0 --msg-id 1 --seq 1 --brightness 200  # HOLD, D0亮
python tools/send_3led_msg.py --port /dev/ttyACM0 --msg-id 2 --seq 0 --brightness 200  # ROD, D1亮
python tools/send_3led_msg.py --port /dev/ttyACM0 --msg-id 4 --seq 1 --brightness 200  # INSERT, D2亮
python tools/send_3led_msg.py --port /dev/ttyACM0 --msg-id 7 --seq 0 --brightness 200  # MF, 三灯全亮
```

## 上电自检

固件上电后会立即执行一次自检，依次显示以下 LED 状态（每个约 250ms）：

| # | msg_id | seq | D2 | D1 | D0 |
|---|--------|-----|----|----|----|
| 1 | 0 | 0 | 灭 | 灭 | 灭 |
| 2 | 1 | 1 | 灭 | 灭 | 亮 |
| 3 | 2 | 0 | 灭 | 亮 | 灭 |
| 4 | 4 | 1 | 亮 | 灭 | 灭 |
| 5 | 7 | 0 | 亮 | 亮 | 亮 |
| 6 | 0 | 0 | 灭 | 灭 | 灭 |

自检结束时所有 LED 熄灭，随后进入串口接收模式。

## 技术细节

- **系统时钟**：HSI 8 MHz（复位默认，未使用 PLL）
- **USART1**：115200 8N1，无流控
- **波特率误差**：+0.64%（8MHz / (16 × 4.3125) = 115,942 baud）
- **LED 驱动**：GPIO 推挽输出，2 MHz
- **代码体积**：极小，裸寄存器，无 HAL 依赖
