"""Time-aware voting gate for optical beacon protocol readings."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import time

from .beacon_types import DecodedBeacon
from .coop_protocol_v2 import CoopMessage


@dataclass(frozen=True)
class _Observation:
    key: tuple[int, int] | None
    confidence: float
    timestamp: float


class TemporalBeaconValidator:
    """Gate single-frame protocol decodes with bounded temporal evidence.

    Ordinary messages use an M-of-N vote.  Motion-authorising messages use a
    stricter consecutive-frame rule so one or two corrupt frames cannot trigger
    insertion or release.  Old observations automatically leave the window.
    """

    def __init__(
        self,
        *,
        window_size: int = 5,
        min_matches: int = 3,
        dangerous_consecutive: int = 5,
        min_confidence: float = 0.70,
        max_age_s: float = 0.30,
        dangerous_ids: set[int] | None = None,
    ) -> None:
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        if not 1 <= min_matches <= window_size:
            raise ValueError("min_matches must be in [1, window_size]")
        if not 1 <= dangerous_consecutive <= window_size:
            raise ValueError("dangerous_consecutive must be in [1, window_size]")
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be in [0, 1]")
        if max_age_s <= 0.0:
            raise ValueError("max_age_s must be positive")

        self.window_size = int(window_size)
        self.min_matches = int(min_matches)
        self.dangerous_consecutive = int(dangerous_consecutive)
        self.min_confidence = float(min_confidence)
        self.max_age_s = float(max_age_s)
        self.dangerous_ids = set(
            dangerous_ids
            if dangerous_ids is not None
            else {
                int(CoopMessage.INSERT_ALLOWED),
                int(CoopMessage.TOP_RELEASE_ALLOWED),
            }
        )
        self._observations: deque[_Observation] = deque(maxlen=self.window_size)

    def reset(self) -> None:
        self._observations.clear()

    def update(
        self,
        decoded: DecodedBeacon,
        *,
        timestamp: float | None = None,
        now: float | None = None,
    ) -> DecodedBeacon:
        """Add one reading and return a validity-gated beacon."""
        current_time = time.monotonic() if now is None else float(now)
        observed_time = current_time if timestamp is None else float(timestamp)
        self._purge_old(current_time)

        if current_time - observed_time > self.max_age_s:
            self._observations.append(_Observation(None, 0.0, current_time))
            return _gated(decoded, "stale_input")
        if not decoded.valid:
            self._observations.append(_Observation(None, 0.0, observed_time))
            return _gated(decoded, "invalid_input")
        if decoded.confidence < self.min_confidence:
            self._observations.append(_Observation(None, decoded.confidence, observed_time))
            return _gated(decoded, "low_confidence")

        key = (int(decoded.msg_id), int(decoded.seq))
        self._observations.append(_Observation(key, decoded.confidence, observed_time))
        if decoded.msg_id in self.dangerous_ids:
            count = self._trailing_count(key)
            required = self.dangerous_consecutive
            reason = f"dangerous_consecutive ({count}/{required})"
        else:
            count = sum(item.key == key for item in self._observations)
            required = self.min_matches
            reason = f"temporal_vote ({count}/{required} in {self.window_size})"

        if count < required:
            return _gated(decoded, reason, confidence=decoded.confidence * count / required)

        matching = [
            item.confidence for item in self._observations if item.key == key
        ]
        stable_confidence = min(matching[-required:])
        return DecodedBeacon(
            msg_id=decoded.msg_id,
            msg_name=decoded.msg_name,
            seq=decoded.seq,
            valid=True,
            confidence=stable_confidence,
            source=decoded.source,
            reason=reason,
            raw_bits=decoded.raw_bits,
        )

    def _purge_old(self, now: float) -> None:
        while self._observations and now - self._observations[0].timestamp > self.max_age_s:
            self._observations.popleft()

    def _trailing_count(self, key: tuple[int, int]) -> int:
        count = 0
        for item in reversed(self._observations):
            if item.key != key:
                break
            count += 1
        return count


def _gated(
    decoded: DecodedBeacon,
    reason: str,
    *,
    confidence: float | None = None,
) -> DecodedBeacon:
    return DecodedBeacon(
        msg_id=decoded.msg_id,
        msg_name=decoded.msg_name,
        seq=decoded.seq,
        valid=False,
        confidence=decoded.confidence if confidence is None else confidence,
        source=decoded.source,
        reason=reason,
        raw_bits=decoded.raw_bits,
    )
