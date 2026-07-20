from robocon_coop_comm.six_led_decoder import SixLedReading, six_led_to_coop_beacon


def _reading(bits: dict[str, int], *, valid: bool = True) -> SixLedReading:
    return SixLedReading(
        bits=bits,
        brightness={name: 200.0 if value else 20.0 for name, value in bits.items()},
        confidence=0.9,
        valid=valid,
    )


def test_four_light_bridge_decodes_persistent_state() -> None:
    decoded = six_led_to_coop_beacon(
        _reading({"D0": 1, "D1": 0, "D2": 1, "D3": 0, "REF": 1, "PAR": 0})
    )

    assert decoded.valid is True
    assert decoded.msg_id == 5
    assert decoded.msg_name == "WEAPON_LOCKED"
    assert decoded.seq == 0


def test_four_light_bridge_rejects_bad_reference_or_parity() -> None:
    no_reference = six_led_to_coop_beacon(
        _reading({"D0": 1, "D1": 0, "D2": 0, "D3": 0, "REF": 0, "PAR": 1})
    )
    bad_parity = six_led_to_coop_beacon(
        _reading({"D0": 1, "D1": 0, "D2": 0, "D3": 0, "REF": 1, "PAR": 0})
    )

    assert no_reference.valid is False
    assert bad_parity.valid is False


def test_four_light_bridge_preserves_vision_invalidity() -> None:
    decoded = six_led_to_coop_beacon(
        _reading(
            {"D0": 0, "D1": 1, "D2": 0, "D3": 0, "REF": 1, "PAR": 1},
            valid=False,
        )
    )

    assert decoded.msg_id == 2
    assert decoded.valid is False
    assert decoded.reason == "vision_invalid"
