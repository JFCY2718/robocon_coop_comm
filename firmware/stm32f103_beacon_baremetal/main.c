/*
 * STM32F103C8T6 LED Beacon MCU — Baremetal C Firmware
 * ====================================================
 *
 * Target:   STM32F103C8T6 (Blue Pill)
 * Clock:    HSI 8 MHz (reset default, no PLL)
 * Toolchain: arm-none-eabi-gcc (or STM32CubeIDE / Keil / IAR)
 *
 * This firmware receives 6-byte serial frames from the R1 main controller,
 * drives 3–6 LEDs to display the current message, and replies with a 3-byte ACK.
 *
 * It uses ONLY register-level access. No HAL. No CubeMX. No Arduino.
 *
 * ---- Hardware Pinout ----
 *
 *  LED outputs (3-LED mode — currently validated):
 *    PA0 = D0  (msg_id bit 0)
 *    PA1 = D1  (msg_id bit 1)
 *    PA2 = D2  (msg_id bit 2)
 *
 *  LED outputs (6-LED mode — reserved for future expansion):
 *    PA3 = REF (always on when frame valid)
 *    PA4 = SEQ (sequence toggle bit)
 *    PA5 = PAR (even parity: D0 ^ D1 ^ D2 ^ SEQ)
 *
 *  USART1 (serial link to R1 main controller):
 *    PA9  = USART1_TX  (alternate function push-pull)
 *    PA10 = USART1_RX  (input floating)
 *
 * ---- Serial Frame Format (R1 -> MCU, 6 bytes) ----
 *
 *   Byte 0: 0xAA  ─┐ header
 *   Byte 1: 0x55  ─┘
 *   Byte 2: msg_id     (0 ~ 7, maps to protocol.MsgID)
 *   Byte 3: seq        (0 or 1, toggles on new event)
 *   Byte 4: brightness (0 ~ 255, reserved — no PWM in current fw)
 *   Byte 5: checksum   = msg_id ^ seq ^ brightness
 *
 * ---- ACK Format (MCU -> R1, 3 bytes) ----
 *
 *   Byte 0: 0xCC
 *   Byte 1: msg_id     (echo)
 *   Byte 2: seq        (echo)
 *
 * ---- LED Display Logic ----
 *
 *   D0  = (msg_id >> 0) & 1
 *   D1  = (msg_id >> 1) & 1
 *   D2  = (msg_id >> 2) & 1
 *   REF = 1
 *   SEQ = seq & 1
 *   PAR = D0 ^ D1 ^ D2 ^ SEQ
 *
 * ---- Verified Commands ----
 *
 *   msg_id=4 seq=1 brightness=200  →  frame=AA 55 04 01 C8 CD  →  ack=CC 04 01  D2D1D0=100
 *   msg_id=1 seq=0 brightness=200  →  frame=AA 55 01 00 C8 C9  →  ack=CC 01 00  D2D1D0=001
 *   msg_id=2 seq=1 brightness=200  →  frame=AA 55 02 01 C8 CB  →  ack=CC 02 01  D2D1D0=010
 *   msg_id=7 seq=0 brightness=200  →  frame=AA 55 07 00 C8 CF  →  ack=CC 07 00  D2D1D0=111
 */

#include <stdint.h>

/* --------------------------------------------------------------------------
 * Register definitions (STM32F103 memory-mapped I/O)
 * -------------------------------------------------------------------------- */

/* Reset & Clock Control */
#define RCC_BASE    0x40021000UL
#define RCC_CR      (*((volatile uint32_t *)(RCC_BASE + 0x00)))
#define RCC_CFGR    (*((volatile uint32_t *)(RCC_BASE + 0x04)))
#define RCC_APB2ENR (*((volatile uint32_t *)(RCC_BASE + 0x18)))

#define RCC_APB2ENR_IOPAEN   (1U << 2)   /* GPIOA clock enable */
#define RCC_APB2ENR_USART1EN (1U << 14)  /* USART1 clock enable */

/* GPIOA */
#define GPIOA_BASE  0x40010800UL
#define GPIOA_CRL   (*((volatile uint32_t *)(GPIOA_BASE + 0x00)))  /* PA0-PA7 config */
#define GPIOA_CRH   (*((volatile uint32_t *)(GPIOA_BASE + 0x04)))  /* PA8-PA15 config */
#define GPIOA_ODR   (*((volatile uint32_t *)(GPIOA_BASE + 0x0C)))  /* Port output data */

