# STM32 六灯测试固件 — Hikrobot Bitmask Smoke Test

## 当前用途

这是 **STM32F103 六灯测试固件**，用于配合 Hikrobot 相机进行 LED bitmask 识别 smoke test。

- ✅ 验证相机能否区分 6 个 LED 的亮灭
- ✅ 验证 bitmask 映射 (D0=bit0 … PAR=bit5) 与 Python 侧一致
- ❌ **不是**最终比赛固件
- ❌ **不包含**比赛协议逻辑 (msg_id/seq/ACK)
- ❌ 不宣称硬件闭环验收通过

## 硬件

| 项目 | 值 |
|------|-----|
| MCU | STM32F103C8T6 (Blue Pill) |
| 调试器 | ST-Link V2 |
| IDE | STM32CubeIDE (或 arm-none-eabi-gcc) |
| 时钟 | HSI 8 MHz (内部 RC) |

## GPIO 配置 (Pin Map)

| 引脚 | LED | bit 位 | bitmask hex |
|------|-----|--------|-------------|
| PA0 | D0 | bit0 (LSB) | `0x01` |
| PA1 | D1 | bit1 | `0x02` |
| PA2 | D2 | bit2 | `0x04` |
| PA3 | REF | bit3 | `0x08` |
| PA4 | SEQ | bit4 | `0x10` |
| PA5 | PAR | bit5 (MSB) | `0x20` |

全亮 = `0x3F`，全灭 = `0x00`。

Pin map 与仓库现有 `main.c` 完全一致。

### GPIO 寄存器配置

- 模式: General purpose push-pull output, 2 MHz
- CRL 值: `0x00222222` (PA0-PA5 = 0x2 each)
- 初始输出: 低电平 (全灭)

### LED 极性

```c
#define LED_ACTIVE_HIGH  1
```

**当前假设 LED 为高电平点亮** (`GPIO_ODR` 置位 = LED 亮)。

如果实际硬件 LED 是低电平点亮 (active-low)，请把 `sixled_test_main.c` 中的宏改为:

```c
#define LED_ACTIVE_HIGH  0
```

代码中所有 LED 操作通过 `LED_ON()` / `LED_OFF()` 宏处理极性，改为 0 后会自动反转。

## 如何烧录

### 方式 A: STM32CubeIDE (推荐)

1. 打开/新建 STM32F103C8T6 CubeIDE 工程。
2. 在 CubeMX 中配置:
   - PA0-PA5 → GPIO_Output
   - (可选) PA9 → USART1_TX, PA10 → USART1_RX
3. 将 `firmware/stm32f103_beacon_baremetal/sixled_test_main.c` 的内容
   复制到工程中的 `Core/Src/main.c`。
4. **编译**: Project → Build All (Ctrl+B)
5. **连接 ST-Link** 到 Blue Pill 的 SWD 接口 (SWCLK, SWDIO, GND, 3.3V)。
6. **烧录**: Run → Run (或 Debug)
7. 烧录完成后按板上的 RESET 按钮，或重新上电。

### 方式 B: baremetal arm-none-eabi-gcc

```bash
cd firmware/stm32f103_beacon_baremetal

# 编译
arm-none-eabi-gcc -mcpu=cortex-m3 -mthumb -nostartfiles \
    -T stm32f103c8.ld sixled_test_main.c -o sixled_test.elf

# 生成 hex/bin
arm-none-eabi-objcopy -O ihex sixled_test.elf sixled_test.hex
arm-none-eabi-objcopy -O binary sixled_test.elf sixled_test.bin

# 烧录 (ST-Link)
st-flash write sixled_test.bin 0x08000000
```

### 恢复原固件

原比赛协议固件在 `firmware/stm32f103_beacon_baremetal/main.c`。

- 重新烧录 `beacon.elf` 或 `beacon.bin` 即可恢复串口协议模式。
- 在 CubeIDE 中将 `main.c` 替换回原始内容，重新编译烧录。

## 肉眼验证步骤

上电后自动运行以下序列：

