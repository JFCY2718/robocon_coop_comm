"""Tests for AprilTagBeaconDecoder — the real-hardware beacon decode pipeline.

Covers:
- No tag detected → invalid result
- Tag ID mismatch → invalid result
- Successful decode with synthetic image + mock detections
- SEQ tracking across frames
- Brightness threshold gating
- Homography failure handling
- Reset behaviour
- Null/empty image handling
"""

from __future__ import annotations
from unittest import mock

import numpy as np
import pytest

from robocon_coop_comm.beacon_decoder_apriltag import AprilTagBeaconDecoder
from robocon_coop_comm.beacon_types import BeaconFrame
from robocon_coop_comm.apriltag_detector import TagDetection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_detector(
    detections: list | None = None,
    raise_on_detect: Exception | None = None,
):
    """Build a mock ApriltagDetector."""
    det = mock.MagicMock()
    if raise_on_detect:
        det.detect.side_effect = raise_on_detect
    else:
        det.detect.return_value = detections or []
    return det


def _mock_mapper(
    roi_points: list | None = None,
    homography: object = np.eye(3),
    raise_on_map: Exception | None = None,
):
    """Build a mock AprilTagRoiMapper."""
    m = mock.MagicMock()
    if raise_on_map:
        m.map_rois.side_effect = raise_on_map
    else:
        m.map_rois.return_value = (roi_points or [], homography)
    return m


def _tag_detection(
    tag_id: int = 0,
    family: str = "tag36h11",
    decision_margin: float = 50.0,
    corners: list | None = None,
) -> TagDetection:
    if corners is None:
        corners = [
            (100.0, 100.0),
            (300.0, 100.0),
            (300.0, 300.0),
            (100.0, 300.0),
        ]
    return TagDetection(
        tag_id=tag_id,
        family=family,
        corners=corners,
        center=(200.0, 200.0),
        decision_margin=decision_margin,
    )


def _frame(image: np.ndarray | None = None, source: str = "test") -> BeaconFrame:
    if image is None:
        image = np.full((480, 640), 128, dtype=np.uint8)
    return BeaconFrame(image=image, source=source, frame_id=0)


def _dummy_roi_points():
    """Return 3 ROI points matching D0/D1/D2 for testing."""
    from robocon_coop_comm.apriltag_roi_mapper import RoiPoint

    return [
        RoiPoint(name="D0", x_px=150, y_px=400, radius_px=12),
        RoiPoint(name="D1", x_px=320, y_px=410, radius_px=12),
        RoiPoint(name="D2", x_px=490, y_px=400, radius_px=12),
    ]


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_default_construction(self) -> None:
        det = _mock_detector()
        mapper = _mock_mapper()
        d = AprilTagBeaconDecoder(det, mapper)
        assert d._target_tag_id == 0
        assert d._threshold == 120
        assert d._seq == 0
        assert d._last_msg_id is None

    def test_custom_params(self) -> None:
        det = _mock_detector()
        mapper = _mock_mapper()
        d = AprilTagBeaconDecoder(
            det, mapper, target_tag_id=5, threshold=150
        )
        assert d._target_tag_id == 5
        assert d._threshold == 150


# ---------------------------------------------------------------------------
# decode — no detection cases
# ---------------------------------------------------------------------------


