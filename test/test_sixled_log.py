"""Tests for shared sixled_log module — bitmask helpers, normalise_row, dominant_bitmask."""

from __future__ import annotations

import pytest

from robocon_coop_comm.sixled_log import (
    LED_NAMES,
    LED_BIT_MAP,
    bitmask_to_hex_str,
    bitmask_to_pattern,
    bits_to_bitmask,
    dominant_bitmask,
    normalise_row,
    parse_bitmask_str,
    resolve_bitmask,
)


# ---------------------------------------------------------------------------
# bitmask helpers
# ---------------------------------------------------------------------------


class TestBitmaskHelpers:
    def test_bits_to_bitmask_all_off(self) -> None:
        bits = {n: 0 for n in LED_NAMES}
        assert bits_to_bitmask(bits) == 0

    def test_bits_to_bitmask_all_on(self) -> None:
        bits = {n: 1 for n in LED_NAMES}
        assert bits_to_bitmask(bits) == 0x3F

    def test_bits_to_bitmask_d0_only(self) -> None:
        bits = {n: 1 if n == "D0" else 0 for n in LED_NAMES}
        assert bits_to_bitmask(bits) == 0x01

    def test_bits_to_bitmask_par_only(self) -> None:
        bits = {n: 1 if n == "PAR" else 0 for n in LED_NAMES}
        assert bits_to_bitmask(bits) == 0x20

    @pytest.mark.parametrize("val, expected", [
        (0, "000000"),
        (0x3F, "111111"),
        (0x01, "100000"),   # D0 only (leftmost)
        (0x02, "010000"),   # D1 only
        (0x04, "001000"),   # D2 only
        (0x08, "000100"),   # REF only
        (0x10, "000010"),   # SEQ only
        (0x20, "000001"),   # PAR only (rightmost)
    ])
    def test_bitmask_to_pattern(self, val: int, expected: str) -> None:
        assert bitmask_to_pattern(val) == expected

    @pytest.mark.parametrize("val, expected", [
        (0, "0x00"),
        (0x3F, "0x3F"),
        (0x01, "0x01"),
        (0x20, "0x20"),
    ])
    def test_bitmask_to_hex_str(self, val: int, expected: str) -> None:
        assert bitmask_to_hex_str(val) == expected

    @pytest.mark.parametrize("s, expected", [
        ("0x3F", 0x3F),
        ("0x00", 0),
        ("63", 63),
        ("0", 0),
        ("0x01", 1),
        ("0x20", 0x20),
        ("garbage", None),
        ("", None),
    ])
    def test_parse_bitmask_str(self, s: str, expected: int | None) -> None:
        assert parse_bitmask_str(s) == expected


# ---------------------------------------------------------------------------
# normalise_row
# ---------------------------------------------------------------------------


class TestNormaliseRow:
    def test_normalise_new_style_noop(self) -> None:
        row = {"pattern": "111111", "bitmask": "0x3F", "D0": "1"}
        norm = normalise_row(row)
        assert norm is row  # no copy needed

    def test_normalise_old_style_lifts_pattern(self) -> None:
        row = {None: ["111111", "0x3F", "1", "1", "1", "1", "1", "1",
                        "50.0", "52.0", "72.0", "78.0", "41.0", "60.0"]}
        norm = normalise_row(row)
        assert norm["pattern"] == "111111"
        assert norm["bitmask"] == "0x3F"

    def test_normalise_old_style_lifts_led_bits(self) -> None:
        row = {None: ["000000", "0x00", "0", "0", "0", "0", "0", "0",
                        "10.0", "10.0", "10.0", "10.0", "10.0", "10.0"]}
        norm = normalise_row(row)
        for name in LED_NAMES:
            assert norm[name] == "0"

    def test_normalise_old_style_lifts_means(self) -> None:
        row = {None: ["111111", "0x3F", "1", "1", "1", "1", "1", "1",
                        "50.0", "52.0", "72.0", "78.0", "41.0", "60.0"]}
        norm = normalise_row(row)
        assert norm["D0_mean"] == "50.0"
        assert norm["PAR_mean"] == "60.0"

    def test_normalise_does_not_overwrite_existing(self) -> None:
        row = {"pattern": "keep_me", None: ["000000"]}
        norm = normalise_row(row)
        assert norm["pattern"] == "keep_me"


# ---------------------------------------------------------------------------
# resolve_bitmask
# ---------------------------------------------------------------------------


class TestResolveBitmask:
    def test_direct_bitmask(self) -> None:
        assert resolve_bitmask({"bitmask": "0x3F"}) == "0x3F"

    def test_bitmask_hex_alias(self) -> None:
        assert resolve_bitmask({"bitmask_hex": "0x00"}) == "0x00"

    def test_fallback_to_pattern(self) -> None:
        assert resolve_bitmask({"pattern": "111111"}) == "111111"

    def test_empty_when_nothing(self) -> None:
        assert resolve_bitmask({"valid": "1"}) == ""


# ---------------------------------------------------------------------------
# dominant_bitmask
# ---------------------------------------------------------------------------


class TestDominantBitmask:
    def test_empty_rows(self) -> None:
        bm, count, ratio = dominant_bitmask([])
        assert bm == ""
        assert count == 0
        assert ratio == 0.0

    def test_single_row(self) -> None:
        bm, count, ratio = dominant_bitmask([{"bitmask": "0x3F"}])
        assert bm == "0x3F"
        assert count == 1
        assert ratio == pytest.approx(1.0)

    def test_mixed_rows(self) -> None:
        rows = [{"bitmask": "0x3F"}] * 8 + [{"bitmask": "0x00"}] * 2
        bm, count, ratio = dominant_bitmask(rows)
        assert bm == "0x3F"
        assert count == 8
        assert ratio == pytest.approx(0.8)

    def test_rows_without_bitmask(self) -> None:
        rows = [{"valid": "1"}] * 10
        bm, count, ratio = dominant_bitmask(rows)
        assert bm == ""
        assert count == 0
