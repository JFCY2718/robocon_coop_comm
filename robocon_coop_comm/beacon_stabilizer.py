"""Beacon stabilizer: requires N consecutive consistent frames before accepting a signal.

Simulates real-world vision where a single-frame decode could be noisy.
Only outputs valid=True after min_stable_frames consecutive frames with
the same msg_id and seq.
"""

from __future__ import annotations

from .beacon_types import DecodedBeacon


class BeaconStabilizer:
    """Tracks consecutive stable frames and gates validity.

    Args:
        min_stable_frames: number of consecutive identical (msg_id, seq) frames
            required before outputting valid=True.
    """

    def __init__(self, min_stable_frames: int = 3) -> None:
        if min_stable_frames < 1:
            raise ValueError("min_stable_frames must be >= 1")
        self.min_stable_frames = min_stable_frames
        self._stable_count = 0
        self._last_msg_id: int | None = None
        self._last_seq: int | None = None

    def update(self, decoded: DecodedBeacon) -> DecodedBeacon:
        """Feed one decoded beacon and return a (possibly gated) result.

        Args:
            decoded: raw decoded beacon from BeaconDecoder.

        Returns:
            DecodedBeacon with valid gated by stability requirement.
        """
        if not decoded.valid:
            self._stable_count = 0
            self._last_msg_id = None
            self._last_seq = None
            return DecodedBeacon(
                msg_id=decoded.msg_id,
                msg_name=decoded.msg_name,
                seq=decoded.seq,
                valid=False,
                confidence=decoded.confidence,
                source=decoded.source,
                reason="invalid_input",
                raw_bits=decoded.raw_bits,
            )

        # Check if this frame matches the previous one
        if decoded.msg_id == self._last_msg_id and decoded.seq == self._last_seq:
            self._stable_count += 1
        else:
            self._stable_count = 1
            self._last_msg_id = decoded.msg_id
            self._last_seq = decoded.seq

        if self._stable_count >= self.min_stable_frames:
            return DecodedBeacon(
                msg_id=decoded.msg_id,
                msg_name=decoded.msg_name,
                seq=decoded.seq,
                valid=True,
                confidence=decoded.confidence,
                source=decoded.source,
                reason="stable",
                raw_bits=decoded.raw_bits,
            )

        return DecodedBeacon(
            msg_id=decoded.msg_id,
            msg_name=decoded.msg_name,
            seq=decoded.seq,
            valid=False,
            confidence=decoded.confidence * (self._stable_count / self.min_stable_frames),
            source=decoded.source,
            reason=f"waiting_for_stability ({self._stable_count}/{self.min_stable_frames})",
            raw_bits=decoded.raw_bits,
        )
