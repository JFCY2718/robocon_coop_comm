"""Tests for SixLedRoiDecoder — pure vision-layer 6-LED decoding.

Covers:
- SixLedReading dataclass
- SixLedRoiDecoder construction
- decode with all LEDs ON / OFF / mixed
- Threshold gating
- Confidence computation
- Validity heuristics (out of bounds, too dark, overexposed)
- Null image handling
- six_led_to_decoded_beacon bridge function
"""

from __future__ import annotations

import numpy as np
import pytest

from robocon_coop_comm.six_led_decoder import (
    SixLedReading,
    SixLedRoiDecoder,
    six_led_to_decoded_beacon,
)
from robocon_coop_comm.beacon_types import BeaconFrame
from robocon_coop_comm.apriltag_roi_mapper import RoiPoint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _roi_points_6(name_prefix: str = "LED") -> list[RoiPoint]:
    """Six ROI points in a horizontal row."""
    return [
        RoiPoint(name="REF", x_px=100, y_px=400, radius_px=12),
        RoiPoint(name="D0", x_px=140, y_px=400, radius_px=12),
        RoiPoint(name="D1", x_px=180, y_px=400, radius_px=12),
        RoiPoint(name="D2", x_px=220, y_px=400, radius_px=12),
        RoiPoint(name="SEQ", x_px=260, y_px=400, radius_px=12),
        RoiPoint(name="PAR", x_px=300, y_px=400, radius_px=12),
    ]


def _frame(image: np.ndarray | None = None) -> BeaconFrame:
    if image is None:
        image = np.full((480, 640), 128, dtype=np.uint8)
    return BeaconFrame(image=image, source="test", frame_id=0)


# ---------------------------------------------------------------------------
# SixLedReading
# ---------------------------------------------------------------------------


class TestSixLedReading:
    def test_construction(self) -> None:
        r = SixLedReading(
            bits={"REF": 1, "D0": 0},
            brightness={"REF": 200.0, "D0": 50.0},
            confidence=0.85,
            valid=True,
        )
        assert r.bits == {"REF": 1, "D0": 0}
        assert r.confidence == 0.85
        assert r.valid is True

    def test_defaults(self) -> None:
        r = SixLedReading(
            bits={"D0": 0}, brightness={"D0": 10.0},
            confidence=0.0, valid=False,
        )
        assert r.frame_id == -1
        assert r.extra == {}

    def test_is_frozen(self) -> None:
        r = SixLedReading(
            bits={}, brightness={}, confidence=0.0, valid=False,
        )
        with pytest.raises(Exception):
            r.valid = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SixLedRoiDecoder — construction
# ---------------------------------------------------------------------------


class TestDecoderConstruction:
    def test_defaults(self) -> None:
        d = SixLedRoiDecoder()
        assert d.threshold == 120
        assert d.roi_size == 24
        assert d._min_brightness == 5.0
        assert d._max_brightness == 250.0

    def test_custom_params(self) -> None:
        d = SixLedRoiDecoder(threshold=150, roi_size=32, min_roi_brightness=10.0, max_roi_brightness=240.0)
        assert d.threshold == 150
        assert d.roi_size == 32


# ---------------------------------------------------------------------------
# decode — basic
# ---------------------------------------------------------------------------


