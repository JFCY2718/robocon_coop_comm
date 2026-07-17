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
 *  Four-data-light V2 outputs:
 *    PA3 = D3  (state_id bit 3)
 *    PA4 = REF (always on for a valid V2 state)
 *    PA5 = PAR (even parity: D0 ^ D1 ^ D2 ^ D3)
 *
 *  USART1 (serial link to R1 main controller):
 *    PA9  = USART1_TX  (alternate function push-pull)
 *    PA10 = USART1_RX  (input floating)
 *
 * ---- Legacy Serial Frame Format (preserved, R1 -> MCU, 6 bytes) ----
 *
 *   Byte 0: 0xAA  ─┐ header
 *   Byte 1: 0x55  ─┘
 *   Byte 2: msg_id     (0 ~ 7, maps to protocol.MsgID)
 *   Byte 3: seq        (0 or 1, toggles on new event)
 *   Byte 4: brightness (0 ~ 255, reserved — no PWM in current fw)
 *   Byte 5: checksum   = msg_id ^ seq ^ brightness
 *
 * ---- Four-light V2 Frame (R1 -> MCU, 6 bytes) ----
 *
 *   0xBD | 0x02 | state_id(0..15) | counter | brightness | CRC-8/ATM
 *
 * V2 ACK:
 *
 *   0xBE | 0x02 | state_id | counter | status | CRC-8/ATM
 *
 * V2 frames must refresh within 300 ms. On timeout all LEDs turn off.
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

/* Cortex-M3 SysTick */
#define SYST_CSR (*((volatile uint32_t *)0xE000E010UL))
#define SYST_RVR (*((volatile uint32_t *)0xE000E014UL))
#define SYST_CVR (*((volatile uint32_t *)0xE000E018UL))

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
#define LEGACY_HEADER_0       0xAAU
#define LEGACY_HEADER_1       0x55U
#define LEGACY_ACK_HEADER     0xCCU
#define V2_FRAME_HEADER       0xBDU
#define V2_ACK_HEADER         0xBEU
#define V2_VERSION            0x02U
#define V2_STATUS_OK          0x00U
#define V2_STATUS_BAD_VERSION 0x01U
#define V2_STATUS_BAD_STATE   0x02U
#define V2_STATUS_BAD_CRC     0x03U
#define FRAME_LEN             6U
#define V2_TIMEOUT_MS         300U

/* --------------------------------------------------------------------------
 * LED state buffer (physical pins PA0..PA5; labels depend on protocol version)
 * -------------------------------------------------------------------------- */
static volatile uint8_t current_led_mask;
static volatile uint32_t system_ms;
static uint32_t last_v2_frame_ms;
static uint8_t v2_watchdog_active;

/* --------------------------------------------------------------------------
 * Low-level helpers
 * -------------------------------------------------------------------------- */

/** Write a byte to USART1 (blocking). */
static void usart1_putc(uint8_t c)
{
    while (!(USART1_SR & USART_SR_TXE)) { /* wait for TX empty */ }
    USART1_DR = c;
}

/** Apply a physical six-bit mask directly to PA0..PA5. */
static void leds_apply_mask(uint8_t mask)
{
    uint32_t odr = GPIOA_ODR & ~(PA0 | PA1 | PA2 | PA3 | PA4 | PA5);
    odr |= ((uint32_t)mask & 0x3FU);
    GPIOA_ODR = odr;
    current_led_mask = mask & 0x3FU;
}

