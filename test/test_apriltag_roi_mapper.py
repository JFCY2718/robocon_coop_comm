"""Comprehensive tests for AprilTag-guided LED ROI mapper.

Covers:
- RoiPoint dataclass
- AprilTagRoiMapper construction and validation
- Homography estimation from tag corners
- Point projection accuracy (axis-aligned + perspective)
- ROI clamping at image boundaries
- Factory method for_3led_below
- Integration: mapper → OpenCV homography → pixel projection
- Graceful failure when homography cannot be estimated
"""

from __future__ import annotations

import numpy as np
import pytest

from robocon_coop_comm.apriltag_roi_mapper import (
    AprilTagRoiMapper,
    RoiPoint,
    _estimate_homography,
    _pixels_per_mm,
    _project_point,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _square_corners(
    top_left: tuple[float, float] = (100.0, 100.0),
    size: float = 200.0,
) -> list[tuple[float, float]]:
    """Return axis-aligned square corners clockwise from top-left."""
    x, y = top_left
    return [
        (x, y),
        (x + size, y),
        (x + size, y + size),
        (x, y + size),
    ]


def _perspective_corners(
    tl: tuple[float, float] = (150.0, 80.0),
    tr: tuple[float, float] = (450.0, 100.0),
    br: tuple[float, float] = (420.0, 350.0),
    bl: tuple[float, float] = (120.0, 320.0),
) -> list[tuple[float, float]]:
    """Return perspective-distorted corners (simulates off-angle view)."""
    return [tl, tr, br, bl]


# ---------------------------------------------------------------------------
# RoiPoint
# ---------------------------------------------------------------------------


class TestRoiPoint:
    def test_construction(self) -> None:
        r = RoiPoint(name="D0", x_px=100, y_px=200, radius_px=12)
        assert r.name == "D0"
        assert r.x_px == 100
        assert r.y_px == 200
        assert r.radius_px == 12

    def test_is_frozen(self) -> None:
        r = RoiPoint(name="D0", x_px=1, y_px=2, radius_px=3)
        with pytest.raises(Exception):
            r.x_px = 99  # type: ignore[misc]

    def test_equality(self) -> None:
        a = RoiPoint(name="D0", x_px=1, y_px=2, radius_px=3)
        b = RoiPoint(name="D0", x_px=1, y_px=2, radius_px=3)
        c = RoiPoint(name="D0", x_px=4, y_px=2, radius_px=3)
        assert a == b
        assert a != c


# ---------------------------------------------------------------------------
# AprilTagRoiMapper — construction
# ---------------------------------------------------------------------------


class TestMapperConstruction:
    def test_default_construction(self) -> None:
        m = AprilTagRoiMapper(tag_size_mm=100.0)
        assert m.tag_size_mm == 100.0
        assert m.led_positions_mm == []
        assert m.full_tag_mm == pytest.approx(125.0)  # 100 * 10/8
        assert m.white_border_mm == pytest.approx(12.5)  # 100 / 8

    def test_tag_size_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="tag_size_mm"):
            AprilTagRoiMapper(tag_size_mm=0.0)

    def test_tag_size_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="tag_size_mm"):
            AprilTagRoiMapper(tag_size_mm=-50.0)

    def test_with_led_positions(self) -> None:
        positions = [("D0", 10.0, 50.0), ("D1", 50.0, 50.0)]
        m = AprilTagRoiMapper(tag_size_mm=80.0, led_positions_mm=positions)
        assert len(m.led_positions_mm) == 2
        assert m.led_positions_mm[0] == ("D0", 10.0, 50.0)

    def test_led_positions_are_copied(self) -> None:
        """Modifying the input list after construction must not affect the mapper."""
        positions = [("D0", 10.0, 50.0)]
        m = AprilTagRoiMapper(tag_size_mm=100.0, led_positions_mm=positions)
        positions.append(("D1", 99.0, 99.0))
        assert len(m.led_positions_mm) == 1

    def test_custom_led_radius(self) -> None:
        m = AprilTagRoiMapper(tag_size_mm=100.0, led_radius_mm=8.0)
        assert m.led_radius_mm == 8.0

    def test_full_tag_mm_scales_with_tag_size(self) -> None:
        m100 = AprilTagRoiMapper(tag_size_mm=100.0)
        m150 = AprilTagRoiMapper(tag_size_mm=150.0)
        assert m100.full_tag_mm == pytest.approx(125.0)
        assert m150.full_tag_mm == pytest.approx(187.5)

    def test_white_border_mm_scales_with_tag_size(self) -> None:
        m = AprilTagRoiMapper(tag_size_mm=160.0)
        assert m.white_border_mm == pytest.approx(20.0)  # 160/8


