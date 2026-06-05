"""Tests for pipeline benchmark."""

from __future__ import annotations

import pytest

from robocon_coop_comm.pipeline_benchmark import benchmark_dojo_pipeline, run_dojo_pipeline_once
from robocon_coop_comm.trace_export import trace_events_to_chrome_json

cv2 = pytest.importorskip("cv2")


class TestRunDojoPipelineOnce:
    def test_returns_step_results(self) -> None:
        results, recorder = run_dojo_pipeline_once()
        assert len(results) == 7  # 7 dojo steps

    def test_last_step_is_r1_in_mf(self) -> None:
        results, _ = run_dojo_pipeline_once()
        assert results[-1].r1_msg_id == 7
        assert results[-1].r1_msg_name == "R1_IN_MF"

    def test_recorder_has_dojo_step_complete(self) -> None:
        _, recorder = run_dojo_pipeline_once()
        events = recorder.events()
        names = [e.name for e in events]
        assert "dojo_step_complete" in names

    def test_recorder_can_export_chrome_trace(self) -> None:
        _, recorder = run_dojo_pipeline_once()
        data = trace_events_to_chrome_json(recorder.events())
        assert "traceEvents" in data
        assert len(data["traceEvents"]) > 0


class TestBenchmarkDojoPipeline:
    def test_successful_iterations(self) -> None:
        r = benchmark_dojo_pipeline(iterations=3)
        assert r.successful_iterations == 3

    def test_timing_non_negative(self) -> None:
        r = benchmark_dojo_pipeline(iterations=3)
        assert r.avg_ms >= 0.0
        assert r.min_ms >= 0.0
        assert r.max_ms >= 0.0
        assert r.p95_ms >= 0.0

    def test_p95_ge_min(self) -> None:
        r = benchmark_dojo_pipeline(iterations=3)
        assert r.p95_ms >= r.min_ms

    def test_total_ms_non_negative(self) -> None:
        r = benchmark_dojo_pipeline(iterations=3)
        assert r.total_ms >= 0.0


class TestBenchmarkWithWarmup:
    def test_warmup_fields_present(self) -> None:
        r = benchmark_dojo_pipeline(iterations=3, warmup_iterations=1)
        assert r.measured_iterations == 3
        assert r.warmup_iterations == 1
        assert r.cold_start_ms is not None
        assert r.warm_avg_ms is not None
        assert r.warm_p95_ms is not None
        assert r.successful_iterations == 3

    def test_no_warmup(self) -> None:
        r = benchmark_dojo_pipeline(iterations=3, warmup_iterations=0)
        assert r.cold_start_ms is None
        assert r.measured_iterations == 3
        assert r.warmup_iterations == 0