/** Set all LEDs off. */
static void leds_off(void)
{
    leds_apply_mask(0U);
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
static void leds_update_legacy(uint8_t msg_id, uint8_t seq)
{
    uint8_t d0 = (msg_id >> 0) & 1U;
    uint8_t d1 = (msg_id >> 1) & 1U;
    uint8_t d2 = (msg_id >> 2) & 1U;
    uint8_t ref = (msg_id == 0U) ? 0U : 1U;
    uint8_t sequence = seq & 1U;
    uint8_t parity = d0 ^ d1 ^ d2 ^ sequence;
    leds_apply_mask(
        d0 | (uint8_t)(d1 << 1U) | (uint8_t)(d2 << 2U) |
        (uint8_t)(ref << 3U) | (uint8_t)(sequence << 4U) |
        (uint8_t)(parity << 5U)
    );
}

static uint8_t four_light_parity(uint8_t state_id)
{
    uint8_t value = state_id & 0x0FU;
    value ^= (uint8_t)(value >> 2U);
    value ^= (uint8_t)(value >> 1U);
    return value & 1U;
}

static void leds_update_v2(uint8_t state_id)
{
    uint8_t mask = (uint8_t)((state_id & 0x0FU) | 0x10U);
    if (four_light_parity(state_id) != 0U) {
        mask |= 0x20U;
    }
    leds_apply_mask(mask);
}

/** Send a 3-byte ACK: CC msg_id seq. */
static void send_legacy_ack(uint8_t msg_id, uint8_t seq)
{
    usart1_putc(LEGACY_ACK_HEADER);
    usart1_putc(msg_id);
    usart1_putc(seq);
}

static uint8_t crc8_atm(const uint8_t *data, uint8_t length)
{
    uint8_t crc = 0U;
    for (uint8_t i = 0U; i < length; ++i) {
        crc ^= data[i];
        for (uint8_t bit = 0U; bit < 8U; ++bit) {
            crc = (crc & 0x80U) ? (uint8_t)((crc << 1U) ^ 0x07U)
                                : (uint8_t)(crc << 1U);
        }
    }
    return crc;
}

static void send_v2_ack(uint8_t state_id, uint8_t counter, uint8_t status)
{
    uint8_t ack[FRAME_LEN] = {V2_ACK_HEADER, V2_VERSION, state_id, counter, status, 0U};
    ack[5] = crc8_atm(ack, 5U);
    for (uint8_t i = 0U; i < FRAME_LEN; ++i) {
        usart1_putc(ack[i]);
    }
}

/** Display a single message for self-test, with ACK. */
static void self_test_one(uint8_t msg_id, uint8_t seq)
{
    leds_update_legacy(msg_id, seq);
    send_legacy_ack(msg_id, seq);

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
static void process_legacy_frame(const uint8_t frame[FRAME_LEN])
{
    uint8_t msg_id = frame[2];
    uint8_t seq = frame[3];
    uint8_t brightness = frame[4];
    if (msg_id <= 31U && seq <= 1U && frame[5] == (uint8_t)(msg_id ^ seq ^ brightness)) {
        leds_update_legacy(msg_id, seq);
        send_legacy_ack(msg_id, seq);
    }
}

static void process_v2_frame(const uint8_t frame[FRAME_LEN])
{
    uint8_t state_id = frame[2];
    uint8_t counter = frame[3];
    uint8_t status = V2_STATUS_OK;

    if (frame[1] != V2_VERSION) {
        status = V2_STATUS_BAD_VERSION;
    } else if (state_id > 15U) {
        status = V2_STATUS_BAD_STATE;
    } else if (frame[5] != crc8_atm(frame, 5U)) {
        status = V2_STATUS_BAD_CRC;
    }

    if (status == V2_STATUS_OK) {
        leds_update_v2(state_id);
        last_v2_frame_ms = system_ms;
        v2_watchdog_active = 1U;
    }
    send_v2_ack(state_id, counter, status);
}

static void frame_loop(void)
{
    uint8_t frame[FRAME_LEN];
    uint8_t frame_pos = 0U;

    for (;;) {
        if ((USART1_SR & USART_SR_RXNE) != 0U) {
            uint8_t byte = (uint8_t)(USART1_DR & 0xFFU);
            if (frame_pos == 0U) {
                if (byte == LEGACY_HEADER_0 || byte == V2_FRAME_HEADER) {
                    frame[0] = byte;
                    frame_pos = 1U;
                }
            } else if (frame_pos == 1U && frame[0] == LEGACY_HEADER_0 &&
                       byte != LEGACY_HEADER_1) {
                frame_pos = (byte == LEGACY_HEADER_0 || byte == V2_FRAME_HEADER) ? 1U : 0U;
                if (frame_pos == 1U) {
                    frame[0] = byte;
                }
            } else {
                frame[frame_pos++] = byte;
                if (frame_pos == FRAME_LEN) {
                    if (frame[0] == LEGACY_HEADER_0) {
                        process_legacy_frame(frame);
                    } else {
                        process_v2_frame(frame);
                    }
                    frame_pos = 0U;
                }
            }
        }

        if (v2_watchdog_active != 0U &&
            (uint32_t)(system_ms - last_v2_frame_ms) > V2_TIMEOUT_MS) {
            leds_off();
            v2_watchdog_active = 0U;
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

static void systick_init(void)
{
    SYST_RVR = 7999U; /* 1 ms at 8 MHz */
    SYST_CVR = 0U;
    SYST_CSR = 0x07U; /* processor clock, interrupt, enable */
}

/* --------------------------------------------------------------------------
 * Entry point
 * -------------------------------------------------------------------------- */

int main(void)
{
    clock_init();
    gpio_init();
    usart1_init();
    systick_init();

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

/*
 * Linker-defined symbols from stm32f103c8.ld.
 * _sbss / _ebss delimit the .bss section in SRAM — must be zeroed on reset.
 */
extern uint32_t _sbss;
extern uint32_t _ebss;

/* Forward declarations for exception handlers */
void Reset_Handler(void);
void NMI_Handler(void);
void HardFault_Handler(void);
void MemManage_Handler(void);
void BusFault_Handler(void);
void UsageFault_Handler(void);
void SVC_Handler(void);
void DebugMon_Handler(void);
void PendSV_Handler(void);
void SysTick_Handler(void);

/* Core exception vectors, including SysTick for the V2 communication watchdog. */
__attribute__((section(".vectors"), used))
const uint32_t vector_table[] = {
    SRAM_END,
    (uint32_t)Reset_Handler,
    (uint32_t)NMI_Handler,
    (uint32_t)HardFault_Handler,
    (uint32_t)MemManage_Handler,
    (uint32_t)BusFault_Handler,
    (uint32_t)UsageFault_Handler,
    0U, 0U, 0U, 0U,
    (uint32_t)SVC_Handler,
    (uint32_t)DebugMon_Handler,
    0U,
    (uint32_t)PendSV_Handler,
    (uint32_t)SysTick_Handler,
};

/*
 * Reset_Handler is the hardware entry point called after reset.
 * It must zero .bss before handing control to main(), otherwise
 * uninitialised static variables (system_ms, watchdog, etc.) can
 * contain random SRAM garbage and cause undefined behaviour on real
 * hardware.
 *
 * The .data section is empty in this firmware so a copy loop from
 * flash is not needed — if any initialised globals are added later,
 * a flash-to-SRAM copy must be inserted here.
 */
void Reset_Handler(void)
{
    uint32_t *bss = &_sbss;
    while (bss < &_ebss) {
        *bss++ = 0U;
    }
    main();
    /* main() never returns; loop here to satisfy the compiler */
    for (;;) {}
}

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

void SysTick_Handler(void)
{
    system_ms++;
}
