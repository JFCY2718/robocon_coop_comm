"""Tests for PatternMapper — configurable LED pattern mapping.

Covers:
- LedDef / LedPattern dataclass
- Predefined patterns (3led_below, 6led_horizontal)
- Manual ROI mapping with various scales
- AprilTag-guided ROI mapping (delegates to AprilTagRoiMapper)
- Serialisation round-trip
- Edge cases (empty pattern, zero LEDs)
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from robocon_coop_comm.pattern_mapper import (
    PATTERN_3LED_BELOW,
    PATTERN_6LED_HORIZONTAL,
    PATTERN_6LED_TWO_ROW,
    LedDef,
    LedPattern,
    PatternMapper,
)
from robocon_coop_comm.apriltag_roi_mapper import RoiPoint


# ---------------------------------------------------------------------------
# LedDef
# ---------------------------------------------------------------------------


class TestLedDef:
    def test_construction(self) -> None:
        led = LedDef("REF", x_mm=10.0, y_mm=20.0)
        assert led.name == "REF"
        assert led.x_mm == 10.0
        assert led.y_mm == 20.0

    def test_is_frozen(self) -> None:
        led = LedDef("D0", 0.0, 0.0)
        with pytest.raises(Exception):
            led.x_mm = 99.0  # type: ignore[misc]

    def test_equality(self) -> None:
        a = LedDef("D0", 1.0, 2.0)
        b = LedDef("D0", 1.0, 2.0)
        c = LedDef("D1", 1.0, 2.0)
        assert a == b
        assert a != c


# ---------------------------------------------------------------------------
# LedPattern
# ---------------------------------------------------------------------------


class TestLedPattern:
    def test_construction(self) -> None:
        leds = [LedDef("REF", 0.0, 0.0), LedDef("D0", 10.0, 0.0)]
        p = LedPattern("test", "test pattern", leds)
        assert p.name == "test"
        assert p.description == "test pattern"
        assert len(p.leds) == 2

    def test_default_leds_empty(self) -> None:
        p = LedPattern("empty", "no leds")
        assert p.leds == []

    def test_is_frozen(self) -> None:
        p = LedPattern("t", "d", [])
        with pytest.raises(Exception):
            p.name = "x"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Predefined patterns
# ---------------------------------------------------------------------------


class TestPredefinedPatterns:
    def test_3led_below(self) -> None:
        p = PATTERN_3LED_BELOW
        assert p.name == "3led_below"
        assert len(p.leds) == 3
        names = [led.name for led in p.leds]
        assert names == ["D0", "D1", "D2"]
        # D0 left, D1 centre, D2 right.
        assert p.leds[0].x_mm < p.leds[1].x_mm < p.leds[2].x_mm
        # All at same y (below the tag).
        assert p.leds[0].y_mm == p.leds[1].y_mm == p.leds[2].y_mm

    def test_6led_horizontal(self) -> None:
        p = PATTERN_6LED_HORIZONTAL
        assert p.name == "6led_horizontal"
        assert len(p.leds) == 6
        names = [led.name for led in p.leds]
        assert names == ["REF", "D0", "D1", "D2", "SEQ", "PAR"]

    def test_6led_two_row(self) -> None:
        p = PATTERN_6LED_TWO_ROW
        assert p.name == "6led_two_row"
        assert len(p.leds) == 6
        # Top row: REF, D0, D1 (y=0).
        top = [led for led in p.leds if led.y_mm == 0.0]
        assert [led.name for led in top] == ["REF", "D0", "D1"]
        # Bottom row: D2, SEQ, PAR (y=30).
        bottom = [led for led in p.leds if led.y_mm == 30.0]
        assert [led.name for led in bottom] == ["D2", "SEQ", "PAR"]


# ---------------------------------------------------------------------------
# PatternMapper — construction
# ---------------------------------------------------------------------------


class TestPatternMapperConstruction:
    def test_defaults(self) -> None:
        m = PatternMapper(PATTERN_3LED_BELOW)
        assert m.led_count == 3
        assert m.led_names == ["D0", "D1", "D2"]
        assert m.px_per_mm == 2.0

    def test_custom_scale(self) -> None:
        m = PatternMapper(PATTERN_6LED_HORIZONTAL, px_per_mm=3.5)
        assert m.px_per_mm == 3.5
        assert m.led_count == 6

    def test_custom_radius(self) -> None:
        m = PatternMapper(PATTERN_3LED_BELOW, default_radius_mm=8.0)
        assert m._default_radius_mm == 8.0

    def test_pattern_property(self) -> None:
        m = PatternMapper(PATTERN_3LED_BELOW)
        assert m.pattern is PATTERN_3LED_BELOW


# ---------------------------------------------------------------------------
# PatternMapper — manual_rois
# ---------------------------------------------------------------------------


class TestManualRois:
    def test_basic_projection(self) -> None:
        m = PatternMapper(PATTERN_3LED_BELOW, px_per_mm=2.0)
        rois = m.manual_rois(origin_px=(100, 200))
        assert len(rois) == 3
        # D0 at (0, 110) mm → (100, 420) px.
        assert rois[0].name == "D0"
        assert rois[0].x_px == 100
        assert rois[0].y_px == 420  # 200 + 110*2
        # D1 at (50, 110) mm → (200, 420) px.
        assert rois[1].name == "D1"
        assert rois[1].x_px == 200
        # D2 at (100, 110) mm → (300, 420) px.
        assert rois[2].name == "D2"
        assert rois[2].x_px == 300

    def test_custom_scale_override(self) -> None:
        m = PatternMapper(PATTERN_3LED_BELOW, px_per_mm=2.0)
        rois = m.manual_rois(origin_px=(0, 0), px_per_mm=4.0)
        # D0 at (0, 110) mm → (0, 440) px.
        assert rois[0].y_px == 440

    def test_custom_radius_override(self) -> None:
        m = PatternMapper(PATTERN_3LED_BELOW, px_per_mm=2.0, default_radius_mm=5.0)
        rois = m.manual_rois(origin_px=(0, 0), radius_mm=10.0)
        assert rois[0].radius_px == 20  # 10mm * 2 px/mm

    def test_origin_offset(self) -> None:
        m = PatternMapper(PATTERN_3LED_BELOW, px_per_mm=1.0)
        rois = m.manual_rois(origin_px=(50, 30))
        assert rois[0].x_px == 50  # 50 + 0*1
        assert rois[0].y_px == 140  # 30 + 110*1

    def test_empty_pattern_returns_empty(self) -> None:
        empty = LedPattern("empty", "")
        m = PatternMapper(empty)
        assert m.manual_rois((0, 0)) == []

    def test_radius_minimum_1_px(self) -> None:
        """Even with tiny radius_mm and tiny scale, radius_px ≥ 1."""
        m = PatternMapper(PATTERN_3LED_BELOW, px_per_mm=0.01, default_radius_mm=1.0)
        rois = m.manual_rois((0, 0))
        assert rois[0].radius_px == 1


# ---------------------------------------------------------------------------
# PatternMapper — apriltag_rois
# ---------------------------------------------------------------------------


class TestApriltagRois:
    def test_delegates_to_apriltag_roi_mapper(self) -> None:
        m = PatternMapper(PATTERN_3LED_BELOW, px_per_mm=2.0)
        # Axis-aligned square tag: 250px = 125mm full tag → 2 px/mm.
        corners = [
            (100.0, 100.0),
            (350.0, 100.0),
            (350.0, 350.0),
            (100.0, 350.0),
        ]
        rois, H = m.apriltag_rois(
            tag_corners=corners,
            tag_size_mm=100.0,
            image_shape=(480, 640),
        )
        assert H is not None
        assert len(rois) == 3
        # Black border bottom ≈ 325px (tag bottom 350 minus white border ~25px).
        # LED y at 110mm below black-border top-left → ~345px.
        # LEDs should be below the black border, inside or below white border.
        black_border_bottom_y = corners[2][1] - 25  # ~325
        for r in rois:
            assert r.y_px > black_border_bottom_y, f"{r.name} at y={r.y_px} not below {black_border_bottom_y}"

    def test_offset_shifts_all_leds(self) -> None:
        """tag_to_pattern_offset_mm shifts the entire pattern."""
        m = PatternMapper(PATTERN_3LED_BELOW, px_per_mm=2.0)
        corners = [
            (100.0, 100.0),
            (350.0, 100.0),
            (350.0, 350.0),
            (100.0, 350.0),
        ]
        # Without offset.
        rois_no_offset, _ = m.apriltag_rois(corners, tag_size_mm=100.0, image_shape=(480, 640))
        # With +20mm y offset.
        rois_offset, _ = m.apriltag_rois(
            corners, tag_size_mm=100.0, image_shape=(480, 640),
            tag_to_pattern_offset_mm=(0.0, 20.0),
        )
        # Offsetting should move LEDs further down.
        for r_no, r_off in zip(rois_no_offset, rois_offset):
            assert r_off.y_px > r_no.y_px

    def test_custom_radius(self) -> None:
        m = PatternMapper(PATTERN_3LED_BELOW, default_radius_mm=5.0)
        corners = [
            (100.0, 100.0),
            (350.0, 100.0),
            (350.0, 350.0),
            (100.0, 350.0),
        ]
        rois_default, _ = m.apriltag_rois(corners, tag_size_mm=100.0, image_shape=(480, 640))
        rois_custom, _ = m.apriltag_rois(
            corners, tag_size_mm=100.0, image_shape=(480, 640), led_radius_mm=10.0,
        )
        assert rois_custom[0].radius_px > rois_default[0].radius_px


# ---------------------------------------------------------------------------
# PatternMapper — serialisation
# ---------------------------------------------------------------------------


class TestSerialisation:
    def test_round_trip_3led(self) -> None:
        m = PatternMapper(PATTERN_3LED_BELOW, px_per_mm=3.0, default_radius_mm=6.0)
        data = m.to_dict()
        m2 = PatternMapper.from_dict(data)
        assert m2.led_count == m.led_count
        assert m2.led_names == m.led_names
        assert m2.px_per_mm == 3.0
        assert m2._default_radius_mm == 6.0

    def test_round_trip_6led(self) -> None:
        m = PatternMapper(PATTERN_6LED_HORIZONTAL, px_per_mm=2.5)
        data = m.to_dict()
        m2 = PatternMapper.from_dict(data)
        assert m2.led_count == 6
        assert m2.led_names == ["REF", "D0", "D1", "D2", "SEQ", "PAR"]

    def test_to_dict_is_json_serialisable(self) -> None:
        m = PatternMapper(PATTERN_3LED_BELOW)
        data = m.to_dict()
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        assert parsed["name"] == "3led_below"
        assert len(parsed["leds"]) == 3

    def test_from_dict_defaults_missing_fields(self) -> None:
        """Missing optional fields fall back to defaults."""
        minimal = {
            "name": "custom",
            "leds": [{"name": "X", "x_mm": 1.0, "y_mm": 2.0}],
        }
        m = PatternMapper.from_dict(minimal)
        assert m.px_per_mm == 2.0
        assert m._default_radius_mm == 5.0
        assert m.pattern.description == ""


# ---------------------------------------------------------------------------
# Manual ROI → manual_rois mapping accuracy
# ---------------------------------------------------------------------------


class TestManualRoiAccuracy:
    def test_6led_horizontal_spacing(self) -> None:
        m = PatternMapper(PATTERN_6LED_HORIZONTAL, px_per_mm=2.0)
        rois = m.manual_rois((0, 0))
        # Evenly spaced by 20mm = 40px.
        for i in range(len(rois) - 1):
            gap = rois[i + 1].x_px - rois[i].x_px
            assert gap == 40

    def test_two_row_layout_positions(self) -> None:
        m = PatternMapper(PATTERN_6LED_TWO_ROW, px_per_mm=2.0)
        rois = m.manual_rois((100, 100))
        # Top row y = 100 + 0*2 = 100.
        top_leds = [r for r in rois if r.y_px == 100]
        assert len(top_leds) == 3
        # Bottom row y = 100 + 30*2 = 160.
        bot_leds = [r for r in rois if r.y_px == 160]
        assert len(bot_leds) == 3
