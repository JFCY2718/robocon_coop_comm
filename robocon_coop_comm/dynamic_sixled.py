"""AprilTag-guided dynamic six-LED ROI projection and decoding."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .apriltag_detector import TagDetection
from .apriltag_roi_mapper import RoiPoint
from .beacon_geometry import BeaconGeometry, LED_ORDER
from .beacon_types import BeaconFrame
from .six_led_decoder import SixLedReading, SixLedRoiDecoder


@dataclass(frozen=True)
class ProjectionResult:
    rois: tuple[RoiPoint, ...]
    homography: object | None
    valid: bool
    reason: str = ""


@dataclass(frozen=True)
class DynamicSixLedResult:
    reading: SixLedReading
    tag: TagDetection | None
    rois: tuple[RoiPoint, ...]
    valid: bool
    invalid_reason: str = ""
    lost_frames: int = 0


class SixLedHomographyProjector:
    """Project the fixed planar beacon layout from tag coordinates to pixels."""

    def __init__(self, geometry: BeaconGeometry) -> None:
        self.geometry = geometry

    def project(
        self,
        tag_corners: list[tuple[float, float]],
        image_shape: tuple[int, int],
    ) -> ProjectionResult:
        if len(tag_corners) != 4:
            return ProjectionResult((), None, False, "tag_corner_count")

        import cv2
        import numpy as np

        half = self.geometry.tag_size_mm / 2.0
        # pupil-apriltags corners: top-left, top-right, bottom-right, bottom-left.
        source = np.asarray(
            [(-half, half), (half, half), (half, -half), (-half, -half)],
            dtype=np.float32,
        )
        target = np.asarray(tag_corners, dtype=np.float32)
        homography = cv2.getPerspectiveTransform(source, target)
        if not np.isfinite(homography).all():
            return ProjectionResult((), None, False, "homography_non_finite")

        height, width = int(image_shape[0]), int(image_shape[1])
        radius_mm = self.geometry.roi_radius_mm
        rois: list[RoiPoint] = []
        for name, x_mm, y_mm in self.geometry.led_centers_tag_mm:
            centre = _project(homography, x_mm, y_mm)
            edge_x = _project(homography, x_mm + radius_mm, y_mm)
            edge_y = _project(homography, x_mm, y_mm + radius_mm)
            if centre is None or edge_x is None or edge_y is None:
                return ProjectionResult((), homography, False, f"{name}_projection_invalid")
            radius_px = int(round((math.dist(centre, edge_x) + math.dist(centre, edge_y)) / 2.0))
            radius_px = max(1, radius_px)
            x_px, y_px = int(round(centre[0])), int(round(centre[1]))
            if (
                x_px - radius_px < 0
                or y_px - radius_px < 0
                or x_px + radius_px >= width
                or y_px + radius_px >= height
            ):
                return ProjectionResult((), homography, False, f"{name}_roi_out_of_bounds")
            rois.append(RoiPoint(name, x_px, y_px, radius_px))

        if tuple(roi.name for roi in rois) != LED_ORDER:
            return ProjectionResult((), homography, False, "led_order_mismatch")
        return ProjectionResult(tuple(rois), homography, True)


class DynamicSixLedTracker:
    """Detect, validate, project and decode one camera frame at a time.

    Last ROIs are retained only for debug drawing.  A frame without a current,
    valid tag observation is never returned as actionable/valid.
    """

    def __init__(
        self,
        detector,
        geometry: BeaconGeometry | None = None,
        decoder: SixLedRoiDecoder | None = None,
        *,
        target_tag_id: int = 0,
        min_decision_margin: float = 30.0,
        max_hamming: int = 0,
        tag_lost_frames: int = 5,
        camera_params: tuple[float, float, float, float] | None = None,
        detection_interval: int = 1,
        track_between_detections: bool = False,
        max_optical_flow_error: float = 12.0,
        max_optical_flow_displacement_px: float = 80.0,
    ) -> None:
        self.detector = detector
        self.geometry = geometry or BeaconGeometry()
        self.projector = SixLedHomographyProjector(self.geometry)
        self.decoder = decoder or SixLedRoiDecoder(sample_shape="circle")
        self.target_tag_id = int(target_tag_id)
        self.min_decision_margin = float(min_decision_margin)
        self.max_hamming = int(max_hamming)
        self.tag_lost_frames = max(0, int(tag_lost_frames))
        self.camera_params = camera_params
        if detection_interval < 1:
            raise ValueError("detection_interval must be >= 1")
        self.detection_interval = int(detection_interval)
        self.track_between_detections = bool(track_between_detections)
        self.max_optical_flow_error = float(max_optical_flow_error)
        self.max_optical_flow_displacement_px = float(max_optical_flow_displacement_px)
        self._lost_frames = 0
        self._last_rois: tuple[RoiPoint, ...] = ()
        self._last_tag: TagDetection | None = None
        self._previous_gray = None
        self._frames_since_detection = 0

    def process(self, frame: BeaconFrame) -> DynamicSixLedResult:
        if frame.image is None:
            return self._invalid(frame, "null_image")
        tag = self._track_tag(frame.image)
        tracked = tag is not None
        if tag is None:
            try:
                if self.camera_params is None:
                    detections = self.detector.detect(frame.image)
                else:
                    detections = self.detector.detect(
                        frame.image,
                        estimate_pose=True,
                        camera_params=self.camera_params,
                        tag_size_m=self.geometry.tag_size_mm / 1000.0,
                    )
            except Exception as exc:
                return self._invalid(frame, f"apriltag_detect_error: {exc}")

            matching = [item for item in detections if item.tag_id == self.target_tag_id]
            if not matching:
                reason = "no_tag_detected" if not detections else "tag_id_mismatch"
                return self._invalid(frame, reason)
            tag = max(matching, key=lambda item: item.decision_margin)
            if tag.hamming > self.max_hamming:
                return self._invalid(frame, "tag_hamming_exceeded", tag)
            if tag.decision_margin < self.min_decision_margin:
                return self._invalid(frame, "tag_margin_too_low", tag)

        projection = self.projector.project(tag.corners, frame.image.shape[:2])
        if not projection.valid:
            return self._invalid(frame, projection.reason, tag)

        self._lost_frames = 0
        self._last_rois = projection.rois
        self._remember_tag(frame.image, tag, tracked=tracked)
        reading = self.decoder.decode(frame, projection.rois)
        reason = "" if reading.valid else "sixled_reading_invalid"
        reading = _with_metadata(reading, tag, projection.rois, reason)
        return DynamicSixLedResult(
            reading, tag, projection.rois, reading.valid, reason, self._lost_frames
        )

    def _track_tag(self, image) -> TagDetection | None:
        if (
            not self.track_between_detections
            or self.detection_interval <= 1
            or self._last_tag is None
            or self._previous_gray is None
            or self._frames_since_detection >= self.detection_interval - 1
        ):
            return None

        import cv2
        import numpy as np

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        previous = np.asarray(self._last_tag.corners, dtype=np.float32).reshape(-1, 1, 2)
        current, status, error = cv2.calcOpticalFlowPyrLK(
            self._previous_gray,
            gray,
            previous,
            None,
            winSize=(21, 21),
            maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03),
        )
        if current is None or status is None or error is None:
            return None
        if not bool(np.all(status.reshape(-1) == 1)):
            return None
        points = current.reshape(-1, 2)
        errors = error.reshape(-1)
        if not np.isfinite(points).all() or not np.isfinite(errors).all():
            return None
        if float(np.max(errors)) > self.max_optical_flow_error:
            return None
        displacement = np.linalg.norm(points - previous.reshape(-1, 2), axis=1)
        if float(np.max(displacement)) > self.max_optical_flow_displacement_px:
            return None
        if not _valid_quadrilateral(points, gray.shape[:2]):
            return None

        center = tuple(float(value) for value in points.mean(axis=0))
        extra = dict(self._last_tag.extra)
        extra.update({"tracked": True, "optical_flow_max_error": float(np.max(errors))})
        return TagDetection(
            tag_id=self._last_tag.tag_id,
            family=self._last_tag.family,
            corners=[tuple(float(value) for value in point) for point in points],
            center=center,
            decision_margin=self._last_tag.decision_margin,
            hamming=self._last_tag.hamming,
            extra=extra,
        )

    def _remember_tag(self, image, tag: TagDetection, *, tracked: bool) -> None:
        import cv2

        self._previous_gray = (
            cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        ).copy()
        self._last_tag = tag
        if tracked:
            self._frames_since_detection += 1
        else:
            self._frames_since_detection = 0

    def _invalid(
        self,
        frame: BeaconFrame,
        reason: str,
        tag: TagDetection | None = None,
    ) -> DynamicSixLedResult:
        self._last_tag = None
        self._previous_gray = None
        self._frames_since_detection = 0
        self._lost_frames += 1
        debug_rois = self._last_rois if self._lost_frames <= self.tag_lost_frames else ()
        reading = SixLedReading(
            bits={},
            brightness={},
            confidence=0.0,
            valid=False,
            frame_id=frame.frame_id,
            extra={
                "invalid_reason": reason,
                "stale_rois_for_debug": bool(debug_rois),
                "lost_frames": self._lost_frames,
            },
        )
        return DynamicSixLedResult(
            reading, tag, debug_rois, False, reason, self._lost_frames
        )


def _project(homography, x_mm: float, y_mm: float) -> tuple[float, float] | None:
    import numpy as np

    projected = np.asarray(homography, dtype=float) @ np.asarray([x_mm, y_mm, 1.0])
    if not np.isfinite(projected).all() or abs(float(projected[2])) < 1e-9:
        return None
    return float(projected[0] / projected[2]), float(projected[1] / projected[2])


def _valid_quadrilateral(points, image_shape: tuple[int, int]) -> bool:
    import cv2
    import numpy as np

    if points.shape != (4, 2):
        return False
    height, width = image_shape
    if (
        np.any(points[:, 0] < 0)
        or np.any(points[:, 0] >= width)
        or np.any(points[:, 1] < 0)
        or np.any(points[:, 1] >= height)
    ):
        return False
    contour = points.astype(np.float32).reshape(-1, 1, 2)
    return bool(cv2.isContourConvex(contour) and abs(cv2.contourArea(contour)) >= 100.0)


def _with_metadata(
    reading: SixLedReading,
    tag: TagDetection,
    rois: tuple[RoiPoint, ...],
    invalid_reason: str,
) -> SixLedReading:
    extra = dict(reading.extra)
    extra.update(
        {
            "invalid_reason": invalid_reason,
            "tag_id": tag.tag_id,
            "tag_center_px": tag.center,
            "tag_decision_margin": tag.decision_margin,
            "tag_hamming": tag.hamming,
            "tag_tracked": bool(tag.extra.get("tracked", False)),
            "optical_flow_max_error": tag.extra.get("optical_flow_max_error"),
            "dynamic_rois": tuple((r.name, r.x_px, r.y_px, r.radius_px) for r in rois),
        }
    )
    return SixLedReading(
        bits=reading.bits,
        brightness=reading.brightness,
        confidence=reading.confidence,
        valid=reading.valid,
        frame_id=reading.frame_id,
        extra=extra,
    )
