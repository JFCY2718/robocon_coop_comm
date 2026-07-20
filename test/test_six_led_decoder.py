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

    def test_help_shows_new_adaptive_args(self) -> None:
        """--help shows the new adaptive and background-ring arguments."""
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
        for arg in ("--adaptive", "--ref-fraction", "--background-ring",
                     "--ring-ratio", "--contrast-floor"):
            assert arg in result.stdout, f"missing {arg} in --help"

    def test_help_shows_competition_pipeline_args(self) -> None:
        import subprocess
        import sys
        from pathlib import Path

        script = str(Path(__file__).parent.parent / "tools" / "hikrobot_6led_live.py")
        result = subprocess.run(
            [sys.executable, script, "--help"],
            capture_output=True, text=True, timeout=15,
        )
        for arg in (
            "--competition",
            "--sample-statistic",
            "--hysteresis-fraction",
            "--optical-flow",
            "--latest-frame",
            "--temporal-validate",
        ):
            assert arg in result.stdout, f"missing {arg} in --help"

    def test_fixed_roi_example_uses_frozen_six_led_order(self) -> None:
        import json
        from pathlib import Path

        path = (
            Path(__file__).parent.parent
            / "data"
            / "sixled"
            / "configs"
            / "sixled_roi.example.json"
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["led_order"] == ["D0", "D1", "D2", "D3", "REF", "PAR"]
        assert payload["bitmask_mapping"] == {
            "D0": 0,
            "D1": 1,
            "D2": 2,
            "D3": 3,
            "REF": 4,
            "PAR": 5,
        }


# ---------------------------------------------------------------------------
# Adaptive threshold
# ---------------------------------------------------------------------------


class TestAdaptiveThreshold:
    def test_ref_brightness_sets_threshold(self) -> None:
        """When adaptive is enabled, threshold = REF * ref_fraction."""
        d = SixLedRoiDecoder(adaptive_threshold=True, ref_fraction=0.5)
        # REF is a specific bright pixel region, others vary.
        img = np.full((480, 640), 30, dtype=np.uint8)
        # Make REF area bright (200), others dim (30).
        # roi_points_6 uses centre positions around (400, 300).
        roi = _roi_points_6()
        result = d.decode(_frame(img), roi)
        # REF ~30 (dim) → threshold = 30*0.5 = 15, REF_fraction fallback since < contrast_floor
        # All brightnesses ~30, so threshold = fallback 120
        # Actually REF = 30 which is < contrast_floor (default 15), so falls back to manual threshold 120
        # All < 120 → all off
        assert result.valid

    def test_adaptive_threshold_above_contrast_floor(self) -> None:
        """REF bright enough → threshold computed from REF."""
        d = SixLedRoiDecoder(
            adaptive_threshold=True, ref_fraction=0.5, contrast_floor=10.0,
        )
        # Set REF region to 200, others to 200 (so all > threshold)
        img = np.full((480, 640), 200, dtype=np.uint8)
        roi = _roi_points_6()
        result = d.decode(_frame(img), roi)
        # REF ~200, threshold = 200*0.5 = 100
        # All 200 > 100 → all on
        assert result.bits.get("D0", 0) == 1
        assert result.bits.get("REF", 0) == 1

    def test_adaptive_dim_scene_still_works(self) -> None:
        """Even with dimmer lights, adaptive threshold tracks REF."""
        d = SixLedRoiDecoder(
            adaptive_threshold=True, ref_fraction=0.5,
            min_roi_brightness=0.0, contrast_floor=10.0,
        )
        img = np.full((480, 640), 80, dtype=np.uint8)
        roi = _roi_points_6()
        result = d.decode(_frame(img), roi)
        # All ~80, REF ~80, threshold ~40, all on
        assert result.bits.get("REF", 0) == 1


# ---------------------------------------------------------------------------
# Background ring
# ---------------------------------------------------------------------------


class TestBackgroundRing:
    def test_ring_subtracts_ambient_offset(self) -> None:
        """Centre-bright ring-dim → positive contrast, light detected."""
        d = SixLedRoiDecoder(
            adaptive_threshold=True, ref_fraction=0.5,
            background_ring=True, ring_ratio=2.5,
            min_roi_brightness=-999.0, contrast_floor=5.0,
        )
        # Ambient @ 100, lights @ 200 centre → contrast = 100
        # Make image: all 100, then draw bright circles
        img = np.full((480, 640), 100, dtype=np.uint8)
        roi = _roi_points_6()
        for rp in roi:
            rr, cc = _circle_coords(rp.x_px, rp.y_px, rp.radius_px)
            img[rr, cc] = 200
        result = d.decode(_frame(img), roi)
        # Centre ~200, ring ~100 → contrast ~100 → all on
        assert result.bits.get("REF", 0) == 1
        # Effective threshold = REF contrast * 0.5 ~ 50
        assert d.effective_threshold > 0

    def test_uniform_image_no_contrast_all_off(self) -> None:
        """Uniform image → centre ≈ ring → contrast ≈ 0 → all off."""
        d = SixLedRoiDecoder(
            background_ring=True, ring_ratio=2.5,
            contrast_floor=5.0, threshold=50,
        )
        img = np.full((480, 640), 128, dtype=np.uint8)
        roi = _roi_points_6()
        result = d.decode(_frame(img), roi)
        # Uniform → centre-ring ≈ 0, below contrast_floor → all off
        assert result.bits.get("D0", 0) == 0
        assert result.bits.get("REF", 0) == 0
        assert result.valid is True


class TestCompetitionSampling:
    def test_percentile_sampling_tolerates_partial_led_coverage(self) -> None:
        roi = [RoiPoint(name="D0", x_px=100, y_px=100, radius_px=10)]
        img = np.full((220, 220), 20, dtype=np.uint8)
        cv2 = __import__("cv2")
        cv2.circle(img, (100, 100), 6, 220, -1)

        mean_result = SixLedRoiDecoder(
            threshold=120,
            sample_shape="circle",
            min_roi_brightness=0,
        ).decode(_frame(img), roi)
        percentile_result = SixLedRoiDecoder(
            threshold=120,
            sample_shape="circle",
            sample_statistic="percentile",
            centre_percentile=70,
            min_roi_brightness=0,
        ).decode(_frame(img), roi)

        assert mean_result.bits["D0"] == 0
        assert percentile_result.bits["D0"] == 1

    def test_hysteresis_retains_previous_bit_inside_deadband(self) -> None:
        roi = [RoiPoint(name="D0", x_px=100, y_px=100, radius_px=10)]
        decoder = SixLedRoiDecoder(
            threshold=100,
            hysteresis_fraction=0.1,
            min_roi_brightness=0,
        )
        on = decoder.decode(_frame(np.full((220, 220), 120, dtype=np.uint8)), roi)
        held = decoder.decode(_frame(np.full((220, 220), 105, dtype=np.uint8)), roi)
        off = decoder.decode(_frame(np.full((220, 220), 85, dtype=np.uint8)), roi)
        assert on.bits["D0"] == 1
        assert held.bits["D0"] == 1
        assert held.extra["uncertain_leds"] == ("D0",)
        assert off.bits["D0"] == 0

    def test_led_gain_compensates_a_dimmer_channel(self) -> None:
        roi = [RoiPoint(name="D0", x_px=100, y_px=100, radius_px=10)]
        decoder = SixLedRoiDecoder(
            threshold=100,
            led_gains={"D0": 1.5},
            min_roi_brightness=0,
        )
        result = decoder.decode(_frame(np.full((220, 220), 80, dtype=np.uint8)), roi)
        assert result.brightness["D0"] == pytest.approx(120.0)
        assert result.bits["D0"] == 1

    def test_saturation_guard_marks_reading_invalid(self) -> None:
        decoder = SixLedRoiDecoder(max_saturation_fraction=0.5)
        result = decoder.decode(
            _frame(np.full((480, 640), 255, dtype=np.uint8)),
            _roi_points_6(),
        )
        assert result.valid is False
        assert max(result.extra["saturation_fraction"].values()) == 1.0

    def test_background_ring_must_fit_inside_frame(self) -> None:
        decoder = SixLedRoiDecoder(
            background_ring=True,
            ring_ratio=2.5,
            min_roi_brightness=0,
        )
        roi = [RoiPoint(name="D0", x_px=15, y_px=15, radius_px=10)]
        result = decoder.decode(_frame(np.full((100, 100), 50, dtype=np.uint8)), roi)
        assert result.valid is False

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"sample_statistic": "median"}, "sample_statistic"),
            ({"hysteresis_fraction": 0.5}, "hysteresis_fraction"),
            ({"max_saturation_fraction": 1.1}, "max_saturation_fraction"),
            ({"led_gains": {"D0": 0}}, "led_gains"),
        ],
    )
    def test_invalid_robust_sampling_parameters(self, kwargs, message: str) -> None:
        with pytest.raises(ValueError, match=message):
            SixLedRoiDecoder(**kwargs)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _circle_coords(cx: int, cy: int, r: int) -> "tuple":
    """Return (row_indices, col_indices) for a filled circle, clamped to (0,480),(0,640)."""
    import numpy as np
    y0, y1 = max(0, cy - r), min(480, cy + r + 1)
    x0, x1 = max(0, cx - r), min(640, cx + r + 1)
    if y0 >= y1 or x0 >= x1:
        return np.array([], dtype=int), np.array([], dtype=int)
    yy, xx = np.ogrid[y0:y1, x0:x1]
    mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= r**2
    rows = y0 + np.where(mask)[0]
    cols = x0 + np.where(mask)[1]
    return rows, cols
