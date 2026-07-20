"""Synthetic tests for the AprilTag-guided six-LED pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import cv2
import numpy as np
import pytest

from robocon_coop_comm.apriltag_detector import TagDetection
from robocon_coop_comm.beacon_geometry import BeaconGeometry, LED_ORDER
from robocon_coop_comm.beacon_types import BeaconFrame
from robocon_coop_comm.dynamic_sixled import DynamicSixLedTracker, SixLedHomographyProjector
from robocon_coop_comm.six_led_decoder import SixLedRoiDecoder


TAG_CORNERS = [(225.0, 325.0), (375.0, 325.0), (375.0, 475.0), (225.0, 475.0)]


def _tag(**overrides) -> TagDetection:
    values = {
        "tag_id": 0,
        "family": "tag36h11",
        "corners": TAG_CORNERS,
        "center": (300.0, 400.0),
        "decision_margin": 50.0,
        "hamming": 0,
    }
    values.update(overrides)
    return TagDetection(**values)


def _frame(frame_id: int = 1) -> BeaconFrame:
    return BeaconFrame(np.full((800, 900), 20, dtype=np.uint8), "synthetic", frame_id)


def test_default_geometry_and_fixed_bit_order() -> None:
    geometry = BeaconGeometry()
    assert geometry.board_width_mm == 280.0
    assert geometry.board_height_mm == 220.0
    assert geometry.tag_size_mm == 150.0
    assert geometry.tag_center_mm == (-55.0, 0.0)
    assert geometry.led_cap_radius_mm == 11.2
    assert geometry.roi_radius_mm == pytest.approx(7.28)
    assert geometry.led_centers_tag_mm == (
        ("D0", 95.0, 70.0),
        ("D1", 135.0, 70.0),
        ("D2", 175.0, 70.0),
        ("D3", 95.0, 20.0),
        ("REF", 135.0, 20.0),
        ("PAR", 175.0, 20.0),
    )
    assert tuple(name for name, _, _ in geometry.led_centers_mm) == LED_ORDER


def test_geometry_json_override_preserves_order() -> None:
    payload = json.dumps({"tag_size_mm": 149.2, "roi_radius_scale": 0.6})
    with mock.patch.object(Path, "open", mock.mock_open(read_data=payload)):
        geometry = BeaconGeometry.from_json("layout.json")
    assert geometry.tag_size_mm == 149.2
    assert geometry.roi_radius_scale == 0.6
    assert tuple(name for name, _, _ in geometry.led_centers_mm) == LED_ORDER


def test_competition_geometry_file_loads() -> None:
    path = (
        Path(__file__).parent.parent
        / "data"
        / "sixled"
        / "configs"
        / "competition_beacon_320x240.json"
    )
    geometry = BeaconGeometry.from_json(path)
    assert geometry.board_width_mm == 320.0
    assert geometry.board_height_mm == 240.0
    assert geometry.tag_size_mm == 150.0
    assert tuple(name for name, _, _ in geometry.led_centers_mm) == LED_ORDER


def test_known_homography_projects_all_six_leds() -> None:
    result = SixLedHomographyProjector(BeaconGeometry()).project(TAG_CORNERS, (800, 900))
    assert result.valid is True
    assert [(r.name, r.x_px, r.y_px) for r in result.rois] == [
        ("D0", 395, 330), ("D1", 435, 330), ("D2", 475, 330),
        ("D3", 395, 380), ("REF", 435, 380), ("PAR", 475, 380),
    ]


def test_roi_radius_follows_tag_scale() -> None:
    projector = SixLedHomographyProjector(BeaconGeometry())
    normal = projector.project(TAG_CORNERS, (1000, 1200))
    doubled = projector.project(
        [(150.0, 250.0), (450.0, 250.0), (450.0, 550.0), (150.0, 550.0)],
        (1200, 1600),
    )
    assert normal.valid and doubled.valid
    assert normal.rois[0].radius_px == 7
    assert doubled.rois[0].radius_px == 15
    ratio = doubled.rois[0].radius_px / normal.rois[0].radius_px
    assert 1.8 <= ratio <= 2.2


def test_perspective_projection_stays_ordered_and_finite() -> None:
    result = SixLedHomographyProjector(BeaconGeometry()).project(
        [(250.0, 300.0), (420.0, 320.0), (400.0, 500.0), (230.0, 470.0)],
        (900, 1200),
    )
    assert result.valid
    assert tuple(roi.name for roi in result.rois) == LED_ORDER
    assert all(roi.radius_px > 0 for roi in result.rois)


def test_out_of_bounds_projection_is_invalid_not_clamped() -> None:
    result = SixLedHomographyProjector(BeaconGeometry()).project(
        [(5.0, 5.0), (80.0, 5.0), (80.0, 80.0), (5.0, 80.0)],
        (100, 100),
    )
    assert result.valid is False
    assert "out_of_bounds" in result.reason


def test_tracker_rejects_wrong_id_hamming_and_margin() -> None:
    detector = mock.MagicMock()
    tracker = DynamicSixLedTracker(detector)
    frame = _frame()
    detector.detect.return_value = [_tag(tag_id=3)]
    assert tracker.process(frame).invalid_reason == "tag_id_mismatch"
    detector.detect.return_value = [_tag(hamming=1)]
    assert tracker.process(frame).invalid_reason == "tag_hamming_exceeded"
    detector.detect.return_value = [_tag(decision_margin=29.9)]
    assert tracker.process(frame).invalid_reason == "tag_margin_too_low"


def test_tracker_decodes_circular_rois_in_six_led_order() -> None:
    detector = mock.MagicMock()
    detector.detect.return_value = [_tag()]
    decoder = SixLedRoiDecoder(threshold=100, sample_shape="circle")
    tracker = DynamicSixLedTracker(detector, decoder=decoder)
    frame = _frame()
    rois = tracker.projector.project(TAG_CORNERS, frame.image.shape[:2]).rois
    for roi in rois:
        if roi.name in {"D0", "D3", "PAR"}:
            cv2.circle(frame.image, (roi.x_px, roi.y_px), roi.radius_px, 220, -1)
    result = tracker.process(frame)
    assert result.valid
    assert [result.reading.bits[name] for name in LED_ORDER] == [1, 0, 0, 1, 0, 1]


def test_tag_loss_keeps_debug_rois_but_never_valid_then_expires() -> None:
    detector = mock.MagicMock()
    detector.detect.return_value = [_tag()]
    tracker = DynamicSixLedTracker(detector, tag_lost_frames=2)
    first = tracker.process(_frame(1))
    assert first.rois
    detector.detect.return_value = []
    lost1 = tracker.process(_frame(2))
    lost2 = tracker.process(_frame(3))
    lost3 = tracker.process(_frame(4))
    assert not lost1.valid and lost1.rois
    assert not lost2.valid and lost2.rois
    assert not lost3.valid and not lost3.rois


def test_pose_request_is_forwarded_only_with_calibration() -> None:
    detector = mock.MagicMock()
    detector.detect.return_value = [_tag()]
    tracker = DynamicSixLedTracker(detector, camera_params=(1000.0, 1000.0, 450.0, 400.0))
    tracker.process(_frame())
    detector.detect.assert_called_once_with(
        mock.ANY,
        estimate_pose=True,
        camera_params=(1000.0, 1000.0, 450.0, 400.0),
        tag_size_m=0.15,
    )


def test_optical_flow_tracks_between_full_detections() -> None:
    detector = mock.MagicMock()
    detector.detect.return_value = [_tag()]
    tracker = DynamicSixLedTracker(
        detector,
        detection_interval=2,
        track_between_detections=True,
    )
    first = tracker.process(_frame(1))
    assert first.tag is not None

    points = np.asarray(TAG_CORNERS, dtype=np.float32).reshape(-1, 1, 2)
    with mock.patch(
        "cv2.calcOpticalFlowPyrLK",
        return_value=(points, np.ones((4, 1), dtype=np.uint8), np.zeros((4, 1))),
    ):
        second = tracker.process(_frame(2))

    assert detector.detect.call_count == 1
    assert second.tag is not None and second.tag.extra["tracked"] is True
    assert second.reading.extra["tag_tracked"] is True


def test_failed_optical_flow_falls_back_to_full_detection() -> None:
    detector = mock.MagicMock()
    detector.detect.return_value = [_tag()]
    tracker = DynamicSixLedTracker(
        detector,
        detection_interval=2,
        track_between_detections=True,
    )
    tracker.process(_frame(1))
    points = np.asarray(TAG_CORNERS, dtype=np.float32).reshape(-1, 1, 2)
    with mock.patch(
        "cv2.calcOpticalFlowPyrLK",
        return_value=(points, np.zeros((4, 1), dtype=np.uint8), np.zeros((4, 1))),
    ):
        result = tracker.process(_frame(2))
    assert detector.detect.call_count == 2
    assert result.tag is not None and not result.tag.extra.get("tracked", False)


def test_invalid_detection_interval_is_rejected() -> None:
    with pytest.raises(ValueError, match="detection_interval"):
        DynamicSixLedTracker(mock.MagicMock(), detection_interval=0)
