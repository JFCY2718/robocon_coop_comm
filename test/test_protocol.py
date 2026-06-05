from robocon_coop_comm.protocol import MsgID, decode_led_bits, encode_led_bits


def test_all_msg_ids_round_trip_for_both_seq_values():
    for msg_id in range(32):
        for seq in (0, 1):
            encoded = encode_led_bits(msg_id, seq)
            decoded = decode_led_bits(encoded.bits)
            assert decoded.valid
            assert decoded.msg_id == msg_id
            assert decoded.seq == seq


def test_parity_detects_single_bit_error():
    encoded = encode_led_bits(MsgID.INSERT_ALLOWED, 1)
    bits = dict(encoded.bits)
    bits["D2"] ^= 1
    decoded = decode_led_bits(bits)
    assert not decoded.valid


def test_ref_off_is_invalid_even_if_parity_ok():
    encoded = encode_led_bits(MsgID.R1_CLEAR_MC, 0)
    bits = dict(encoded.bits)
    bits["REF"] = 0
    decoded = decode_led_bits(bits)
    assert not decoded.valid
