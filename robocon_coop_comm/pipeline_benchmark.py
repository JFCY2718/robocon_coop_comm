"""Pipeline benchmark: measures end-to-end dojo pipeline latency.

Wraps DojoEndToEndPipeline with TraceRecorder for performance measurement.
This is a MEASUREMENT tool, not a control tool.

Supports warmup iterations to separate cold-start from steady-state latency.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dojo_end_to_end import DojoEndToEndPipeline, DojoStepResult
from .trace_events import TraceRecorder


@dataclass
class BenchmarkResult:
    """Result of running multiple pipeline iterations."""

    # Legacy fields (kept for backward compatibility)
    iterations: int
    total_ms: float
    avg_ms: float
    min_ms: float
    max_ms: float
    p95_ms: float
    successful_iterations: int

    # Warmup fields
    warmup_iterations: int = 0
    measured_iterations: int = 0
    cold_start_ms: float | None = None
    warm_avg_ms: float | None = None
    warm_min_ms: float | None = None
    warm_max_ms: float | None = None
    warm_p95_ms: float | None = None


# The sequence of dojo steps to execute
_DOJO_STEPS: list[tuple[str, str, dict[str, bool] | None, dict[str, bool] | None]] = [
    ("START", "s", None, None),
    ("R1_ROD_CLAMPED", "n", {"rod_clamped": True}, None),
    ("R1_AT_ASSEMBLY_POSE", "n", {"in_assembly_pose": True}, None),
    ("INSERT_ALLOWED", "n", {"rod_pose_locked": True, "chassis_stopped": True},
     {"head_grabbed": True, "r1_tag_visible": True, "pre_insert_pose_ok": True}),
    ("WEAPON_LOCKED", "n", {"weapon_locked": True}, {"insertion_motion_done": True}),
    ("R1_CLEAR_MC", "n", {"r1_clear_mc": True}, None),
    ("R1_IN_MF", "n", {"r1_in_mf": True}, None),
]


def run_dojo_pipeline_once() -> tuple[list[DojoStepResult], TraceRecorder]:
    """Run one full dojo pipeline with tracing.

    Returns:
        (step_results, recorder)
    """
    pipeline = DojoEndToEndPipeline()
    recorder = TraceRecorder()
    results: list[DojoStepResult] = []

    for label, key, r1_sensors, r2_sensors in _DOJO_STEPS:
        if r1_sensors:
            pipeline.set_r1_sensor(**r1_sensors)
        if r2_sensors:
            pipeline.set_r2_sensor(**r2_sensors)

        recorder.record("operator_command", step_label=label, detail=f"key={key}")
        r = pipeline.execute_key(label, key)
        recorder.record("r1_fsm_updated", step_label=label,
                        msg_id=r.r1_msg_id, msg_name=r.r1_msg_name, r1_state=r.r1_state)
        recorder.record("serial_frame_written", step_label=label, detail=r.frame_hex)
        recorder.record("mcu_led_updated", step_label=label)
        recorder.record("virtual_frame_generated", step_label=label)
        recorder.record("beacon_decoded", step_label=label)
        recorder.record("beacon_stabilized", step_label=label,
                        detail=f"valid={r.stable_valid}")
        recorder.record("r2_fsm_updated", step_label=label, r2_state=r.r2_state)
        recorder.record("dojo_step_complete", step_label=label,
                        msg_id=r.r1_msg_id, r2_state=r.r2_state)
        results.append(r)

    return results, recorder


def _run_one_and_get_duration() -> float | None:
    """Run one pipeline iteration. Returns duration_ms or None on failure."""
    try:
        results, recorder = run_dojo_pipeline_once()
        if results and results[-1].r1_msg_id == 7:
            return recorder.duration_ms("operator_command", "dojo_step_complete")
    except Exception:
        pass
    return None


def _compute_stats(durations: list[float]) -> tuple[float, float, float, float, float]:
    """Compute (total, avg, min, max, p95) from a sorted list of durations."""
    if not durations:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    durations.sort()
    total = sum(durations)
    p95_idx = min(int(len(durations) * 0.95), len(durations) - 1)
    return total, total / len(durations), durations[0], durations[-1], durations[p95_idx]


def benchmark_dojo_pipeline(
    iterations: int = 100,
    warmup_iterations: int = 1,
) -> BenchmarkResult:
    """Run the full dojo pipeline multiple times and collect timing stats.

    Args:
        iterations: number of measured pipeline runs.
        warmup_iterations: number of warmup runs (not counted in stats).
            The first warmup run's duration is recorded as cold_start_ms.

    Returns:
        BenchmarkResult with timing statistics.
    """
    # Warmup phase
    cold_start: float | None = None
    for i in range(warmup_iterations):
        d = _run_one_and_get_duration()
        if i == 0 and d is not None:
            cold_start = d

    # Measured phase
    durations: list[float] = []
    successful = 0
    for _ in range(iterations):
        d = _run_one_and_get_duration()
        if d is not None:
            durations.append(d)
            successful += 1

    total, avg, mn, mx, p95 = _compute_stats(list(durations))

    # Legacy fields: keep measured data as the primary values
    return BenchmarkResult(
        iterations=iterations,
        total_ms=total,
        avg_ms=avg,
        min_ms=mn,
        max_ms=mx,
        p95_ms=p95,
        successful_iterations=successful,
        warmup_iterations=warmup_iterations,
        measured_iterations=iterations,
        cold_start_ms=cold_start,
        warm_avg_ms=avg,
        warm_min_ms=mn,
        warm_max_ms=mx,
        warm_p95_ms=p95,
    )