class TestDecodeNoDetection:
    def test_null_image_returns_invalid(self) -> None:
        det = _mock_detector()
        mapper = _mock_mapper()
        d = AprilTagBeaconDecoder(det, mapper)
        frame = BeaconFrame(image=None, source="test", frame_id=0)
        result = d.decode(frame)
        assert result.valid is False
        assert result.reason == "null_image"

    def test_no_tags_detected_returns_invalid(self) -> None:
        det = _mock_detector(detections=[])
        mapper = _mock_mapper()
        d = AprilTagBeaconDecoder(det, mapper)
        result = d.decode(_frame())
        assert result.valid is False
        assert result.reason == "no_tag_detected"

    def test_detector_raises_returns_invalid(self) -> None:
        det = _mock_detector(raise_on_detect=RuntimeError("boom"))
        mapper = _mock_mapper()
        d = AprilTagBeaconDecoder(det, mapper)
        result = d.decode(_frame())
        assert result.valid is False
        assert "apriltag_detect_error" in result.reason

    def test_tag_id_mismatch(self) -> None:
        """When target_tag_id is set and no matching tag is found."""
        det = _mock_detector(detections=[
            _tag_detection(tag_id=1, decision_margin=50.0),
            _tag_detection(tag_id=2, decision_margin=30.0),
        ])
        mapper = _mock_mapper()
        d = AprilTagBeaconDecoder(det, mapper, target_tag_id=0)
        result = d.decode(_frame())
        assert result.valid is False
        assert "tag_id_mismatch" in result.reason
        assert "wanted 0" in result.reason


# ---------------------------------------------------------------------------
# decode — successful path (synthetic)
# ---------------------------------------------------------------------------


class TestDecodeSuccess:
    def test_all_leds_on_decodes_msg_id_7(self) -> None:
        """D0=1, D1=1, D2=1 → msg_id=7."""
        roi_pts = _dummy_roi_points()
        det = _mock_detector(detections=[_tag_detection()])
        mapper = _mock_mapper(roi_points=roi_pts)
        d = AprilTagBeaconDecoder(det, mapper, threshold=120)

        # Image with bright spots at ROI centres → all LEDs ON.
        img = np.full((480, 640), 20, dtype=np.uint8)
        for rp in roi_pts:
            cv2 = __import__("cv2")
            cv2.circle(img, (rp.x_px, rp.y_px), rp.radius_px, 220, -1)

        result = d.decode(_frame(img))
        assert result.valid is True
        assert result.msg_id == 7
        assert result.confidence > 0.0

    def test_all_leds_off_decodes_msg_id_0(self) -> None:
        """D0=0, D1=0, D2=0 → msg_id=0."""
        roi_pts = _dummy_roi_points()
        det = _mock_detector(detections=[_tag_detection()])
        mapper = _mock_mapper(roi_points=roi_pts)
        d = AprilTagBeaconDecoder(det, mapper, threshold=120)

        # Dark image → all LEDs OFF.
        img = np.full((480, 640), 10, dtype=np.uint8)
        result = d.decode(_frame(img))
        assert result.valid is True
        assert result.msg_id == 0

    def test_d0_on_d1_off_d2_off_decodes_msg_id_1(self) -> None:
        """D0=1, D1=0, D2=0 → msg_id=1."""
        roi_pts = _dummy_roi_points()
        det = _mock_detector(detections=[_tag_detection()])
        mapper = _mock_mapper(roi_points=roi_pts)
        d = AprilTagBeaconDecoder(det, mapper, threshold=120)

        img = np.full((480, 640), 10, dtype=np.uint8)
        cv2 = __import__("cv2")
        cv2.circle(img, (roi_pts[0].x_px, roi_pts[0].y_px), roi_pts[0].radius_px, 220, -1)

        result = d.decode(_frame(img))
        assert result.valid is True
        assert result.msg_id == 1

    def test_threshold_gating(self) -> None:
        """Brightness just below threshold → LED OFF; just above → LED ON."""
        roi_pts = _dummy_roi_points()
        det = _mock_detector(detections=[_tag_detection()])
        mapper = _mock_mapper(roi_points=roi_pts)

        # Threshold = 120.
        d = AprilTagBeaconDecoder(det, mapper, threshold=120)

        # Brightness = 119 → OFF.
        img_dim = np.full((480, 640), 119, dtype=np.uint8)
        result_dim = d.decode(_frame(img_dim))
        assert result_dim.msg_id == 0  # all OFF

        # Brightness = 121 → ON.
        img_bright = np.full((480, 640), 121, dtype=np.uint8)
        result_bright = d.decode(_frame(img_bright))
        assert result_bright.msg_id == 7  # all ON


