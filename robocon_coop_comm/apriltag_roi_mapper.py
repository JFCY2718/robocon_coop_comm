"""AprilTag-guided LED ROI mapper.

Given an AprilTag detection (4 corners in image pixel coordinates) and the
physical dimensions of the tag + LED board, computes the pixel-coordinate ROI
centres for each LED via homography / perspective correction.

Coordinate system
-----------------

The tag coordinate system is defined as::

    (0,0) ─────────────────────── (full_tag_mm, 0)
      │  ┌─────────────────────┐  │
      │  │  white border       │  │
      │  │  ┌───────────────┐  │  │
      │  │  │  black border  │  │  │  ← tag_size_mm (outer edge of black)
      │  │  │  (data bits)   │  │  │
      │  │  └───────────────┘  │  │
      │  └─────────────────────┘  │
    (0, full_tag_mm) ────────── (full_tag_mm, full_tag_mm)

- ``tag_size_mm``: outer edge length of the black border (8/10 of full tag).
- White border: 1/10 of full tag on each side → ``tag_size_mm / 8`` mm.
- Full tag outer (white border corners) = ``tag_size_mm * 10 / 8``.

LED positions are specified relative to the **black border top-left corner**
(i.e. the inner edge of the white border).

Usage::

    mapper = AprilTagRoiMapper(
        tag_size_mm=100.0,
        led_positions_mm=[
            ("D0", 10.0, 110.0),
            ("D1", 50.0, 110.0),
            ("D2", 90.0, 110.0),
        ],
        led_radius_mm=6.0,
    )

    detections = apriltag_detector.detect(frame)
    for d in detections:
        rois, homography = mapper.map_rois(d.corners, frame.shape[:2])
        for roi in rois:
            brightness = roi_mean(frame, roi.x_px, roi.y_px, roi.radius_px * 2)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoiPoint:
    """A single LED ROI centre mapped to image pixel coordinates."""

    name: str
    x_px: int
    y_px: int
    radius_px: int


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class AprilTagRoiMapper:
    """Map LED positions from a physical AprilTag coordinate frame to image pixels.

    Uses OpenCV ``findHomography`` for perspective correction.  The homography
    is computed from the four white-border corners of the tag (known physical
    mm coordinates) to the four detected image-plane corners.

    Args:
        tag_size_mm: Outer edge length of the **black border** in mm.
        led_positions_mm: Sequence of ``(name, x_mm, y_mm)`` tuples where
            *x_mm* and *y_mm* are relative to the black-border top-left corner.
        led_radius_mm: Sampling radius for each LED ROI in mm.
    """

    # Tag geometry constants (tag36h11: 10 total, 8 black, 1 white each side).
    _TAG_TOTAL_UNITS = 10.0
    _TAG_BLACK_UNITS = 8.0
    _TAG_WHITE_UNITS = 1.0

    def __init__(
        self,
        tag_size_mm: float,
        led_positions_mm: list[tuple[str, float, float]] | None = None,
        led_radius_mm: float = 5.0,
    ) -> None:
        if tag_size_mm <= 0:
            raise ValueError(f"tag_size_mm must be > 0, got {tag_size_mm}")

        self.tag_size_mm = float(tag_size_mm)
        self.led_radius_mm = float(led_radius_mm)
        self._led_positions: list[tuple[str, float, float]] = (
            list(led_positions_mm) if led_positions_mm else []
        )

        # Derived physical dimensions.
        self._white_border_mm = tag_size_mm * (
            self._TAG_WHITE_UNITS / self._TAG_BLACK_UNITS
        )
        self._full_tag_mm = tag_size_mm * (
            self._TAG_TOTAL_UNITS / self._TAG_BLACK_UNITS
        )

    # ------------------------------------------------------------------
    # properties
    # ------------------------------------------------------------------

    @property
    def led_positions_mm(self) -> list[tuple[str, float, float]]:
        """Read-only view of the configured LED positions."""
        return list(self._led_positions)

    @property
    def full_tag_mm(self) -> float:
        """Total tag outer dimension (including white border) in mm."""
        return self._full_tag_mm

    @property
    def white_border_mm(self) -> float:
        """Width of the white border in mm."""
        return self._white_border_mm

    # ------------------------------------------------------------------
    # core mapping
    # ------------------------------------------------------------------

    def map_rois(
        self,
        tag_corners: list[tuple[float, float]],
        image_shape: tuple[int, int],
    ) -> tuple[list[RoiPoint], object | None]:
        """Compute LED ROI points in image pixel coordinates.

        Args:
            tag_corners: Four detected tag corners in image pixel coordinates,
                ordered clockwise from top-left::

                    [tl, tr, br, bl]

            image_shape: ``(height, width)`` of the source image.

        Returns:
            ``(roi_points, homography)`` where *roi_points* is a list of
            ``RoiPoint`` (one per configured LED) and *homography* is the
            OpenCV 3×3 homography matrix (or ``None`` if the homography
            could not be estimated).
        """
        if len(tag_corners) != 4:
            raise ValueError(
                f"Expected 4 tag corners, got {len(tag_corners)}"
            )

        homography = _estimate_homography(
            tag_corners=tag_corners, full_tag_mm=self._full_tag_mm
        )
        if homography is None:
            return [], None

        h, w = int(image_shape[0]), int(image_shape[1])

        # Scale factor: how many pixels per mm near the tag centre.
        px_per_mm = _pixels_per_mm(homography, self._full_tag_mm)

        radius_px = max(1, int(round(self.led_radius_mm * px_per_mm)))

        roi_points: list[RoiPoint] = []
        for name, led_x_mm, led_y_mm in self._led_positions:
            # Convert black-border-relative → full-tag-relative.
            tag_x_mm = self._white_border_mm + led_x_mm
            tag_y_mm = self._white_border_mm + led_y_mm

            px, py = _project_point(homography, tag_x_mm, tag_y_mm)

            # Clamp to image bounds.
            px = max(0, min(w - 1, px))
            py = max(0, min(h - 1, py))

            roi_points.append(
                RoiPoint(name=name, x_px=px, y_px=py, radius_px=radius_px)
            )

        return roi_points, homography

    # ------------------------------------------------------------------
    # convenience factories
    # ------------------------------------------------------------------

    @classmethod
    def for_3led_below(
        cls,
        tag_size_mm: float,
        d0_offset_mm: float = 0.0,
        spacing_mm: float | None = None,
        gap_below_tag_mm: float = 10.0,
        led_radius_mm: float = 5.0,
    ) -> AprilTagRoiMapper:
        """Create a mapper for the standard 3-LED layout (LEDs below the tag).

        Three LEDs placed in a horizontal row below the black border::

            ┌───────────────┐
            │   AprilTag    │
            └───────────────┘
              D0    D1    D2

        Args:
            tag_size_mm: Black border outer dimension.
            d0_offset_mm: Horizontal offset of D0 from the black-border left edge.
            spacing_mm: Centre-to-centre spacing between LEDs.  Defaults to
                ``tag_size_mm / 3`` (evenly distributed).
            gap_below_tag_mm: Vertical gap from black-border bottom edge to
                the LED row centre-line.
            led_radius_mm: Sampling radius for each LED.
        """
        if spacing_mm is None:
            spacing_mm = tag_size_mm / 3.0

        y_mm = tag_size_mm + float(gap_below_tag_mm)
        positions: list[tuple[str, float, float]] = [
            ("D0", d0_offset_mm, y_mm),
            ("D1", d0_offset_mm + spacing_mm, y_mm),
            ("D2", d0_offset_mm + 2 * spacing_mm, y_mm),
        ]
        return cls(
            tag_size_mm=tag_size_mm,
            led_positions_mm=positions,
            led_radius_mm=led_radius_mm,
        )


# ---------------------------------------------------------------------------
# Internal helpers (module-level for testability)
# ---------------------------------------------------------------------------


def _estimate_homography(
    tag_corners: list[tuple[float, float]],
    full_tag_mm: float,
) -> object | None:
    """Compute the homography from tag-mm space to image-pixel space.

    Returns:
        3×3 numpy array, or ``None`` if the homography could not be estimated.
    """
    import cv2
    import numpy as np

    # Source: tag outer corners in mm (clockwise from top-left).
    src_pts = np.array(
        [
            [0.0, 0.0],
            [full_tag_mm, 0.0],
            [full_tag_mm, full_tag_mm],
            [0.0, full_tag_mm],
        ],
        dtype=np.float32,
    )

    # Destination: detected corners in image pixels (matching clockwise order).
    dst_pts = np.array(
        [[float(x), float(y)] for x, y in tag_corners],
        dtype=np.float32,
    )

    H, mask = cv2.findHomography(src_pts, dst_pts, method=0)
    if H is None or mask is None:
        return None
    return H


def _project_point(
    homography: object,
    x_mm: float,
    y_mm: float,
) -> tuple[int, int]:
    """Project a point from tag-mm space to image-pixel space.

    Args:
        homography: 3×3 OpenCV homography matrix.
        x_mm, y_mm: Coordinates in the tag-mm frame (relative to white-border
            top-left origin).

    Returns:
        ``(x_px, y_px)`` rounded to the nearest integer pixel.
    """
    import numpy as np

    H = np.asarray(homography, dtype=np.float64)
    pt = np.array([x_mm, y_mm, 1.0], dtype=np.float64)
    proj = H @ pt
    px = int(round(float(proj[0] / proj[2])))
    py = int(round(float(proj[1] / proj[2])))
    return px, py


def _pixels_per_mm(homography: object, full_tag_mm: float) -> float:
    """Estimate the pixels-per-mm scale factor near the tag centre.

    Projects a 1-mm horizontal vector at the tag centre and returns its
    length in pixels.
    """
    import numpy as np

    half = full_tag_mm / 2.0
    cx, cy = _project_point(homography, half, half)
    cx1, cy1 = _project_point(homography, half + 1.0, half)
    return float(np.linalg.norm([cx1 - cx, cy1 - cy]))