class TestDecodeBasic:
    def test_all_leds_on(self) -> None:
        d = SixLedRoiDecoder(threshold=100)
        img = np.full((480, 640), 200, dtype=np.uint8)  # bright everywhere
        roi = _roi_points_6()
        result = d.decode(_frame(img), roi)
        assert result.valid is True
        assert all(v == 1 for v in result.bits.values())
        assert result.confidence > 0.5  # far from threshold

    def test_all_leds_off(self) -> None:
        d = SixLedRoiDecoder(threshold=100)
        img = np.full((480, 640), 10, dtype=np.uint8)  # dark everywhere
        roi = _roi_points_6()
        result = d.decode(_frame(img), roi)
        assert result.valid is True
        assert all(v == 0 for v in result.bits.values())

    def test_mixed_leds(self) -> None:
        """Paint only D0 and D2 bright — others dark."""
        d = SixLedRoiDecoder(threshold=100)
        img = np.full((480, 640), 10, dtype=np.uint8)
        cv2 = __import__("cv2")
        roi = _roi_points_6()
        # Bright spots at D0 and D2.
        for name in ("D0", "D2"):
            rp = next(r for r in roi if r.name == name)
            cv2.circle(img, (rp.x_px, rp.y_px), rp.radius_px, 220, -1)

        result = d.decode(_frame(img), roi)
        assert result.bits["D0"] == 1
        assert result.bits["D2"] == 1
        assert result.bits["D1"] == 0
        assert result.bits["REF"] == 0

    def test_threshold_exact_boundary(self) -> None:
        """Brightness == threshold → OFF (strict >)."""
        d = SixLedRoiDecoder(threshold=100)
        img = np.full((480, 640), 100, dtype=np.uint8)  # exactly at threshold
        roi = _roi_points_6()
        result = d.decode(_frame(img), roi)
        assert all(v == 0 for v in result.bits.values())

    def test_threshold_just_above(self) -> None:
        d = SixLedRoiDecoder(threshold=100)
        img = np.full((480, 640), 101, dtype=np.uint8)
        roi = _roi_points_6()
        result = d.decode(_frame(img), roi)
        assert all(v == 1 for v in result.bits.values())


# ---------------------------------------------------------------------------
# decode — null / edge cases
# ---------------------------------------------------------------------------


class TestDecodeEdgeCases:
    def test_null_image(self) -> None:
        d = SixLedRoiDecoder()
        frame = BeaconFrame(image=None, source="test", frame_id=0)
        result = d.decode(frame, _roi_points_6())
        assert result.valid is False
        assert result.bits == {}
        assert result.confidence == 0.0

    def test_empty_roi_list(self) -> None:
        d = SixLedRoiDecoder()
        img = np.full((480, 640), 200, dtype=np.uint8)
        result = d.decode(_frame(img), [])
        assert result.bits == {}
        assert result.valid is False

    def test_roi_out_of_bounds(self) -> None:
        """ROI outside image → bit=0, valid=False."""
        d = SixLedRoiDecoder()
        img = np.full((480, 640), 200, dtype=np.uint8)
        roi = [RoiPoint(name="FAR", x_px=9999, y_px=9999, radius_px=12)]
        result = d.decode(_frame(img), roi)
        assert result.valid is False
        assert result.bits["FAR"] == 0


# ---------------------------------------------------------------------------
# Validity heuristics
# ---------------------------------------------------------------------------


class TestValidityHeuristics:
    def test_too_dark_invalid(self) -> None:
        d = SixLedRoiDecoder(min_roi_brightness=10.0)
        img = np.full((480, 640), 3, dtype=np.uint8)  # below min
        roi = _roi_points_6()
        result = d.decode(_frame(img), roi)
        assert result.valid is False

    def test_overexposed_invalid(self) -> None:
        d = SixLedRoiDecoder(max_roi_brightness=240.0)
        img = np.full((480, 640), 250, dtype=np.uint8)  # above max
        roi = _roi_points_6()
        result = d.decode(_frame(img), roi)
        assert result.valid is False

    def test_normal_brightness_valid(self) -> None:
        d = SixLedRoiDecoder(min_roi_brightness=5.0, max_roi_brightness=250.0)
        img = np.full((480, 640), 128, dtype=np.uint8)
        roi = _roi_points_6()
        result = d.decode(_frame(img), roi)
        assert result.valid is True


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------