# ---------------------------------------------------------------------------
# SEQ tracking
# ---------------------------------------------------------------------------


class TestSeqTracking:
    def test_seq_toggles_when_msg_id_changes(self) -> None:
        roi_pts = _dummy_roi_points()
        det = _mock_detector(detections=[_tag_detection()])
        mapper = _mock_mapper(roi_points=roi_pts)
        d = AprilTagBeaconDecoder(det, mapper, threshold=120)

        # Frame 1: msg_id=1 (only D0 on).
        img1 = np.full((480, 640), 10, dtype=np.uint8)
        cv2 = __import__("cv2")
        cv2.circle(img1, (roi_pts[0].x_px, roi_pts[0].y_px), roi_pts[0].radius_px, 220, -1)
        r1 = d.decode(_frame(img1))
        assert r1.msg_id == 1
        seq1 = r1.seq

        # Frame 2: same msg_id → seq unchanged.
        r2 = d.decode(_frame(img1.copy()))
        assert r2.msg_id == 1
        assert r2.seq == seq1

        # Frame 3: msg_id changes to 7 → seq toggles.
        img3 = np.full((480, 640), 10, dtype=np.uint8)
        for rp in roi_pts:
            cv2.circle(img3, (rp.x_px, rp.y_px), rp.radius_px, 220, -1)
        r3 = d.decode(_frame(img3))
        assert r3.msg_id == 7
        assert r3.seq != seq1

    def test_seq_not_toggled_on_first_frame(self) -> None:
        """First frame initialises last_msg_id without toggling seq."""
        roi_pts = _dummy_roi_points()
        det = _mock_detector(detections=[_tag_detection()])
        mapper = _mock_mapper(roi_points=roi_pts)
        d = AprilTagBeaconDecoder(det, mapper)
        assert d._seq == 0
        assert d._last_msg_id is None

        img = np.full((480, 640), 220, dtype=np.uint8)
        result = d.decode(_frame(img))
        assert d._last_msg_id is not None
        assert d._seq == 0  # still 0 (first frame initialises, doesn't toggle)


# ---------------------------------------------------------------------------
# Homography failure
# ---------------------------------------------------------------------------


class TestHomographyFailure:
    def test_mapper_returns_empty_rois(self) -> None:
        det = _mock_detector(detections=[_tag_detection()])
        mapper = _mock_mapper(roi_points=[], homography=None)
        d = AprilTagBeaconDecoder(det, mapper)
        result = d.decode(_frame())
        assert result.valid is False
        assert result.reason == "homography_failed"

    def test_mapper_raises(self) -> None:
        det = _mock_detector(detections=[_tag_detection()])
        mapper = _mock_mapper(raise_on_map=ValueError("bad corners"))
        d = AprilTagBeaconDecoder(det, mapper)
        result = d.decode(_frame())
        assert result.valid is False
        assert "roi_projection_error" in result.reason


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_seq_clears_tracking(self) -> None:
        roi_pts = _dummy_roi_points()
        det = _mock_detector(detections=[_tag_detection()])
        mapper = _mock_mapper(roi_points=roi_pts)
        d = AprilTagBeaconDecoder(det, mapper)

        # Process one frame to set last_msg_id and seq.
        img = np.full((480, 640), 220, dtype=np.uint8)
        d.decode(_frame(img))
        assert d._last_msg_id is not None

        d.reset_seq()
        assert d._last_msg_id is None
        assert d._seq == 0


# ---------------------------------------------------------------------------
# Target tag selection (best decision margin)
# ---------------------------------------------------------------------------


