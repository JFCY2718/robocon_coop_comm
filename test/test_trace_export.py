"""Tests for Chrome Trace JSON export."""

from __future__ import annotations

import json
import tempfile

import pytest

from robocon_coop_comm.trace_events import TraceRecorder
from robocon_coop_comm.trace_export import trace_events_to_chrome_json, write_chrome_trace

cv2 = pytest.importorskip("cv2")


def _make_events() -> list:
    r = TraceRecorder()
    r.record("start", step_label="s1", msg_id=4, msg_name="INSERT_ALLOWED")
    r.record("end", step_label="s2", r2_state="INSERTING")
    return r.events()


class TestChromeJson:
    def test_returns_dict(self) -> None:
        data = trace_events_to_chrome_json(_make_events())
        assert isinstance(data, dict)

    def test_has_trace_events(self) -> None:
        data = trace_events_to_chrome_json(_make_events())
        assert "traceEvents" in data

    def test_event_count(self) -> None:
        events = _make_events()
        data = trace_events_to_chrome_json(events)
        assert len(data["traceEvents"]) == len(events)

    def test_event_fields(self) -> None:
        data = trace_events_to_chrome_json(_make_events())
        e = data["traceEvents"][0]
        assert "name" in e
        assert "ph" in e
        assert "ts" in e
        assert "args" in e

    def test_ts_starts_near_zero(self) -> None:
        data = trace_events_to_chrome_json(_make_events())
        first_ts = data["traceEvents"][0]["ts"]
        assert first_ts >= 0.0
        assert first_ts < 1000.0  # should be near 0 microseconds

    def test_args_populated(self) -> None:
        data = trace_events_to_chrome_json(_make_events())
        args = data["traceEvents"][0]["args"]
        assert args["step_label"] == "s1"
        assert args["msg_id"] == 4


class TestWriteChromeTrace:
    def test_writes_file(self) -> None:
        events = _make_events()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        write_chrome_trace(path, events)
        with open(path) as f:
            data = json.load(f)
        assert "traceEvents" in data
        assert len(data["traceEvents"]) == len(events)
