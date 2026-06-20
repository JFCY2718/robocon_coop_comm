/*
 * sixled_test_main.c — STM32F103C8T6 六灯测试固件参考实现
 * ==========================================================
 *
 * 用途：验证 Hikrobot 相机能否正确识别 6 个 LED 的亮灭（bitmask smoke test）。
 * 这不是最终比赛固件。
 *
 * Target:   STM32F103C8T6 (Blue Pill)
 * Clock:    HSI 8 MHz
 * Toolchain: arm-none-eabi-gcc (或 STM32CubeIDE)
 *
 * ---- Pin Map (与仓库现有 main.c 一致) ----
 *
 *   PA0 = D0   (bit0, LSB)
 *   PA1 = D1   (bit1)
 *   PA2 = D2   (bit2)
 *   PA3 = REF  (bit3)
 *   PA4 = SEQ  (bit4)
 *   PA5 = PAR  (bit5, MSB)
 *
 * ---- LED 极性 ----
 *
 *   本固件假设 LED 为高电平点亮 (active-high)。
 *
 *   #define LED_ACTIVE_HIGH  1
 *
 *   如果实际硬件 LED 是低电平点亮，请把下面一行改为:
 *
 *   #define LED_ACTIVE_HIGH  0
 *
 *   代码中所有 LED 操作通过宏 LED_ON() / LED_OFF() 处理极性。
 *
 * ---- 上电测试序列 ----
 *
 *   1. 全灭  1 秒
 *   2. 全亮  1 秒  (bitmask = 0x3F = 0b111111)
 *   3. 单灯轮流亮（每个 0.5 秒）:
 *      D0 → D1 → D2 → REF → SEQ → PAR
 *   4. 跑马灯循环（每次亮一颗，从左到右滚动）
 *
 * ---- 串口控制 (可选) ----
 *
 *   如果启用 UART (USART_RX_ENABLED=1)，可从串口发送 0~63 的十进制数字
 *   + 换行，MCU 将显示对应的 6-bit mask。
 *
 *   例如发送 "63\n" → 全亮 (0x3F)
 *        发送 "0\n"  → 全灭
 *        发送 "1\n"  → 仅 D0 亮
 *
 * ---- 编译 (baremetal arm-none-eabi-gcc) ----
 *
 *   arm-none-eabi-gcc -mcpu=cortex-m3 -mthumb -nostartfiles \
 *       -T stm32f103c8.ld sixled_test_main.c -o sixled_test.elf
 *   arm-none-eabi-objcopy -O ihex sixled_test.elf sixled_test.hex
 *   arm-none-eabi-objcopy -O binary sixled_test.elf sixled_test.bin
 *
 * ---- 在 STM32CubeIDE 中使用 ----
 *
 *   将此文件内容复制到 CubeIDE 工程的 Core/Src/main.c，
 *   替换原有 main.c 内容。编译后通过 ST-Link 烧录。
 *
 * ---- 恢复原固件 ----
 *
 *   烧录仓库中的 main.c（beacon.elf）即可恢复串口协议固件。
 */

#include <stdint.h>

/* ========================================================================
 * 配置宏
 * ======================================================================== */

#define LED_ACTIVE_HIGH  1    /* 改为 0 如果 LED 低电平点亮 */

/* 是否启用 USART1 串口接收（0=仅跑测试序列, 1=支持串口输入mask） */
#define USART_RX_ENABLED 1

/* 测试阶段每步持续时间 (毫秒)，基于 8MHz 的粗略延时 */
#define DELAY_500MS  1000000
#define DELAY_1000MS 2000000
#define DELAY_150MS   300000

/* ========================================================================
 * 寄存器定义 (STM32F103)
 * ======================================================================== */

/* Reset & Clock Control */
#define RCC_BASE    0x40021000UL
#define RCC_CR      (*((volatile uint32_t *)(RCC_BASE + 0x00)))
#define RCC_APB2ENR (*((volatile uint32_t *)(RCC_BASE + 0x18)))

#define RCC_APB2ENR_IOPAEN   (1U << 2)
#define RCC_APB2ENR_USART1EN (1U << 14)

/* GPIOA */
#define GPIOA_BASE  0x40010800UL
#define GPIOA_CRL   (*((volatile uint32_t *)(GPIOA_BASE + 0x00)))
#define GPIOA_CRH   (*((volatile uint32_t *)(GPIOA_BASE + 0x04)))
#define GPIOA_ODR   (*((volatile uint32_t *)(GPIOA_BASE + 0x0C)))

/* GPIOA pin masks */
#define PIN_D0   (1U << 0)   /* PA0 */
#define PIN_D1   (1U << 1)   /* PA1 */
#define PIN_D2   (1U << 2)   /* PA2 */
#define PIN_REF  (1U << 3)   /* PA3 */
#define PIN_SEQ  (1U << 4)   /* PA4 */
#define PIN_PAR  (1U << 5)   /* PA5 */

/* All 6 LED pins */
#define LED_PIN_MASK  (PIN_D0 | PIN_D1 | PIN_D2 | PIN_REF | PIN_SEQ | PIN_PAR)