/* GPIOA_ODR bit masks */
#define PA0  (1U << 0)
#define PA1  (1U << 1)
#define PA2  (1U << 2)
#define PA3  (1U << 3)
#define PA4  (1U << 4)
#define PA5  (1U << 5)

/*
 * GPIOx_CRL / GPIOx_CRH: 4 bits per pin.
 *
 *   For PA0-PA5 (LEDs): general purpose push-pull output, max speed 2 MHz
 *     MODE = 01 (output, 2 MHz)  CNF = 00 (general purpose push-pull)
 *     → 4-bit value = 0x2
 *
 *   For PA9 (USART1_TX): alternate function push-pull output, 50 MHz
 *     MODE = 11 (output, 50 MHz)  CNF = 10 (alternate function push-pull)
 *     → 4-bit value = 0xB
 *
 *   For PA10 (USART1_RX): input floating
 *     MODE = 00 (input)  CNF = 01 (floating)
 *     → 4-bit value = 0x4
 */

/* USART1 */
#define USART1_BASE 0x40013800UL
#define USART1_SR   (*((volatile uint32_t *)(USART1_BASE + 0x00)))
#define USART1_DR   (*((volatile uint32_t *)(USART1_BASE + 0x04)))
#define USART1_BRR  (*((volatile uint32_t *)(USART1_BASE + 0x08)))
#define USART1_CR1  (*((volatile uint32_t *)(USART1_BASE + 0x0C)))

/* USART1_SR bits */
#define USART_SR_RXNE  (1U << 5)  /* Read data register not empty */
#define USART_SR_TXE   (1U << 7)  /* Transmit data register empty */
#define USART_SR_TC    (1U << 6)  /* Transmission complete */

/* USART1_CR1 bits */
#define USART_CR1_UE   (1U << 13)  /* USART enable */
#define USART_CR1_TE   (1U << 3)   /* Transmitter enable */
#define USART_CR1_RE   (1U << 2)   /* Receiver enable */

/* --------------------------------------------------------------------------
 * Frame constants
 * -------------------------------------------------------------------------- */
#define FRAME_HEADER_0  0xAA
#define FRAME_HEADER_1  0x55
#define ACK_HEADER      0xCC
#define FRAME_LEN       6

/* --------------------------------------------------------------------------
 * LED state buffer (6 LEDs: D0, D1, D2, REF, SEQ, PAR)
 * -------------------------------------------------------------------------- */
static volatile uint8_t led_d0, led_d1, led_d2, led_ref, led_seq, led_par;

/* --------------------------------------------------------------------------
 * Low-level helpers
 * -------------------------------------------------------------------------- */

/** Write a byte to USART1 (blocking). */
static void usart1_putc(uint8_t c)
{
    while (!(USART1_SR & USART_SR_TXE)) { /* wait for TX empty */ }
    USART1_DR = c;
}

/** Read a byte from USART1 (blocking). */
static uint8_t usart1_getc(void)
{
    while (!(USART1_SR & USART_SR_RXNE)) { /* wait for RX not empty */ }
    return (uint8_t)(USART1_DR & 0xFF);
}

/** Apply LED state to GPIOA output pins. */
static void leds_apply(void)
{
    uint32_t odr = GPIOA_ODR & ~(PA0 | PA1 | PA2 | PA3 | PA4 | PA5);

    if (led_d0)  odr |= PA0;
    if (led_d1)  odr |= PA1;
    if (led_d2)  odr |= PA2;
    if (led_ref) odr |= PA3;
    if (led_seq) odr |= PA4;
    if (led_par) odr |= PA5;

    GPIOA_ODR = odr;
}

/** Set all LEDs off. */
static void leds_off(void)
{
    led_d0 = led_d1 = led_d2 = led_ref = led_seq = led_par = 0;
    leds_apply();
}

/**
 * Update LED state from a decoded message.
 *
 *   D0  = bit0(msg_id)
 *   D1  = bit1(msg_id)
 *   D2  = bit2(msg_id)
 *   REF = 1
 *   SEQ = seq & 1
 *   PAR = D0 ^ D1 ^ D2 ^ SEQ
 */
