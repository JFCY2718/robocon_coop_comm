"""Configurable LED pattern mapper.

Defines physical LED layouts and maps them to image-pixel ROI coordinates
via either manual (origin + px/mm scale) or AprilTag-guided (homography)
projection.

A "pattern" is a named set of LED physical positions in mm, relative to
a pattern-local origin.  The mapper translates these into pixel ROI points
that can be fed to ``roi_mean`` for brightness sampling.

Usage::

    from robocon_coop_comm.pattern_mapper import (
        PatternMapper,
        LedPattern,
        PATTERN_3LED_BELOW,
        PATTERN_6LED_HORIZONTAL,
    )

    mapper = PatternMapper(PATTERN_6LED_HORIZONTAL, px_per_mm=2.5)

    # --- manual ROI ---
    rois = mapper.manual_rois(origin_px=(200, 400))
    for r in rois:
        b = roi_mean(frame, r.x_px, r.y_px, r.radius_px * 2)

    # --- AprilTag-guided ---
    rois, H = mapper.apriltag_rois(
        tag_corners=detection.corners,
        tag_size_mm=100.0,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .apriltag_roi_mapper import AprilTagRoiMapper, RoiPoint

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LedDef:
    """One LED in a pattern layout.

    Args:
        name: LED identifier (e.g. ``"REF"``, ``"D0"``, ``"SEQ"``).
        x_mm: Horizontal offset from pattern origin (mm).
        y_mm: Vertical offset from pattern origin (mm).
    """

    name: str
    x_mm: float
    y_mm: float


@dataclass(frozen=True)
class LedPattern:
    """A named physical LED layout.

    Args:
        name: Short identifier (e.g. ``"3led_below"``).
        description: Human-readable description of the layout.
        leds: Ordered list of ``LedDef`` entries.
    """

    name: str
    description: str
    leds: list[LedDef] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Predefined patterns
# ---------------------------------------------------------------------------

PATTERN_3LED_BELOW = LedPattern(
    name="3led_below",
    description="3 LEDs (D0/D1/D2) in a horizontal row below the tag origin",
    leds=[
        LedDef("D0", 0.0, 110.0),
        LedDef("D1", 50.0, 110.0),
        LedDef("D2", 100.0, 110.0),
    ],
)
"""Default 3-LED layout used on early hardware revisions."""

PATTERN_6LED_HORIZONTAL = LedPattern(
    name="6led_horizontal",
    description="6 LEDs (REF/D0/D1/D2/SEQ/PAR) in a single horizontal row",
    leds=[
        LedDef("REF", 0.0, 110.0),
        LedDef("D0", 20.0, 110.0),
        LedDef("D1", 40.0, 110.0),
        LedDef("D2", 60.0, 110.0),
        LedDef("SEQ", 80.0, 110.0),
        LedDef("PAR", 100.0, 110.0),
    ],
)
"""6-LED horizontal layout with full protocol bits."""

PATTERN_6LED_TWO_ROW = LedPattern(
    name="6led_two_row",
    description="6 LEDs in two rows: REF/D0/D1 on top, D2/SEQ/PAR on bottom",
    leds=[
        LedDef("REF", 0.0, 0.0),
        LedDef("D0", 20.0, 0.0),
        LedDef("D1", 40.0, 0.0),
        LedDef("D2", 0.0, 30.0),
        LedDef("SEQ", 20.0, 30.0),
        LedDef("PAR", 40.0, 30.0),
    ],
)
"""6-LED two-row layout.  Top: REF/D0/D1, Bottom: D2/SEQ/PAR."""

# ---------------------------------------------------------------------------
# PatternMapper
# ---------------------------------------------------------------------------


class PatternMapper:
    """Maps a ``LedPattern`` to image-pixel ROI coordinates.

    Two mapping modes are supported:

    * **manual** — supply an origin pixel + scale (px/mm).  Useful for
      fixed-camera setups where the board is always in the same image region.
    * **apriltag** — supply detected AprilTag corners + physical tag size.
      The mapper delegates to ``AprilTagRoiMapper`` for perspective-correct
      projection.

    Args:
        pattern: The ``LedPattern`` to map.
        px_per_mm: Default scale factor for manual mapping.  Can be overridden
            per ``manual_rois()`` call.
        default_radius_mm: Default LED sampling radius in mm.
    """

    def __init__(
        self,
        pattern: LedPattern,
        px_per_mm: float = 2.0,
        default_radius_mm: float = 5.0,
    ) -> None:
        self._pattern = pattern
        self._px_per_mm = float(px_per_mm)
        self._default_radius_mm = float(default_radius_mm)

    # ------------------------------------------------------------------
    # properties
    # ------------------------------------------------------------------

    @property
    def pattern(self) -> LedPattern:
        return self._pattern

    @property
    def led_names(self) -> list[str]:
        return [led.name for led in self._pattern.leds]

    @property
    def led_count(self) -> int:
        return len(self._pattern.leds)

    @property
    def px_per_mm(self) -> float:
        return self._px_per_mm

    # ------------------------------------------------------------------
    # manual mapping
    # ------------------------------------------------------------------

    def manual_rois(
        self,
        origin_px: tuple[int, int],
        px_per_mm: float | None = None,
        radius_mm: float | None = None,
    ) -> list[RoiPoint]:
        """Compute ROI pixel positions via manual origin + scale.

        Args:
            origin_px: ``(x, y)`` pixel coordinate of the pattern origin
                (top-left of the LED board area).
            px_per_mm: Override the default scale factor.
            radius_mm: Override the default sampling radius.

        Returns:
            One ``RoiPoint`` per LED in the pattern, in pattern order.
        """
        scale = float(px_per_mm) if px_per_mm is not None else self._px_per_mm
        rad_mm = float(radius_mm) if radius_mm is not None else self._default_radius_mm
        radius_px = max(1, int(round(rad_mm * scale)))
        ox, oy = origin_px

        rois: list[RoiPoint] = []
        for led in self._pattern.leds:
            x_px = int(round(ox + led.x_mm * scale))
            y_px = int(round(oy + led.y_mm * scale))
            rois.append(RoiPoint(name=led.name, x_px=x_px, y_px=y_px, radius_px=radius_px))
        return rois

    # ------------------------------------------------------------------
    # AprilTag-guided mapping
    # ------------------------------------------------------------------

    def apriltag_rois(
        self,
        tag_corners: list[tuple[float, float]],
        tag_size_mm: float,
        image_shape: tuple[int, int],
        tag_to_pattern_offset_mm: tuple[float, float] = (0.0, 0.0),
        led_radius_mm: float | None = None,
    ) -> tuple[list[RoiPoint], object | None]:
        """Compute ROI pixel positions via AprilTag homography.

        LED positions in the pattern are interpreted relative to the
        AprilTag black-border top-left corner.  An additional offset
        ``tag_to_pattern_offset_mm`` shifts the entire pattern relative
        to that corner (e.g. (0, 20) places LEDs 20mm below the tag).

        Args:
            tag_corners: Four detected corners in image pixel coords
                (clockwise from top-left).
            tag_size_mm: Black border outer dimension.
            image_shape: ``(height, width)`` of the camera frame.
            tag_to_pattern_offset_mm: ``(dx, dy)`` offset from tag
                black-border top-left to pattern origin, in mm.
            led_radius_mm: Override the default LED sampling radius.

        Returns:
            ``(roi_points, homography)`` — homography is the 3×3
            OpenCV matrix, or ``None`` if estimation failed.
        """
        rad_mm = float(led_radius_mm) if led_radius_mm is not None else self._default_radius_mm

        # Shift LED positions by the tag→pattern offset.
        ox, oy = tag_to_pattern_offset_mm
        shifted_positions: list[tuple[str, float, float]] = [
            (led.name, led.x_mm + ox, led.y_mm + oy)
            for led in self._pattern.leds
        ]

        mapper = AprilTagRoiMapper(
            tag_size_mm=tag_size_mm,
            led_positions_mm=shifted_positions,
            led_radius_mm=rad_mm,
        )
        return mapper.map_rois(tag_corners, image_shape)

    # ------------------------------------------------------------------
    # serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Export the pattern as a JSON-serialisable dict."""
        return {
            "name": self._pattern.name,
            "description": self._pattern.description,
            "px_per_mm": self._px_per_mm,
            "default_radius_mm": self._default_radius_mm,
            "leds": [
                {"name": led.name, "x_mm": led.x_mm, "y_mm": led.y_mm}
                for led in self._pattern.leds
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> PatternMapper:
        """Create a ``PatternMapper`` from a dictionary (inverse of ``to_dict``)."""
        pattern = LedPattern(
            name=data["name"],
            description=data.get("description", ""),
            leds=[
                LedDef(name=d["name"], x_mm=d["x_mm"], y_mm=d["y_mm"])
                for d in data["leds"]
            ],
        )
        return cls(
            pattern=pattern,
            px_per_mm=data.get("px_per_mm", 2.0),
            default_radius_mm=data.get("default_radius_mm", 5.0),
        )