/* Six LEDs in bitmask order: D0=bit0, D1=bit1, D2=bit2, REF=bit3, SEQ=bit4, PAR=bit5 */
static const uint32_t LED_PINS[6] = {
    PIN_D0,   /* bit0 */
    PIN_D1,   /* bit1 */
    PIN_D2,   /* bit2 */
    PIN_REF,  /* bit3 */
    PIN_SEQ,  /* bit4 */
    PIN_PAR,  /* bit5 */
};
static const char *LED_NAMES[6] = {
    "D0", "D1", "D2", "REF", "SEQ", "PAR"
};

/* USART1 */
#define USART1_BASE 0x40013800UL
#define USART1_SR   (*((volatile uint32_t *)(USART1_BASE + 0x00)))
#define USART1_DR   (*((volatile uint32_t *)(USART1_BASE + 0x04)))
#define USART1_BRR  (*((volatile uint32_t *)(USART1_BASE + 0x08)))
#define USART1_CR1  (*((volatile uint32_t *)(USART1_BASE + 0x0C)))

#define USART_SR_RXNE  (1U << 5)
#define USART_SR_TXE   (1U << 7)
#define USART_CR1_UE   (1U << 13)
#define USART_CR1_TE   (1U << 3)
#define USART_CR1_RE   (1U << 2)

/* ========================================================================
 * LED 极性宏
 * ======================================================================== */

#if LED_ACTIVE_HIGH
  #define LED_ON(odr, pin)   ((odr) |  (pin))
  #define LED_OFF(odr, pin)  ((odr) & ~(pin))
#else
  #define LED_ON(odr, pin)   ((odr) & ~(pin))
  #define LED_OFF(odr, pin)  ((odr) |  (pin))
#endif

/* ========================================================================
 * 延时 (粗略，基于 8MHz HSI)
 * ======================================================================== */

static void delay(uint32_t cycles)
{
    for (volatile uint32_t i = 0; i < cycles; i++) {
        __asm__ volatile("nop");
    }
}

/* ========================================================================
 * SixLed API
 * ======================================================================== */

/**
 * Set all 6 LEDs according to a 6-bit mask.
 *
 *   bit0 (0x01) → D0
 *   bit1 (0x02) → D1
 *   bit2 (0x04) → D2
 *   bit3 (0x08) → REF
 *   bit4 (0x10) → SEQ
 *   bit5 (0x20) → PAR
 *
 * Only the lower 6 bits of `mask` are used.
 */
void SixLed_SetMask(uint8_t mask)
{
    uint32_t odr = GPIOA_ODR & ~LED_PIN_MASK;
    for (int i = 0; i < 6; i++) {
        if (mask & (1U << i)) {
            odr = LED_ON(odr, LED_PINS[i]);
        }
        /* else: already cleared by & ~LED_PIN_MASK above */
    }
    GPIOA_ODR = odr;
}

/** Turn all 6 LEDs off. */
void SixLed_AllOff(void)
{
    uint32_t odr = GPIOA_ODR & ~LED_PIN_MASK;
    GPIOA_ODR = odr;
}

/** Turn all 6 LEDs on. */
void SixLed_AllOn(void)
{
    uint32_t odr = GPIOA_ODR & ~LED_PIN_MASK;
    for (int i = 0; i < 6; i++) {
        odr = LED_ON(odr, LED_PINS[i]);
    }
    GPIOA_ODR = odr;
}

/** Turn on a single LED by name index (0=D0, 1=D1, ... 5=PAR). */
void SixLed_One(int index)
{
    if (index < 0 || index > 5) return;
    uint32_t odr = GPIOA_ODR & ~LED_PIN_MASK;
    odr = LED_ON(odr, LED_PINS[index]);
    GPIOA_ODR = odr;
}

/** Simple chase pattern: one LED at a time, left to right. */
void SixLed_Chase(void)
{
    for (int i = 0; i < 6; i++) {
        SixLed_One(i);
        delay(DELAY_150MS);
    }
}

/* ========================================================================
 * 串口 (可选)
 * ======================================================================== */

#if USART_RX_ENABLED

static void usart1_putc(uint8_t c)
{
    while (!(USART1_SR & USART_SR_TXE)) {}
    USART1_DR = c;
}

static void usart1_puts(const char *s)
{
    while (*s) usart1_putc((uint8_t)*s++);
}

static uint8_t usart1_getc(void)
{
    while (!(USART1_SR & USART_SR_RXNE)) {}
    return (uint8_t)(USART1_DR & 0xFF);
}

/** Read a decimal number 0-63 from UART, terminated by '\n' or '\r'.
 *  Returns the value, or 0xFF if invalid. */
static int usart1_read_mask(void)
{
    uint8_t val = 0;
    int got_digit = 0;
    for (;;) {
        uint8_t c = usart1_getc();
        if (c == '\n' || c == '\r') {
            return got_digit ? (int)val : -1;
        }
        if (c >= '0' && c <= '9') {
            val = val * 10 + (c - '0');
            got_digit = 1;
            if (val > 63) val = 63;  /* clamp */
        }
    }
}

