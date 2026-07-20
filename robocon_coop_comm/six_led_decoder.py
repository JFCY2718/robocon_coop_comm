"""Six-LED ROI brightness decoder.

Pure vision-layer module: samples brightness at six ROI positions and returns
a bit mask with confidence.  This module does **not** embed competition
semantics (no msg_id decoding, no FSM decisions).  Protocol-level decoding
is handled separately.

Modes
-----

**Fixed threshold** (default)::

    decoder = SixLedRoiDecoder(threshold=120)
    reading = decoder.decode(frame, roi_points)

**Adaptive threshold** (REF-relative, recommended for real scenes)::

    decoder = SixLedRoiDecoder(adaptive_threshold=True, ref_fraction=0.5)
    reading = decoder.decode(frame, roi_points)
    # Threshold = REF_brightness * ref_fraction (auto-computed per frame)

**Background-ring subtraction** (ambient-light robust)::

    decoder = SixLedRoiDecoder(adaptive_threshold=True, background_ring=True)
    # Uses centre_mean - ring_mean instead of raw centre brightness.
    # Eliminates ambient-light offset and makes the system invariant
    # to global illumination changes.

Output::

    reading = decoder.decode(frame, roi_points)
    # reading.bits         → {"REF": 1, "D0": 0, "D1": 1, ...}
    # reading.brightness   → {"REF": 210.3, "D0": 45.2, ...}
    # reading.confidence   → 0.87
    # reading.valid        → True

To convert to a protocol ``DecodedBeacon``, use ``six_led_to_coop_beacon()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .beacon_types import BeaconFrame, DecodedBeacon, msg_name_from_id
from .hikrobot_frame_provider import roi_mean


@dataclass(frozen=True)
class SixLedReading:
    """Raw 6-LED brightness reading from a single camera frame.

    Attributes:
        bits: Per-LED bit value (0 or 1) after thresholding.
        brightness: Raw mean brightness per LED (or centre-minus-background
            contrast when background_ring is enabled).
        confidence: Aggregate confidence [0, 1].
        valid: Basic validity — ``False`` if any ROI is outside image bounds
            or the brightness values are clearly unreadable.
        frame_id: Source frame id for traceability.
    """

    bits: dict[str, int]
    brightness: dict[str, float]
    confidence: float
    valid: bool
    frame_id: int = -1
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Decoder
# ---------------------------------------------------------------------------


class SixLedRoiDecoder:
    """Sample six LED ROI positions and threshold brightness → bit mask.

    Args:
        threshold: Brightness threshold (0–255). Used when ``adaptive_threshold``
            is disabled.  Ignored otherwise (falls back to ``ref_fraction * 20``).
        roi_size: Square sampling half-size in pixels (only for ``square`` shape).
        min_roi_brightness: If *any* sampled ROI mean falls below this floor,
            ``valid`` is set to ``False`` (camera may be blocked / too dark).
        max_roi_brightness: If *all* sampled ROI means exceed this ceiling,
            ``valid`` is set to ``False`` (possible over-exposure / glare).
        sample_shape: ``"square"`` (legacy) or ``"circle"``.
        adaptive_threshold: When ``True`` the per-frame threshold is computed
            from the REF LED brightness as ``ref_brightness * ref_fraction``.
            This is distance/exposure/ambient invariant.
        ref_fraction: Fraction of REF brightness used as the dynamic threshold
            when ``adaptive_threshold`` is enabled (default: 0.45).
        background_ring: When ``True``, sample an annular ring around each LED
            ROI and compute ``centre_mean - ring_mean`` as the reading.  This
            cancels out ambient light and handles non-uniform illumination.
        ring_ratio: Background ring outer radius relative to LED ROI radius
            (default: 2.5 → ring is 2.5× the LED sampling radius).
        contrast_floor: Minimum centre-minus-background contrast to consider a
            light meaningfully "on" (default: 15).  Below this the LED is
            classified as off regardless of threshold.
    """

    def __init__(
        self,
        threshold: int = 120,
        roi_size: int = 24,
        min_roi_brightness: float = 5.0,
        max_roi_brightness: float = 250.0,
        sample_shape: str = "square",
        *,
        adaptive_threshold: bool = False,
        ref_fraction: float = 0.45,
        background_ring: bool = False,
        ring_ratio: float = 2.5,
        contrast_floor: float = 15.0,
    ) -> None:
        self.threshold = int(threshold)
        self.roi_size = int(roi_size)
        self._min_brightness = float(min_roi_brightness)
        self._max_brightness = float(max_roi_brightness)
        if sample_shape not in {"square", "circle"}:
            raise ValueError("sample_shape must be 'square' or 'circle'")
        self.sample_shape = sample_shape
        self.adaptive_threshold = bool(adaptive_threshold)
        self.ref_fraction = float(ref_fraction)
        if not 0.1 <= self.ref_fraction <= 0.9:
            raise ValueError("ref_fraction must be in [0.1, 0.9]")
        self.background_ring = bool(background_ring)
        self.ring_ratio = float(ring_ratio)
        self.contrast_floor = float(contrast_floor)
        # Expose the effective threshold from the last decode (read-only).
        self._effective_threshold: float = float(threshold)

    @property
    def effective_threshold(self) -> float:
        """The threshold actually used in the most recent decode call."""
        return self._effective_threshold

    def decode(
        self,
        frame: BeaconFrame,
        roi_points,
    ) -> SixLedReading:
        """Decode one frame.

        Args:
            frame: ``BeaconFrame`` with ``image`` as a numpy array
                (grayscale H×W or BGR H×W×3).
            roi_points: Sequence of objects with attributes ``name``,
                ``x_px``, ``y_px``, and ``radius_px`` (e.g. ``RoiPoint``).

        Returns:
            ``SixLedReading``.
        """
        image = frame.image
        if image is None:
            return SixLedReading(
                bits={}, brightness={}, confidence=0.0, valid=False,
                frame_id=frame.frame_id,
            )

        bits: dict[str, int] = {}
        brightness: dict[str, float] = {}
        raw_centre: dict[str, float] = {}
        bg_values: dict[str, float] = {}
        all_within_bounds = True
        h, w = image.shape[:2]

        # --- sample every LED -------------------------------------------------
        for rp in roi_points:
            if not (0 <= rp.x_px < w and 0 <= rp.y_px < h):
                all_within_bounds = False
                bits[rp.name] = 0
                brightness[rp.name] = 0.0
                continue

            radius = max(1, int(rp.radius_px))
            if self.sample_shape == "circle":
                centre = _circle_roi_mean(image, rp.x_px, rp.y_px, radius)
            else:
                centre = roi_mean(image, rp.x_px, rp.y_px, radius * 2)
            raw_centre[rp.name] = float(centre)

            if self.background_ring:
                inner = int(round(radius * self.ring_ratio * 0.7))
                outer = int(round(radius * self.ring_ratio))
                bg = _ring_roi_mean(image, rp.x_px, rp.y_px, max(1, inner), max(inner + 1, outer))
                bg_values[rp.name] = float(bg)
                brightness[rp.name] = float(centre) - float(bg)
            else:
                brightness[rp.name] = float(centre)

        # --- determine effective threshold ------------------------------------
        if self.adaptive_threshold and "REF" in brightness:
            ref_b = brightness["REF"]
            if ref_b > self.contrast_floor:
                self._effective_threshold = ref_b * self.ref_fraction
            else:
                self._effective_threshold = float(self.threshold)
        else:
            self._effective_threshold = float(self.threshold)

        # --- bit decision -----------------------------------------------------
        thr = self._effective_threshold
        for rp in roi_points:
            if rp.name not in brightness:
                bits[rp.name] = 0
                continue
            b = brightness[rp.name]
            if b > thr:
                bits[rp.name] = 1
            elif self.background_ring and b < self.contrast_floor:
                bits[rp.name] = 0
            else:
                bits[rp.name] = 0

        # --- confidence & validity --------------------------------------------
        confidence = _compute_confidence(brightness, thr)
        valid = _check_valid(
            brightness,
            all_within_bounds=all_within_bounds,
            min_b=self._min_brightness,
            max_b=self._max_brightness,
        )

        extra: dict = {}
        if self.background_ring:
            extra["raw_centre"] = dict(raw_centre)
            extra["bg_values"] = dict(bg_values)
        extra["effective_threshold"] = thr

        return SixLedReading(
            bits=bits,
            brightness=brightness,
            confidence=confidence,
            valid=valid,
            frame_id=frame.frame_id,
            extra=extra,
        )


def _circle_roi_mean(image, x_px: int, y_px: int, radius_px: int) -> float:
    """Return mean grayscale intensity inside a circular pixel ROI."""
    import cv2
    import numpy as np

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    height, width = gray.shape[:2]
    radius = max(1, int(radius_px))
    x0, x1 = max(0, x_px - radius), min(width, x_px + radius + 1)
    y0, y1 = max(0, y_px - radius), min(height, y_px + radius + 1)
    if x0 >= x1 or y0 >= y1:
        return 0.0
    yy, xx = np.ogrid[y0:y1, x0:x1]
    mask = (xx - x_px) ** 2 + (yy - y_px) ** 2 <= radius**2
    values = gray[y0:y1, x0:x1][mask]
    return float(values.mean()) if values.size else 0.0


def _ring_roi_mean(image, x_px: int, y_px: int, inner_r: int, outer_r: int) -> float:
    """Mean grayscale intensity inside an annular ring (inner_r < r <= outer_r)."""
    import cv2
    import numpy as np

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    height, width = gray.shape[:2]
    x0, x1 = max(0, x_px - outer_r), min(width, x_px + outer_r + 1)
    y0, y1 = max(0, y_px - outer_r), min(height, y_px + outer_r + 1)
    if x0 >= x1 or y0 >= y1:
        return 0.0
    yy, xx = np.ogrid[y0:y1, x0:x1]
    d2 = (xx - x_px) ** 2 + (yy - y_px) ** 2
    mask = (d2 > inner_r**2) & (d2 <= outer_r**2)
    values = gray[y0:y1, x0:x1][mask]
    return float(values.mean()) if values.size else 0.0

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _compute_confidence(
    brightness: dict[str, float],
    threshold: float,
) -> float:
    """Aggregate confidence from brightness margins relative to threshold.

    Each LED contributes a margin = |brightness - threshold|.
    Larger margins → higher confidence.  Normalised to [0, 1].
    """
    if not brightness:
        return 0.0

    margins = [abs(b - threshold) for b in brightness.values()]
    avg_margin = sum(margins) / len(margins)
    # Scale: margin of 0 → 0.0, margin of 100+ → 1.0.
    return round(min(1.0, max(0.0, avg_margin / 100.0)), 4)


def _check_valid(
    brightness: dict[str, float],
    all_within_bounds: bool,
    min_b: float,
    max_b: float,
) -> bool:
    """Basic validity heuristics."""
    if not brightness:
        return False
    if not all_within_bounds:
        return False
    values = list(brightness.values())
    # If any value is below the floor, the image is likely too dark.
    if any(v < min_b for v in values):
        return False
    # If all values are above the ceiling, likely over-exposed.
    if all(v > max_b for v in values):
        return False
    return True


# ---------------------------------------------------------------------------
# Protocol bridge (optional — converts SixLedReading → DecodedBeacon)
# ---------------------------------------------------------------------------


def six_led_to_decoded_beacon(
    reading: SixLedReading,
    source: str = "6led_decoder",
) -> DecodedBeacon:
    """Convert a raw ``SixLedReading`` into a protocol-level ``DecodedBeacon``.

    This function maps the 6-LED bits onto the 8-LED protocol wire format
    and runs ``protocol.decode_led_bits`` for validation.

    LED name mapping (configurable by what the pattern supplies)::

        REF → REF
        D0  → D0
        D1  → D1
        D2  → D2
        SEQ → SEQ
        PAR → PAR
        (D3, D4 default to 0)

    If the pattern uses different names, missing keys default to 0.
    """
    from .protocol import decode_led_bits
    from .protocol import LED_NAMES

    bits = reading.bits

    # Build the 8-bit dictionary expected by the protocol.
    proto_bits: dict[str, int] = {}
    for name in LED_NAMES:
        proto_bits[name] = bits.get(name, 0)

    try:
        proto = decode_led_bits(proto_bits)
    except ValueError:
        return DecodedBeacon(
            msg_id=0,
            msg_name=msg_name_from_id(0),
            seq=0,
            valid=False,
            confidence=reading.confidence,
            source=source,
            reason="protocol_decode_error",
        )

    return DecodedBeacon(
        msg_id=proto.msg_id,
        msg_name=proto.msg_name,
        seq=proto.seq,
        valid=proto.valid and reading.valid,
        confidence=reading.confidence,
        source=source,
        reason="" if proto.valid else "parity_or_ref_failed",
        raw_bits=dict(proto.bits),
    )


def six_led_to_coop_beacon(
    reading: SixLedReading,
    source: str = "6led_decoder_v2",
) -> DecodedBeacon:
    """Decode D0-D3/REF/PAR as the selected 16-state level protocol."""
    from .coop_protocol_v2 import bits_to_mask, decode_mask

    try:
        decoded = decode_mask(bits_to_mask(reading.bits))
    except ValueError as exc:
        return DecodedBeacon(
            msg_id=0,
            msg_name="IDLE",
            seq=0,
            valid=False,
            confidence=reading.confidence,
            source=source,
            reason=f"protocol_input_error: {exc}",
        )

    message_id = int(decoded.message) if decoded.message is not None else 0
    message_name = decoded.message.name if decoded.message is not None else "INVALID"
    valid = decoded.valid and reading.valid
    if not decoded.valid:
        reason = decoded.reason
    elif not reading.valid:
        reason = "vision_invalid"
    else:
        reason = ""
    return DecodedBeacon(
        msg_id=message_id,
        msg_name=message_name,
        seq=0,
        valid=valid,
        confidence=reading.confidence,
        source=source,
        reason=reason,
        raw_bits=decoded.bits,
    )
