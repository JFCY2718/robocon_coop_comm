"""Six-LED ROI brightness decoder.

Pure vision-layer module: samples brightness at six ROI positions and returns
a bit mask with confidence.  This module does **not** embed competition
semantics (no msg_id decoding, no FSM decisions).  Protocol-level decoding
is handled separately.

Outputs a ``SixLedReading`` per frame::

    reading = decoder.decode(frame, roi_points)
    # reading.bits         → {"REF": 1, "D0": 0, "D1": 1, ...}
    # reading.brightness   → {"REF": 210.3, "D0": 45.2, ...}
    # reading.confidence   → 0.87
    # reading.valid        → True

To convert to a protocol ``DecodedBeacon``, use ``six_led_to_decoded_beacon()``.
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
        brightness: Raw mean brightness per LED.
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
        threshold: Brightness threshold (0–255).  ROI mean > threshold → bit=1.
        roi_size: Square sampling half-size in pixels.  Passed to ``roi_mean``
            as the ``size`` parameter (full side length).
        min_roi_brightness: If *any* sampled ROI mean falls below this floor,
            ``valid`` is set to ``False`` (camera may be blocked / too dark).
        max_roi_brightness: If *all* sampled ROI means exceed this ceiling,
            ``valid`` is set to ``False`` (possible over-exposure / glare).
    """

    def __init__(
        self,
        threshold: int = 120,
        roi_size: int = 24,
        min_roi_brightness: float = 5.0,
        max_roi_brightness: float = 250.0,
    ) -> None:
        self.threshold = int(threshold)
        self.roi_size = int(roi_size)
        self._min_brightness = float(min_roi_brightness)
        self._max_brightness = float(max_roi_brightness)

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
        all_within_bounds = True
        h, w = image.shape[:2]

        for rp in roi_points:
            # Basic bounds check.
            if not (0 <= rp.x_px < w and 0 <= rp.y_px < h):
                all_within_bounds = False
                bits[rp.name] = 0
                brightness[rp.name] = 0.0
                continue

            b = roi_mean(image, rp.x_px, rp.y_px, rp.radius_px * 2)
            brightness[rp.name] = float(b)
            bits[rp.name] = 1 if b > self.threshold else 0

        confidence = _compute_confidence(brightness, self.threshold)
        valid = _check_valid(
            brightness,
            all_within_bounds=all_within_bounds,
            min_b=self._min_brightness,
            max_b=self._max_brightness,
        )

        return SixLedReading(
            bits=bits,
            brightness=brightness,
            confidence=confidence,
            valid=valid,
            frame_id=frame.frame_id,
        )


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
