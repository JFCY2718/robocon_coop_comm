"""Chrome Trace JSON export for pipeline trace events.

Exports TraceRecorder events to Chrome Trace format, viewable in:
- chrome://tracing
- Perfetto UI (https://ui.perfetto.dev/)
"""

from __future__ import annotations

import json
from pathlib import Path

from .trace_events import TraceEvent


def trace_events_to_chrome_json(
    events: list[TraceEvent],
    name: str = "robocon_coop_comm",
) -> dict:
    """Convert trace events to Chrome Trace JSON format.

    Args:
        events: list of TraceEvent from TraceRecorder.
        name: process name shown in the viewer.

    Returns:
        dict ready for json.dumps().
    """
    if not events:
        return {"traceEvents": [], "displayTimeUnit": "ms"}

    base_ts = events[0].timestamp_ns

    chrome_events: list[dict] = []
    for e in events:
        ts_us = (e.timestamp_ns - base_ts) / 1_000.0  # nanoseconds -> microseconds
        args: dict[str, object] = {}
        if e.step_label:
            args["step_label"] = e.step_label
        if e.msg_id is not None:
            args["msg_id"] = e.msg_id
        if e.msg_name:
            args["msg_name"] = e.msg_name
        if e.r1_state:
            args["r1_state"] = e.r1_state
        if e.r2_state:
            args["r2_state"] = e.r2_state
        if e.detail:
            args["detail"] = e.detail

        chrome_events.append({
            "name": e.name,
            "cat": "pipeline",
            "ph": "i",  # instant event
            "s": "t",   # thread-level scope
            "ts": ts_us,
            "pid": 1,
            "tid": 1,
            "args": args,
        })

    return {
        "traceEvents": chrome_events,
        "displayTimeUnit": "ms",
    }


def write_chrome_trace(
    path: str,
    events: list[TraceEvent],
    name: str = "robocon_coop_comm",
) -> None:
    """Write trace events to a Chrome Trace JSON file.

    Args:
        path: output file path.
        events: list of TraceEvent.
        name: process name shown in the viewer.
    """
    data = trace_events_to_chrome_json(events, name)
    Path(path).write_text(json.dumps(data, indent=2))
