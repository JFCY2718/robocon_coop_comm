from pathlib import Path


SOURCE = (
    Path(__file__).parents[1]
    / "firmware"
    / "stm32f103_beacon_baremetal"
    / "main.c"
).read_text(encoding="utf-8")


def test_firmware_preserves_legacy_protocol() -> None:
    assert "#define LEGACY_HEADER_0       0xAAU" in SOURCE
    assert "#define LEGACY_HEADER_1       0x55U" in SOURCE
    assert "#define LEGACY_ACK_HEADER     0xCCU" in SOURCE
    assert "msg_id ^ seq ^ brightness" in SOURCE


def test_firmware_contains_v2_crc_ack_and_watchdog() -> None:
    assert "#define V2_FRAME_HEADER       0xBDU" in SOURCE
    assert "#define V2_ACK_HEADER         0xBEU" in SOURCE
    assert "#define V2_VERSION            0x02U" in SOURCE
    assert "#define V2_TIMEOUT_MS         300U" in SOURCE
    assert "crc8_atm" in SOURCE
    assert "SysTick_Handler" in SOURCE


def test_firmware_initializes_c_runtime_sections() -> None:
    linker = (
        Path(__file__).parents[1]
        / "firmware"
        / "stm32f103_beacon_baremetal"
        / "stm32f103c8.ld"
    ).read_text(encoding="utf-8")
    assert "ENTRY(Reset_Handler)" in linker
    assert "_sidata = LOADADDR(.data);" in linker
    assert "while (data < &_edata)" in SOURCE
    assert "*data++ = *source++;" in SOURCE
    assert "while (bss < &_ebss)" in SOURCE


def test_firmware_uses_fixed_pa0_through_pa5_mask() -> None:
    assert "GPIOA_ODR & ~(PA0 | PA1 | PA2 | PA3 | PA4 | PA5)" in SOURCE
    assert "(state_id & 0x0FU) | 0x10U" in SOURCE
    assert "mask |= 0x20U" in SOURCE