class TestConfidence:
    def test_high_confidence_far_from_threshold(self) -> None:
        d = SixLedRoiDecoder(threshold=120)
        img = np.full((480, 640), 255, dtype=np.uint8)  # 135 margin → 1.0
        result = d.decode(_frame(img), _roi_points_6())
        assert result.confidence == 1.0

    def test_low_confidence_near_threshold(self) -> None:
        d = SixLedRoiDecoder(threshold=120)
        img = np.full((480, 640), 121, dtype=np.uint8)  # 1 margin → ~0.01
        result = d.decode(_frame(img), _roi_points_6())
        assert result.confidence < 0.1

    def test_empty_brightness_confidence_zero(self) -> None:
        d = SixLedRoiDecoder()
        frame = BeaconFrame(image=None, source="test", frame_id=0)
        result = d.decode(frame, [])
        assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# six_led_to_decoded_beacon bridge
# ---------------------------------------------------------------------------


class TestBridgeToDecodedBeacon:
    def test_all_zeros_idle(self) -> None:
        """All bits 0 → msg_id=0 (IDLE), valid if REF=1... wait, REF=0."""
        reading = SixLedReading(
            bits={"REF": 0, "D0": 0, "D1": 0, "D2": 0, "SEQ": 0, "PAR": 0},
            brightness={"REF": 0.0, "D0": 0.0, "D1": 0.0, "D2": 0.0, "SEQ": 0.0, "PAR": 0.0},
            confidence=0.0, valid=False,
        )
        result = six_led_to_decoded_beacon(reading)
        # REF=0 → valid=False (parity check requires REF=1).
        assert result.valid is False

    def test_ref_on_msg_id_1(self) -> None:
        """REF=1, D0=1 → msg_id=1. SEQ=0, PAR computed."""
        reading = SixLedReading(
            bits={"REF": 1, "D0": 1, "D1": 0, "D2": 0, "SEQ": 0, "PAR": 1},
            brightness={"REF": 200.0, "D0": 200.0, "D1": 10.0, "D2": 10.0, "SEQ": 10.0, "PAR": 200.0},
            confidence=0.9, valid=True,
        )
        result = six_led_to_decoded_beacon(reading)
        assert result.msg_id == 1
        assert result.confidence == 0.9

    def test_missing_keys_default_to_zero(self) -> None:
        """Patterns with fewer than 8 LEDs: missing keys → 0."""
        reading = SixLedReading(
            bits={"D0": 1, "D1": 1},  # only 2 LEDs provided
            brightness={}, confidence=0.5, valid=True,
        )
        result = six_led_to_decoded_beacon(reading)
        # D0=1, D1=1 → msg_id=3. REF=0 (missing) → valid=False.
        assert result.msg_id == 3
        assert result.valid is False  # REF=0

    def test_invalid_reading_passed_through(self) -> None:
        reading = SixLedReading(
            bits={"REF": 1, "D0": 1, "D1": 0, "D2": 0, "SEQ": 0, "PAR": 1},
            brightness={}, confidence=0.5, valid=False,
        )
        result = six_led_to_decoded_beacon(reading)
        # Protocol layer says valid (correct parity) but reading says invalid.
        assert result.valid is False  # reading.valid overrides

    def test_bgr_image_decoded_correctly(self) -> None:
        """roi_mean handles BGR input internally."""
        d = SixLedRoiDecoder(threshold=100)
        bgr = np.full((480, 640, 3), 200, dtype=np.uint8)
        roi = _roi_points_6()
        result = d.decode(_frame(bgr), roi)
        assert result.valid is True


# ---------------------------------------------------------------------------
# CLI --help must work without Hikrobot SDK
# ---------------------------------------------------------------------------


class Test6LedCliHelp:
    def test_help_works(self) -> None:
        """--help must exit 0 and print usage even without camera/SDK."""
        import subprocess
        import sys
        from pathlib import Path

        script = str(
            Path(__file__).parent.parent / "tools" / "hikrobot_6led_live.py"
        )
        result = subprocess.run(
            [sys.executable, script, "--help"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert "6-LED" in result.stdout
        assert "--threshold" in result.stdout
        assert "--protocol" in result.stdout
        assert "REF" in result.stdout or "6-LED" in result.stdout