static void usart_echo_mask(uint8_t mask)
{
    usart1_puts("mask=");
    for (int i = 5; i >= 0; i--) {
        usart1_putc((mask & (1U << i)) ? '1' : '0');
    }
    usart1_puts(" (0x");
    /* quick hex: upper nibble */
    uint8_t hi = (mask >> 4) & 0xF;
    usart1_putc(hi < 10 ? '0' + hi : 'A' + hi - 10);
    uint8_t lo = mask & 0xF;
    usart1_putc(lo < 10 ? '0' + lo : 'A' + lo - 10);
    usart1_puts(")\r\n");
}

#endif /* USART_RX_ENABLED */

/* ========================================================================
 * 初始化
 * ======================================================================== */

static void clock_init(void)
{
    RCC_CR |= (1U << 0);   /* HSION */
    while (!(RCC_CR & (1U << 1))) {
        __asm__ volatile("nop");
    }
}

static void gpio_init(void)
{
    RCC_APB2ENR |= RCC_APB2ENR_IOPAEN;
    __asm__ volatile("nop");

    /* PA0-PA5: general purpose push-pull output, 2 MHz → value 0x2 per pin */
    GPIOA_CRL &= ~0x00FFFFFF;
    GPIOA_CRL |=  0x00222222;

#if USART_RX_ENABLED
    /* PA9=TX (AF PP 50MHz=0xB), PA10=RX (input floating=0x4) */
    GPIOA_CRH &= ~0x00000FF0;
    GPIOA_CRH |=  0x000004B0;
#endif

    SixLed_AllOff();
}

#if USART_RX_ENABLED
static void usart1_init(void)
{
    RCC_APB2ENR |= RCC_APB2ENR_USART1EN;
    __asm__ volatile("nop");

    /* 115200 @ 8 MHz → BRR = 0x45 */
    USART1_BRR = 0x45;
    USART1_CR1 = USART_CR1_TE | USART_CR1_RE | USART_CR1_UE;
}
#endif

/* ========================================================================
 * 上电测试序列
 * ======================================================================== */

static void test_sequence(void)
{
    /* 1. 全灭 1 秒 */
    SixLed_AllOff();
    delay(DELAY_1000MS);

    /* 2. 全亮 1 秒 → bitmask = 0x3F = 0b111111 */
    SixLed_SetMask(0x3F);
    delay(DELAY_1000MS);

    /* 3. 单灯轮流亮 (每个 0.5 秒) */
    for (int i = 0; i < 6; i++) {
        SixLed_One(i);
        delay(DELAY_500MS);
    }

    /* 4. 全灭再过度 */
    SixLed_AllOff();
    delay(DELAY_500MS);
}

/* ========================================================================
 * 主函数
 * ======================================================================== */

int main(void)
{
    clock_init();
    gpio_init();
#if USART_RX_ENABLED
    usart1_init();
    usart1_puts("\r\n=== STM32F103 SixLED Test Firmware ===\r\n");
    usart1_puts("Send 0-63 + Enter to set bitmask\r\n");
    usart1_puts("  D0=bit0 D1=bit1 D2=bit2 REF=bit3 SEQ=bit4 PAR=bit5\r\n\r\n");
#endif

    /* 上电测试序列 (运行一次) */
    test_sequence();

    /* 进入永久循环 */
#if USART_RX_ENABLED
    usart1_puts("Ready. Enter bitmask (0-63):\r\n");
    for (;;) {
        int v = usart1_read_mask();
        if (v >= 0 && v <= 63) {
            SixLed_SetMask((uint8_t)v);
            usart_echo_mask((uint8_t)v);
        }
    }
#else
    /* 无串口: 循环跑马灯 */
    for (;;) {
        SixLed_Chase();
    }
#endif

    return 0;
}

/* ========================================================================
 * 向量表 (baremetal 编译用)
 * ======================================================================== */

#define SRAM_END  0x20005000UL

__attribute__((section(".vectors"), used))
const uint32_t vector_table[] = {
    SRAM_END,
    (uint32_t)main,
};

void __attribute__((weak)) Default_Handler(void) { for (;;) {} }
void __attribute__((weak, alias("Default_Handler"))) NMI_Handler(void);
void __attribute__((weak, alias("Default_Handler"))) HardFault_Handler(void);
void __attribute__((weak, alias("Default_Handler"))) MemManage_Handler(void);
void __attribute__((weak, alias("Default_Handler"))) BusFault_Handler(void);
void __attribute__((weak, alias("Default_Handler"))) UsageFault_Handler(void);
void __attribute__((weak, alias("Default_Handler"))) SVC_Handler(void);
void __attribute__((weak, alias("Default_Handler"))) DebugMon_Handler(void);
void __attribute__((weak, alias("Default_Handler"))) PendSV_Handler(void);
void __attribute__((weak, alias("Default_Handler"))) SysTick_Handler(void);