class TestTargetTagSelection:
    def test_picks_best_decision_margin_when_multiple_match(self) -> None:
        """When multiple tags match target_tag_id, pick the highest dm."""
        det = _mock_detector(detections=[
            _tag_detection(tag_id=0, decision_margin=30.0),
            _tag_detection(tag_id=0, decision_margin=70.0),  # best
            _tag_detection(tag_id=1, decision_margin=90.0),  # better dm but wrong id
        ])
        roi_pts = _dummy_roi_points()
        mapper = _mock_mapper(roi_points=roi_pts)
        d = AprilTagBeaconDecoder(det, mapper, target_tag_id=0)

        # mapper.map_rois should receive corners from the dm=70.0 tag.
        img = np.full((480, 640), 220, dtype=np.uint8)
        d.decode(_frame(img))

        # Verify mapper was called with the best-matching tag's corners.
        called_corners = mapper.map_rois.call_args[0][0]
        best_tag = _tag_detection(tag_id=0, decision_margin=70.0)
        assert called_corners == best_tag.corners

    def test_no_target_tag_id_uses_best_overall(self) -> None:
        """When target_tag_id is None, use the best dm regardless of id."""
        det = _mock_detector(detections=[
            _tag_detection(tag_id=3, decision_margin=50.0),
            _tag_detection(tag_id=0, decision_margin=80.0),
        ])
        roi_pts = _dummy_roi_points()
        mapper = _mock_mapper(roi_points=roi_pts)
        d = AprilTagBeaconDecoder(det, mapper, target_tag_id=None)

        img = np.full((480, 640), 220, dtype=np.uint8)
        d.decode(_frame(img))

        # Should use tag_id=0 (dm=80).
        called_corners = mapper.map_rois.call_args[0][0]
        best_tag = _tag_detection(tag_id=0, decision_margin=80.0)
        assert called_corners == best_tag.corners


# ---------------------------------------------------------------------------
# BGR image handling
# ---------------------------------------------------------------------------


class TestBgrImage:
    def test_bgr_image_decoded_correctly(self) -> None:
        """roi_mean handles BGR images internally — decoder should work."""
        roi_pts = _dummy_roi_points()
        det = _mock_detector(detections=[_tag_detection()])
        mapper = _mock_mapper(roi_points=roi_pts)
        d = AprilTagBeaconDecoder(det, mapper, threshold=120)

        # BGR image with bright LEDs.
        bgr = np.full((480, 640, 3), 20, dtype=np.uint8)
        cv2 = __import__("cv2")
        for rp in roi_pts:
            cv2.circle(bgr, (rp.x_px, rp.y_px), rp.radius_px, (220, 220, 220), -1)

        result = d.decode(_frame(bgr))
        assert result.valid is True
        assert result.msg_id == 7


# ---------------------------------------------------------------------------
# Confidence heuristic
# ---------------------------------------------------------------------------


class TestConfidence:
    def test_confidence_near_zero_when_brightness_near_threshold(self) -> None:
        roi_pts = _dummy_roi_points()
        det = _mock_detector(detections=[_tag_detection()])
        mapper = _mock_mapper(roi_points=roi_pts)
        d = AprilTagBeaconDecoder(det, mapper, threshold=120)

        # Brightness = threshold ± 1 → very low confidence.
        img = np.full((480, 640), 121, dtype=np.uint8)
        result = d.decode(_frame(img))
        assert result.confidence < 0.1  # margin of 1 → ~0.01

    def test_confidence_high_when_brightness_far_from_threshold(self) -> None:
        roi_pts = _dummy_roi_points()
        det = _mock_detector(detections=[_tag_detection()])
        mapper = _mock_mapper(roi_points=roi_pts)
        d = AprilTagBeaconDecoder(det, mapper, threshold=120)

        # Brightness = 255 → margin of 135 → confidence = 1.0 (clamped).
        img = np.full((480, 640), 255, dtype=np.uint8)
        result = d.decode(_frame(img))
        assert result.confidence == 1.0