| 步骤 | 持续时间 | 预期现象 |
|------|---------|---------|
| 1. 全灭 | 1 秒 | 6 灯全灭 |
| 2. 全亮 | 1 秒 | 6 灯全亮 (bitmask = 0x3F) |
| 3. D0 亮 | 0.5 秒 | 仅 D0 亮 (0x01) |
| 4. D1 亮 | 0.5 秒 | 仅 D1 亮 (0x02) |
| 5. D2 亮 | 0.5 秒 | 仅 D2 亮 (0x04) |
| 6. REF 亮 | 0.5 秒 | 仅 REF 亮 (0x08) |
| 7. SEQ 亮 | 0.5 秒 | 仅 SEQ 亮 (0x10) |
| 8. PAR 亮 | 0.5 秒 | 仅 PAR 亮 (0x20) |
| 9. 全灭 | 0.5 秒 | 过渡 |
| 10. 跑马灯 | 循环 | 单灯轮流从左到右滚动 |

### 如果启用了串口 (USART_RX_ENABLED=1)

- 测试序列结束后进入交互模式。
- 用串口工具 (115200 8N1) 发送 `0`-`63` + 回车。
- MCU 回显当前 bitmask，LED 同步显示。
- 例如发送 `63` → 全亮 `111111 (0x3F)`

## 与 Python 侧 bitmask 对应

| LED | C 侧 `SixLed_SetMask(mask)` | Python 侧 `LED_BIT_MAP` |
|-----|----------------------------|------------------------|
| D0 | `mask & 0x01` → PA0 | `"D0": 0` (bit0) |
| D1 | `mask & 0x02` → PA1 | `"D1": 1` (bit1) |
| D2 | `mask & 0x04` → PA2 | `"D2": 2` (bit2) |
| REF | `mask & 0x08` → PA3 | `"REF": 3` (bit3) |
| SEQ | `mask & 0x10` → PA4 | `"SEQ": 4` (bit4) |
| PAR | `mask & 0x20` → PA5 | `"PAR": 5` (bit5) |

两边 bitmask 定义完全一致，相机识别的 bitmask 可以直接与 STM32 发出的 mask 对比。

## 后续相机测试命令

```bash
# 1. ROI 标定 (全亮时点击 6 个 LED)
python tools/hikrobot_6led_live.py --save-roi data/sixled/configs/my_roi.json

# 2. 实时识别 (跑马灯或串口切换时记录)
python tools/hikrobot_6led_live.py \
    --roi-file data/sixled/configs/my_roi.json \
    --log data/sixled/logs/sixled_smoke.csv \
    --protocol

# 3. 日志汇总
python tools/sixled_log_summary.py data/sixled/logs/sixled_smoke.csv

# 4. 单灯测试验证 (每个 LED 单独亮，确认 bitmask)
#    在串口发送: 1, 2, 4, 8, 16, 32
#    观察相机输出 bitmask 是否匹配
```

## 文件清单

| 文件 | 说明 |
|------|------|
| `main.c` | 原有比赛协议固件 (串口帧+ACK) |
| `sixled_test_main.c` | 六灯测试固件参考实现 (本次新增) |
| `beacon.elf` / `beacon.bin` | 原有固件编译产物 |
| `stm32f103c8.ld` | 链接脚本 |
| `README.md` | 原有固件说明 |
| `PROTOCOL.md` | 原有固件协议说明 |
| `../README_SIXLED_TEST.md` | 本文件 |

## 在 STM32CubeIDE 中打开

- 如果已有 CubeIDE 工程 (`.ioc` / `.project`)，直接在 IDE 中打开工程目录。
- 如果没有 CubeIDE 工程:
  1. File → New → STM32 Project
  2. 选择 MCU: STM32F103C8
  3. 在 Pinout 视图中设置 PA0-PA5 为 GPIO_Output
  4. 将 `sixled_test_main.c` 内容复制到 `Core/Src/main.c`
  5. Build (Ctrl+B) → Run → 选择 ST-Link

下一步: 在 STM32CubeIDE 中确认 MCU 型号、build、通过 ST-Link 烧录后，肉眼验证测试序列。
