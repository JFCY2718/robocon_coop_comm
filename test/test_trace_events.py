"""Tests for trace event recorder."""

from __future__ import annotations

import pytest

from robocon_coop_comm.trace_events import TraceRecorder


class TestTraceRecorder:
    def test_record_event(self) -> None:
        r = TraceRecorder()
        e = r.record("test_event", step_label="step1", msg_id=4)
        assert e.name == "test_event"
        assert e.step_label == "step1"
        assert e.msg_id == 4

    def test_events_returns_list(self) -> None:
        r = TraceRecorder()
        r.record("a")
        r.record("b")
        events = r.events()
        assert len(events) == 2
        assert events[0].name == "a"
        assert events[1].name == "b"

    def test_duration_ms_non_negative(self) -> None:
        r = TraceRecorder()
        r.record("start")
        r.record("end")
        d = r.duration_ms("start", "end")
        assert d >= 0.0

    def test_duration_ms_missing_event_raises(self) -> None:
        r = TraceRecorder()
        r.record("start")
        with pytest.raises(ValueError, match="end event not found"):
            r.duration_ms("start", "nonexistent")

    def test_duration_ms_missing_start_raises(self) -> None:
        r = TraceRecorder()
        r.record("end")
        with pytest.raises(ValueError, match="start event not found"):
            r.duration_ms("nonexistent", "end")

    def test_clear(self) -> None:
        r = TraceRecorder()
        r.record("a")
        r.record("b")
        r.clear()
        assert r.events() == []

    def test_summary(self) -> None:
        r = TraceRecorder()
        r.record("a")
        r.record("b")
        s = r.summary()
        assert "total_events" in s
        assert "total_duration_ms" in s
        assert s["total_events"] == 2.0
        assert s["total_duration_ms"] >= 0.0