# ---------------------------------------------------------------------------
# AprilTagRoiMapper — map_rois (axis-aligned)
# ---------------------------------------------------------------------------


class TestMapRoisAxisAligned:
    """Tests with a perfectly axis-aligned tag (no perspective distortion)."""

    def test_single_led_centre_of_tag(self) -> None:
        """LED at the centre of the black border projects to image centre."""
        m = AprilTagRoiMapper(
            tag_size_mm=100.0,
            led_positions_mm=[("CENTER", 50.0, 50.0)],
        )
        # Tag outer (white border) = 125mm → 250px square in image.
        corners = _square_corners(top_left=(100.0, 100.0), size=250.0)
        rois, H = m.map_rois(corners, image_shape=(480, 640))

        assert len(rois) == 1
        r = rois[0]
        assert r.name == "CENTER"
        # LED at (12.5+50, 12.5+50) = (62.5, 62.5) mm in tag frame
        # Tag maps [0,125]mm → [100,350]px, so 62.5mm → 225px
        assert r.x_px == 225
        assert r.y_px == 225
        assert r.radius_px > 0
        assert H is not None

    def test_led_at_black_border_top_left(self) -> None:
        """LED at (0,0) relative to black border → top-left of black border."""
        m = AprilTagRoiMapper(
            tag_size_mm=100.0,
            led_positions_mm=[("D0", 0.0, 0.0)],
        )
        corners = _square_corners(top_left=(100.0, 100.0), size=250.0)
        rois, H = m.map_rois(corners, image_shape=(480, 640))

        # White border = 12.5mm. At 2 px/mm: 12.5*2 = 25px offset from tag top-left
        # Tag top-left=100, so black top-left = 125
        assert rois[0].x_px == 125
        assert rois[0].y_px == 125

    def test_led_at_black_border_bottom_right(self) -> None:
        """LED at (tag_size_mm, tag_size_mm) = bottom-right of black border."""
        m = AprilTagRoiMapper(
            tag_size_mm=100.0,
            led_positions_mm=[("CORNER", 100.0, 100.0)],
        )
        corners = _square_corners(top_left=(100.0, 100.0), size=250.0)
        rois, H = m.map_rois(corners, image_shape=(480, 640))

        # White border 12.5mm + 100mm = 112.5mm in tag frame
        # At 2 px/mm: 112.5*2 = 225px from tag top-left 100 = 325
        assert rois[0].x_px == 325
        assert rois[0].y_px == 325

    def test_no_leds_configured_returns_empty(self) -> None:
        m = AprilTagRoiMapper(tag_size_mm=100.0)
        corners = _square_corners()
        rois, H = m.map_rois(corners, image_shape=(480, 640))
        assert rois == []
        assert H is not None

    def test_radius_scales_with_resolution(self) -> None:
        """LED radius in pixels should be larger for higher-resolution images."""
        m = AprilTagRoiMapper(
            tag_size_mm=100.0,
            led_positions_mm=[("D0", 50.0, 50.0)],
            led_radius_mm=5.0,
        )
        # Small tag in image → few px/mm.
        corners_small = _square_corners(size=125.0)  # 125px = 125mm → 1 px/mm
        rois_small, _ = m.map_rois(corners_small, image_shape=(240, 320))

        # Large tag in image → more px/mm.
        corners_large = _square_corners(size=500.0)  # 500px = 125mm → 4 px/mm
        rois_large, _ = m.map_rois(corners_large, image_shape=(960, 1280))

        assert rois_small[0].radius_px < rois_large[0].radius_px


# ---------------------------------------------------------------------------
# AprilTagRoiMapper — map_rois (perspective)
# ---------------------------------------------------------------------------