static void leds_update(uint8_t msg_id, uint8_t seq)
{
    led_d0  = (msg_id >> 0) & 1;
    led_d1  = (msg_id >> 1) & 1;
    led_d2  = (msg_id >> 2) & 1;
    led_ref = (msg_id == 0) ? 0 : 1;
    led_seq = seq & 1;
    led_par = led_d0 ^ led_d1 ^ led_d2 ^ led_seq;
    leds_apply();
}

/** Send a 3-byte ACK: CC msg_id seq. */
static void send_ack(uint8_t msg_id, uint8_t seq)
{
    usart1_putc(ACK_HEADER);
    usart1_putc(msg_id);
    usart1_putc(seq);
}

/** Display a single message for self-test, with ACK. */
static void self_test_one(uint8_t msg_id, uint8_t seq)
{
    leds_update(msg_id, seq);
    send_ack(msg_id, seq);

    /* busy-wait ~250 ms at 8 MHz (very rough) */
    for (volatile uint32_t i = 0; i < 500000; i++) {
        __asm__ volatile("nop");
    }
}

/* --------------------------------------------------------------------------
 * Self-test sequence — runs once at power-up
 * -------------------------------------------------------------------------- */
static void self_test(void)
{
    /*
     * Verified sequence to confirm all LEDs and serial link work:
     *   IDLE           msg_id=0 seq=0
     *   HOLD           msg_id=1 seq=1
     *   R1_ROD_CLAMPED msg_id=2 seq=0
     *   INSERT_ALLOWED msg_id=4 seq=1
     *   R1_IN_MF       msg_id=7 seq=0
     *   IDLE           msg_id=0 seq=0  (back to off)
     */
    self_test_one(0, 0);
    self_test_one(1, 1);
    self_test_one(2, 0);
    self_test_one(4, 1);
    self_test_one(7, 0);
    self_test_one(0, 0);

    leds_off();
}

/* --------------------------------------------------------------------------
 * USART receive state machine
 * -------------------------------------------------------------------------- */

/**
 * Wait for a complete 6-byte frame, validate it, update LEDs, and send ACK.
 *
 * State machine:
 *   S0 → wait for 0xAA
 *   S1 → wait for 0x55 (if wrong byte, go back to S0)
 *   S2 → read msg_id
 *   S3 → read seq
 *   S4 → read brightness
 *   S5 → read checksum  →  validate  →  update LEDs + ACK  →  S0
 */
static void frame_loop(void)
{
    uint8_t state = 0;
    uint8_t msg_id = 0, seq = 0, brightness = 0, checksum = 0;

    for (;;) {
        uint8_t c = usart1_getc();

        switch (state) {
        case 0: /* wait for header byte 0xAA */
            if (c == FRAME_HEADER_0) {
                state = 1;
            }
            /* else: stay in S0, discard byte */
            break;

        case 1: /* expect header byte 0x55 */
            if (c == FRAME_HEADER_1) {
                state = 2;
            } else {
                /* If we see another 0xAA here, treat it as a new frame start.
                 * Otherwise go back to hunting for 0xAA. */
                state = (c == FRAME_HEADER_0) ? 1 : 0;
            }
            break;

        case 2: /* msg_id */
            msg_id = c;
            if (msg_id > 31) {
                /* Invalid msg_id → drop frame, hunt for next header */
                state = 0;
                break;
            }
            state = 3;
            break;

        case 3: /* seq */
            seq = c;
            if (seq > 1) {
                state = 0;
                break;
            }
            state = 4;
            break;

        case 4: /* brightness */
            brightness = c;
            state = 5;
            break;

        case 5: /* checksum */
            checksum = c;
            if (checksum == (uint8_t)(msg_id ^ seq ^ brightness)) {
                /* Valid frame → update LEDs and send ACK */
                leds_update(msg_id, seq);
                send_ack(msg_id, seq);
            }
            /*
             * If checksum fails: do NOT update LEDs, do NOT send ACK.
             * Just silently drop the frame and go back to hunting.
             */
            state = 0;
            break;

        default:
            state = 0;
            break;
        }
    }
}

/* --------------------------------------------------------------------------
 * System initialization
 * -------------------------------------------------------------------------- */

