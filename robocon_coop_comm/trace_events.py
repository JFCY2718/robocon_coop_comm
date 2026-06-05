"""Pipeline trace events for performance measurement.

Records timestamped events along the dojo end-to-end pipeline.
Used for latency analysis, not for control.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class TraceEvent:
    """A single timestamped pipeline event."""

    name: str
    timestamp_ns: int
    step_label: str = ""
    msg_id: int | None = None
    msg_name: str = ""
    r1_state: str = ""
    r2_state: str = ""
    detail: str = ""


class TraceRecorder:
    """Records and queries pipeline trace events."""

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    def record(self, name: str, **kwargs: object) -> TraceEvent:
        """Record a trace event with current timestamp."""
        event = TraceEvent(
            name=name,
            timestamp_ns=time.perf_counter_ns(),
            step_label=str(kwargs.get("step_label", "")),
            msg_id=int(kwargs["msg_id"]) if "msg_id" in kwargs else None,
            msg_name=str(kwargs.get("msg_name", "")),
            r1_state=str(kwargs.get("r1_state", "")),
            r2_state=str(kwargs.get("r2_state", "")),
            detail=str(kwargs.get("detail", "")),
        )
        self._events.append(event)
        return event

    def events(self) -> list[TraceEvent]:
        """Return a copy of all recorded events."""
        return list(self._events)

    def clear(self) -> None:
        """Clear all recorded events."""
        self._events.clear()

    def duration_ms(self, start_event: str, end_event: str) -> float:
        """Return duration in ms between the first start_event and first end_event.

        Raises:
            ValueError: if either event is not found.
        """
        start_ts: int | None = None
        end_ts: int | None = None
        for e in self._events:
            if e.name == start_event and start_ts is None:
                start_ts = e.timestamp_ns
            if e.name == end_event and end_ts is None:
                end_ts = e.timestamp_ns
            if start_ts is not None and end_ts is not None:
                break
        if start_ts is None:
            raise ValueError(f"start event not found: {start_event}")
        if end_ts is None:
            raise ValueError(f"end event not found: {end_event}")
        return (end_ts - start_ts) / 1_000_000.0

    def summary(self) -> dict[str, float]:
        """Return summary statistics."""
        total = len(self._events)
        if total < 2:
            return {"total_events": float(total), "total_duration_ms": 0.0}
        duration = (self._events[-1].timestamp_ns - self._events[0].timestamp_ns) / 1_000_000.0
        return {"total_events": float(total), "total_duration_ms": duration}
