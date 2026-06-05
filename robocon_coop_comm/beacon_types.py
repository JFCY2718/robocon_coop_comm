"""Vision-level beacon data types.

These types wrap protocol-level decoded results with vision metadata
(confidence, source, stability info).  They do NOT replace protocol.DecodedBeacon
which is used by R2 FSM.
"""

from __future__ import annotations

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