class TestMapRoisPerspective:
    """Tests with perspective-distorted tag corners (simulates angled camera)."""

    def test_perspective_projection_returns_valid_points(self) -> None:
        m = AprilTagRoiMapper(
            tag_size_mm=100.0,
            led_positions_mm=[("D0", 10.0, 10.0), ("D1", 90.0, 10.0)],
        )
        corners = _perspective_corners()
        rois, H = m.map_rois(corners, image_shape=(480, 640))

        assert len(rois) == 2
        assert H is not None
        # Both points should be within image bounds.
        for r in rois:
            assert 0 <= r.x_px < 640
            assert 0 <= r.y_px < 480

    def test_perspective_leds_shift_relative_to_tag(self) -> None:
        """LEDs placed differently in tag space project to different image coords."""
        m = AprilTagRoiMapper(
            tag_size_mm=100.0,
            led_positions_mm=[
                ("LEFT", 0.0, 50.0),
                ("RIGHT", 100.0, 50.0),
            ],
        )
        corners = _perspective_corners()
        rois, H = m.map_rois(corners, image_shape=(480, 640))

        assert rois[0].x_px < rois[1].x_px  # LEFT is left of RIGHT in image
        # y should be similar (both at same tag y).
        assert abs(rois[0].y_px - rois[1].y_px) < 50

    def test_homography_is_usable_by_opencv(self) -> None:
        """The returned homography matrix should be directly usable with cv2."""
        import cv2

        m = AprilTagRoiMapper(
            tag_size_mm=100.0,
            led_positions_mm=[("D0", 50.0, 50.0)],
        )
        corners = _perspective_corners()
        _, H = m.map_rois(corners, image_shape=(480, 640))

        assert H is not None
        # Use OpenCV perspectiveTransform to project a point.
        # perspectiveTransform expects shape (N, 2) or (N, 1, 2).
        pt = np.array([[62.5, 62.5]], dtype=np.float32)  # tag centre in mm, shape (1,2)
        result = cv2.perspectiveTransform(pt.reshape(1, 1, 2), H)
        assert result.shape == (1, 1, 2)


# ---------------------------------------------------------------------------
# AprilTagRoiMapper — map_rois edge cases
# ---------------------------------------------------------------------------


class TestMapRoisEdgeCases:
    def test_roi_clamped_to_image_bounds(self) -> None:
        """LED far outside the tag should be clamped to image boundary."""
        m = AprilTagRoiMapper(
            tag_size_mm=100.0,
            led_positions_mm=[("FAR", 500.0, 500.0)],  # way beyond tag
        )
        corners = _square_corners(top_left=(10.0, 10.0), size=125.0)
        rois, H = m.map_rois(corners, image_shape=(240, 320))

        assert rois[0].x_px < 320
        assert rois[0].y_px < 240

    def test_negative_corner_coordinates_handled(self) -> None:
        """Tag partially outside image (negative coords) should still work."""
        m = AprilTagRoiMapper(
            tag_size_mm=100.0,
            led_positions_mm=[("D0", 50.0, 50.0)],
        )
        # Tag extends above/left of image origin.
        corners = [(-10.0, -10.0), (115.0, -10.0), (115.0, 115.0), (-10.0, 115.0)]
        rois, H = m.map_rois(corners, image_shape=(480, 640))

        assert len(rois) == 1
        assert rois[0].x_px >= 0
        assert rois[0].y_px >= 0

    def test_frame_with_different_resolutions(self) -> None:
        """Same physical setup, different camera resolutions → different pixel coords."""
        m = AprilTagRoiMapper(
            tag_size_mm=100.0,
            led_positions_mm=[("D0", 50.0, 50.0)],
        )
        corners = _square_corners(size=250.0)
        rois_lo, _ = m.map_rois(corners, image_shape=(480, 640))
        rois_hi, _ = m.map_rois(corners, image_shape=(960, 1280))

        # Same tag in same pixel coords, but different image shape →
        # ROI coords should be identical (tag occupies same pixels).
        assert rois_lo[0].x_px == rois_hi[0].x_px
        assert rois_lo[0].y_px == rois_hi[0].y_px

    def test_wrong_number_of_corners_raises(self) -> None:
        m = AprilTagRoiMapper(
            tag_size_mm=100.0,
            led_positions_mm=[("D0", 50.0, 50.0)],
        )
        with pytest.raises(ValueError, match="Expected 4 tag corners"):
            m.map_rois([(0, 0), (1, 0), (1, 1)], image_shape=(480, 640))


# ---------------------------------------------------------------------------
# _estimate_homography
# ---------------------------------------------------------------------------