static void clock_init(void)
{
    /*
     * After reset the system runs on HSI (8 MHz).
     * HSI is already enabled by hardware.
     * We just confirm it is stable, then use as-is — no PLL.
     */

    /* Enable HSI if not already on (should already be on after reset) */
    RCC_CR |= (1U << 0);  /* HSION */
    while (!(RCC_CR & (1U << 1))) { /* wait for HSIRDY */
        __asm__ volatile("nop");
    }

    /*
     * RCC_CFGR: keep defaults
     *   SW   = 00 (HSI as system clock)
     *   HPRE = 0xxx (AHB prescaler = /1 → 8 MHz)
     *   PPRE1 = 0xx (APB1 = 8 MHz, max 36)
     *   PPRE2 = 0xx (APB2 = 8 MHz, max 72)
     */
}

static void gpio_init(void)
{
    /* Enable GPIOA clock */
    RCC_APB2ENR |= RCC_APB2ENR_IOPAEN;
    __asm__ volatile("nop");

    /*
     * PA0-PA5: general purpose push-pull output, 2 MHz
     *   Each pin uses 4 bits in CRL. Value = 0x2.
     *
     *   CRL bits:  PA5| PA4| PA3| PA2| PA1| PA0
     *   Hex:       2    2    2    2    2    2  → 0x222222
     */
    GPIOA_CRL &= ~0x00FFFFFF;   /* clear PA0-PA5 config */
    GPIOA_CRL |=  0x00222222;   /* set PA0-PA5 as output 2 MHz PP */

    /*
     * PA9  (USART1_TX): alternate function push-pull, 50 MHz → 0xB
     * PA10 (USART1_RX): input floating → 0x4
     *
     * CRH bits:  PA10| PA9
     *   Hex:      4     B  → 0x4B0
     */
    GPIOA_CRH &= ~0x00000FF0;   /* clear PA9, PA10 config */
    GPIOA_CRH |=  0x000004B0;   /* PA9=AF PP 50MHz, PA10=input floating */

    /* Start with all LEDs off */
    leds_off();
}

static void usart1_init(void)
{
    /* Enable USART1 clock (on APB2) */
    RCC_APB2ENR |= RCC_APB2ENR_USART1EN;
    __asm__ volatile("nop");

    /*
     * Baud rate calculation for 115200 @ 8 MHz APB2:
     *
     *   USARTDIV = f_CK / (16 × baud)
     *            = 8,000,000 / (16 × 115,200)
     *            = 8,000,000 / 1,843,200
     *            ≈ 4.340
     *
     *   Mantissa (DIV_Mantissa) = 4
     *   Fraction (DIV_Fraction) = 0.340 × 16 ≈ 5.44 → 5
     *
     *   USART_BRR = (4 << 4) | 5 = 0x45
     *
     * Actual baud  = 8,000,000 / (16 × 4.3125) = 115,942
     * Error        = +0.64%  (well within ±2% tolerance)
     */
    USART1_BRR = 0x45;

    /* Enable USART1: transmitter + receiver + USART */
    USART1_CR1 = USART_CR1_TE | USART_CR1_RE | USART_CR1_UE;
}

/* --------------------------------------------------------------------------
 * Entry point
 * -------------------------------------------------------------------------- */

int main(void)
{
    clock_init();
    gpio_init();
    usart1_init();

    /*
     * Power-on self-test:
     *   Cycles through 6 known-good messages to verify LEDs and serial link.
     *   Sends ACK after each one.
     *   Ends with all LEDs off.
     */
    self_test();

    /*
     * Main loop: wait for serial frames, validate, update LEDs, send ACK.
     * This function never returns.
     */
    frame_loop();

    /* Unreachable */
    return 0;
}

/*
 * Minimal vector table and startup.
 *
 * If you use a linker script that provides a full vector table, you can omit
 * the sections below.  These are here so you can build a self-contained
 * bare-metal ELF with arm-none-eabi-gcc and a minimal linker script.
 *
 * Build example:
 *   arm-none-eabi-gcc -mcpu=cortex-m3 -mthumb -nostartfiles -T stm32f103c8.ld \
 *       main.c -o beacon.elf
 *   arm-none-eabi-objcopy -O ihex beacon.elf beacon.hex
 */

/* Stack top (end of 20 KB SRAM on STM32F103C8T6) */
#define SRAM_END  0x20005000UL

/* Minimal vector table — only stack pointer and reset handler */
__attribute__((section(".vectors"), used))
const uint32_t vector_table[] = {
    SRAM_END,               /* initial stack pointer */
    (uint32_t)main,         /* reset handler */
    /* All other vectors default to 0 (unused in this application) */
};

/* Default handlers for unused exceptions / interrupts */
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
