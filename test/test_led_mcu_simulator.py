"""Tests for LED MCU simulator."""

from __future__ import annotations

from robocon_coop_comm.led_mcu_simulator import LedMcuError, LedMcuSimulator, LedMcuUpdate
from robocon_coop_comm.protocol import encode_led_bits
from robocon_coop_comm.serial_frame import encode_frame


class TestLedMcuSimulator:
    def test_single_valid_frame(self) -> None:
        """msg_id=4, seq=1, brightness=200 -> valid update with correct LED bits."""
        sim = LedMcuSimulator()
        frame = encode_frame(4, 1, 200)
        results = sim.feed(frame)

        assert len(results) == 1
        r = results[0]
        assert isinstance(r, LedMcuUpdate)
        assert r.msg_id == 4
        assert r.seq == 1
        assert r.brightness == 200
        assert r.led_bits["REF"] == 1
        assert r.led_bits["D2"] == 1  # bit 2 of msg_id=4
        assert r.led_bits["D0"] == 0
        assert r.led_bits["D1"] == 0
        assert r.led_bits["SEQ"] == 1
        # PAR = D0^D1^D2^D3^D4^SEQ = 0^0^1^0^0^1 = 0
        assert r.led_bits["PAR"] == 0

    def test_fragmented_input(self) -> None:
        """Feed frame in two parts."""
        sim = LedMcuSimulator()
        frame = encode_frame(4, 1, 200)

        r1 = sim.feed(frame[:2])
        assert r1 == []  # not enough bytes yet

        r2 = sim.feed(frame[2:])
        assert len(r2) == 1
        assert isinstance(r2[0], LedMcuUpdate)
        assert r2[0].msg_id == 4

    def test_noise_resync(self) -> None:
        """Noise bytes before a valid frame are skipped."""
        sim = LedMcuSimulator()
        frame = encode_frame(4, 1, 200)
        noise = b"\x00\x13\xFF"
        results = sim.feed(noise + frame)

        assert len(results) == 1
        assert isinstance(results[0], LedMcuUpdate)
        assert results[0].msg_id == 4

    def test_two_consecutive_frames(self) -> None:
        """Two frames back to back produce two updates."""
        sim = LedMcuSimulator()
        f1 = encode_frame(2, 0, 100)
        f2 = encode_frame(5, 1, 255)
        results = sim.feed(f1 + f2)

        assert len(results) == 2
        assert isinstance(results[0], LedMcuUpdate)
        assert isinstance(results[1], LedMcuUpdate)
        assert results[0].msg_id == 2
        assert results[1].msg_id == 5

    def test_bad_checksum_then_valid(self) -> None:
        """Bad checksum produces error; subsequent valid frame still parsed."""
        sim = LedMcuSimulator()
        bad_frame = bytes([0xAA, 0x55, 4, 1, 200, 0x00])  # wrong checksum
        good_frame = encode_frame(4, 1, 200)
        results = sim.feed(bad_frame + good_frame)

        assert len(results) == 2
        assert isinstance(results[0], LedMcuError)
        assert "checksum" in results[0].reason.lower()
        assert isinstance(results[1], LedMcuUpdate)
        assert results[1].msg_id == 4

    def test_invalid_msg_id(self) -> None:
        """msg_id > 31 produces error."""
        sim = LedMcuSimulator()
        bad = bytes([0xAA, 0x55, 32, 0, 100, 32 ^ 0 ^ 100])
        results = sim.feed(bad)

        assert len(results) == 1
        assert isinstance(results[0], LedMcuError)
        assert "msg_id" in results[0].reason.lower()

    def test_invalid_seq(self) -> None:
        """seq > 1 produces error."""
        sim = LedMcuSimulator()
        bad = bytes([0xAA, 0x55, 4, 2, 100, 4 ^ 2 ^ 100])
        results = sim.feed(bad)

        assert len(results) == 1
        assert isinstance(results[0], LedMcuError)
        assert "seq" in results[0].reason.lower()

    def test_led_bits_match_protocol(self) -> None:
        """LED bits from simulator must exactly match protocol.encode_led_bits."""
        sim = LedMcuSimulator()
        for msg_id in (0, 1, 15, 31):
            for seq in (0, 1):
                frame = encode_frame(msg_id, seq, 200)
                results = sim.feed(frame)
                assert len(results) == 1
                r = results[0]
                assert isinstance(r, LedMcuUpdate)
                expected = encode_led_bits(msg_id, seq)
                assert r.led_bits == expected.bits, f"Mismatch at msg_id={msg_id} seq={seq}"