class TestEstimateHomography:
    def test_axis_aligned_square(self) -> None:
        corners = _square_corners()
        H = _estimate_homography(corners, full_tag_mm=125.0)
        assert H is not None
        H_arr = np.asarray(H)
        assert H_arr.shape == (3, 3)

    def test_perspective_distorted(self) -> None:
        corners = _perspective_corners()
        H = _estimate_homography(corners, full_tag_mm=125.0)
        assert H is not None

    def test_identity_when_corners_match_expected_mm(self) -> None:
        """When image pixels == mm coords, homography should be near-identity."""
        # 125mm full tag → corners at exactly those pixel coords.
        corners = [
            (0.0, 0.0),
            (125.0, 0.0),
            (125.0, 125.0),
            (0.0, 125.0),
        ]
        H = _estimate_homography(corners, full_tag_mm=125.0)
        assert H is not None
        H_arr = np.asarray(H)
        # Should be identity (within numerical tolerance).
        assert H_arr[0, 0] == pytest.approx(1.0, abs=0.01)
        assert H_arr[1, 1] == pytest.approx(1.0, abs=0.01)
        assert H_arr[0, 2] == pytest.approx(0.0, abs=0.1)
        assert H_arr[1, 2] == pytest.approx(0.0, abs=0.1)

    def test_collinear_corners_returns_none(self) -> None:
        """Three+ collinear corners should fail homography estimation."""
        # All corners on the same line.
        corners = [
            (0.0, 0.0),
            (100.0, 0.0),
            (200.0, 0.0),
            (300.0, 0.0),
        ]
        H = _estimate_homography(corners, full_tag_mm=125.0)
        assert H is None

    def test_duplicate_corners_returns_none(self) -> None:
        corners = [(0.0, 0.0), (0.0, 0.0), (0.0, 0.0), (0.0, 0.0)]
        H = _estimate_homography(corners, full_tag_mm=125.0)
        assert H is None


# ---------------------------------------------------------------------------
# _project_point
# ---------------------------------------------------------------------------


