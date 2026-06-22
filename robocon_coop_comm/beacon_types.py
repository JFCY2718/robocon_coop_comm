"""Vision-level beacon data types.

These types wrap protocol-level decoded results with vision metadata
(confidence, source, stability info).  They do NOT replace protocol.DecodedBeacon
which is used by R2 FSM.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .protocol import MsgID


@dataclass(frozen=True)
class DecodedBeacon:
    """Vision-level decoded beacon with confidence and source info."""

    msg_id: int
    msg_name: str
    seq: int
    valid: bool
    confidence: float
    source: str = "unknown"
    reason: str = ""
    raw_bits: dict[str, int] | None = None


@dataclass(frozen=True)
class BeaconFrame:
    """A single frame from a beacon image source.

    image is typed as object to avoid requiring numpy type annotations.
    """

    image: object
    source: str
    frame_id: int
    timestamp: float | None = None


def msg_name_from_id(msg_id: int) -> str:
    """Return the human-readable name for a msg_id.

    Uses protocol.MsgID enum.  Unknown ids return UNKNOWN_<id>.
    """
    try:
        return MsgID(msg_id).name
    except ValueError:
        return f"UNKNOWN_{msg_id}"


# ---------------------------------------------------------------------------
# BeaconEvent — bridges vision pipeline output to FSM input
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BeaconEvent:
    """Vision-to-FSM bridge event.

    This type carries vision metadata (confidence, timestamp, source) that
    ``protocol.DecodedBeacon`` does not.  The FSM MUST check valid, confidence,
    and staleness via ``is_actionable()`` before consuming the event.

    Args:
        msg_id: Protocol message id (0–31).
        seq: Sequence bit (0 or 1).
        valid: Whether the protocol decode (parity + REF) passed.
        confidence: Vision confidence in [0.0, 1.0].
        timestamp: Monotonic timestamp (``time.monotonic()``) when the frame
            was captured.  ``None`` means unknown.
        source: Source identifier (e.g. ``"hikrobot"``, ``"fake"``).
        raw_bitmask: Raw 6-LED bitmask before mapping (``None`` if N/A).
        mapped_event: Human-readable event name from ``PatternMapper`` (``None`` if N/A).
    """

    msg_id: int
    seq: int | None
    valid: bool
    confidence: float
    timestamp: float | None = None
    source: str = "unknown"
    raw_bitmask: int | None = None
    mapped_event: str | None = None

    def is_actionable(
        self,
        min_confidence: float = 0.7,
        max_age_s: float = 2.0,
        now: float | None = None,
    ) -> bool:
        """Return True if this event meets confidence and staleness thresholds.

        Args:
            min_confidence: Minimum required confidence.
            max_age_s: Maximum allowed age in seconds.
            now: Current monotonic time.  Uses ``time.monotonic()`` if None.
        """
        if not self.valid:
            return False
        if self.confidence < min_confidence:
            return False
        if self.timestamp is not None and max_age_s > 0:
            t = now if now is not None else time.monotonic()
            if t - self.timestamp > max_age_s:
                return False
        return True

    @classmethod
    def from_decoded_beacon(
        cls,
        decoded: DecodedBeacon,
        timestamp: float | None = None,
    ) -> BeaconEvent:
        """Create a BeaconEvent from a vision-level DecodedBeacon.

        Args:
            decoded: Vision-level decoded beacon (with confidence).
            timestamp: Optional capture timestamp override.
        """
        return cls(
            msg_id=decoded.msg_id,
            seq=decoded.seq,
            valid=decoded.valid,
            confidence=decoded.confidence,
            timestamp=timestamp,
            source=decoded.source,
        )


# ---------------------------------------------------------------------------
# ActionIntent — FSM output, NOT a hardware command
# ---------------------------------------------------------------------------


from enum import Enum as _Enum, auto as _auto


class ActionIntent(_Enum):
    """FSM decision intent — NEVER directly drives motors or hardware.

    These are high-level intents that downstream layers (motion planner,
    robot controller, etc.) may interpret.  In this round they are purely
    informational and do NOT connect to real actuators.
    """

    NOOP = _auto()
    HOLD_POSITION = _auto()
    ALLOW_NEXT_STAGE = _auto()
    REQUEST_RETRY = _auto()
    START_ASSEMBLY_ALIGN = _auto()
    START_INSERTION = _auto()
    LOCK_WEAPON = _auto()
    ENTER_MF = _auto()
    SEARCH_KFS = _auto()
    ENTER_BATTLE = _auto()
    PLACE_KFS = _auto()
    ABORT_MOTION = _auto()
    ESTOP_STOP = _auto()
    REPORT_ERROR = _auto()
    WAIT = _auto()