class TestProjectPoint:
    def test_identity_homography(self) -> None:
        """With an identity homography, mm coords map 1:1 to pixel coords."""
        identity = np.eye(3, dtype=np.float64)
        px, py = _project_point(identity, 42.0, 73.5)
        assert px == 42
        assert py == 74  # rounded

    def test_scale_translation(self) -> None:
        """Homography with scale=2 and translation=(10,20)."""
        H = np.array(
            [[2.0, 0.0, 10.0], [0.0, 2.0, 20.0], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )
        px, py = _project_point(H, 5.0, 7.0)
        # x = 2*5 + 10 = 20
        # y = 2*7 + 20 = 34
        assert px == 20
        assert py == 34

    def test_perspective_division(self) -> None:
        """Homography with non-trivial perspective (w != 1)."""
        H = np.array(
            [[4.0, 0.0, 10.0], [0.0, 4.0, 20.0], [0.01, 0.0, 2.0]],
            dtype=np.float64,
        )
        px, py = _project_point(H, 5.0, 10.0)
        # w = 0.01*5 + 2 = 2.05
        # x = (4*5 + 10) / 2.05 = 30/2.05 ≈ 14.63 → 15
        # y = (4*10 + 20) / 2.05 = 60/2.05 ≈ 29.27 → 29
        assert px == 15
        assert py == 29


# ---------------------------------------------------------------------------
# _pixels_per_mm
# ---------------------------------------------------------------------------


class TestPixelsPerMm:
    def test_with_identity_homography(self) -> None:
        identity = np.eye(3, dtype=np.float64)
        ppm = _pixels_per_mm(identity, full_tag_mm=100.0)
        assert ppm == pytest.approx(1.0)  # 1 mm = 1 px

    def test_with_scale_2_homography(self) -> None:
        H = np.array(
            [[2.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )
        ppm = _pixels_per_mm(H, full_tag_mm=100.0)
        assert ppm == pytest.approx(2.0)

    def test_with_perspective_homography(self) -> None:
        """Even with perspective, near tag centre the scale should be reasonable."""
        corners = _perspective_corners()
        H = _estimate_homography(corners, full_tag_mm=125.0)
        assert H is not None
        ppm = _pixels_per_mm(H, full_tag_mm=125.0)
        # Tag ~300px wide for 125mm → roughly 2.4 px/mm.
        assert 1.0 < ppm < 10.0


# ---------------------------------------------------------------------------
# AprilTagRoiMapper.for_3led_below factory
# ---------------------------------------------------------------------------


class TestFor3LedBelow:
    def test_default_spacing(self) -> None:
        m = AprilTagRoiMapper.for_3led_below(tag_size_mm=150.0)
        positions = m.led_positions_mm
        assert len(positions) == 3
        assert positions[0][0] == "D0"
        assert positions[1][0] == "D1"
        assert positions[2][0] == "D2"
        # Default spacing = tag_size_mm / 3 = 50mm.
        assert positions[0][1] == pytest.approx(0.0)  # x of D0
        assert positions[1][1] == pytest.approx(50.0)  # x of D1
        assert positions[2][1] == pytest.approx(100.0)  # x of D2
        # y = tag_size_mm + gap = 150 + 10 = 160.
        assert positions[0][2] == pytest.approx(160.0)

    def test_custom_spacing_and_offset(self) -> None:
        m = AprilTagRoiMapper.for_3led_below(
            tag_size_mm=100.0,
            d0_offset_mm=5.0,
            spacing_mm=30.0,
            gap_below_tag_mm=15.0,
            led_radius_mm=7.0,
        )
        positions = m.led_positions_mm
        assert positions[0] == ("D0", 5.0, 115.0)
        assert positions[1] == ("D1", 35.0, 115.0)
        assert positions[2] == ("D2", 65.0, 115.0)
        assert m.led_radius_mm == 7.0
        assert m.tag_size_mm == 100.0

    def test_projects_correctly_with_corners(self) -> None:
        m = AprilTagRoiMapper.for_3led_below(tag_size_mm=100.0)
        corners = _square_corners(top_left=(100.0, 100.0), size=250.0)
        rois, H = m.map_rois(corners, image_shape=(480, 640))

        assert len(rois) == 3
        # D0 should be left of D1, D1 left of D2.
        assert rois[0].x_px < rois[1].x_px < rois[2].x_px
        # All should be below the tag (higher y than tag centre).
        tag_centre_y = corners[0][1] + 125.0  # 100 + 125 = 225
        for r in rois:
            assert r.y_px > tag_centre_y
        assert H is not None


# ---------------------------------------------------------------------------
# Integration: mapper output → roi_mean → decode (simulated)
# ---------------------------------------------------------------------------


class TestIntegrationWithRoiDecoder:
    """End-to-end: mapper projects ROI → roi_mean samples → decode_3led."""

    def test_mapper_to_roi_mean_pipeline(self) -> None:
        """Simulate: synthetic image with 'LEDs' at known positions, decode them."""
        from robocon_coop_comm.hikrobot_frame_provider import roi_mean

        # Create synthetic grayscale image with bright spots at expected LED positions.
        img = np.full((480, 640), 20, dtype=np.uint8)

        # Tag at (100,100) → (350,350).
        corners = _square_corners(top_left=(100.0, 100.0), size=250.0)

        m = AprilTagRoiMapper.for_3led_below(
            tag_size_mm=100.0,
            gap_below_tag_mm=20.0,
        )
        rois, H = m.map_rois(corners, image_shape=(480, 640))

        # Paint bright "LED" spots at the projected ROI centres.
        for r in rois:
            cv2 = __import__("cv2")
            cv2.circle(img, (r.x_px, r.y_px), r.radius_px, 220, -1)

        # Sample via roi_mean.
        brightnesses = [roi_mean(img, r.x_px, r.y_px, r.radius_px * 2) for r in rois]

        # D0 = ON (220>120), D1 = ON, D2 = ON → msg_id=7.
        for b in brightnesses:
            assert b > 120.0

    def test_mapper_cold_leds(self) -> None:
        """When LEDs are off, roi_mean should read low brightness."""
        from robocon_coop_comm.hikrobot_frame_provider import roi_mean

        # Dark image.
        img = np.full((480, 640), 10, dtype=np.uint8)
        corners = _square_corners(top_left=(100.0, 100.0), size=250.0)

        m = AprilTagRoiMapper.for_3led_below(tag_size_mm=100.0)
        rois, _ = m.map_rois(corners, image_shape=(480, 640))

        brightnesses = [roi_mean(img, r.x_px, r.y_px, 24) for r in rois]
        for b in brightnesses:
            assert b < 50.0  # dark image, all LEDs off

    def test_mapper_perspective_with_synthetic_leds(self) -> None:
        """Perspective-distorted tag → project LEDs → verify they're in expected region."""
        img = np.full((480, 640), 50, dtype=np.uint8)

        # Mild perspective (simulates camera at slight angle).
        corners = [
            (220.0, 90.0),  # tl
            (460.0, 80.0),  # tr
            (470.0, 340.0),  # br
            (210.0, 350.0),  # bl
        ]

        m = AprilTagRoiMapper.for_3led_below(tag_size_mm=100.0)
        rois, H = m.map_rois(corners, image_shape=(480, 640))
        assert H is not None

        # All ROIs should be within image.
        for r in rois:
            assert 0 <= r.x_px < 640
            assert 0 <= r.y_px < 480

        # LEDs should be in the lower portion of the image
        # (below tag vertical centre, since LEDs are mounted below the tag).
        tag_centre_y = sum(c[1] for c in corners) / 4
        for r in rois:
            assert r.y_px > tag_centre_y, f"{r.name} y={r.y_px} should be below tag centre {tag_centre_y:.0f}"
