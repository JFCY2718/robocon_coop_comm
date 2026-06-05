"""Pipeline benchmark: measures end-to-end dojo pipeline latency.

Wraps DojoEndToEndPipeline with TraceRecorder for performance measurement.
This is a MEASUREMENT tool, not a control tool.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dojo_end_to_end import DojoEndToEndPipeline, DojoStepResult
from .trace_events import TraceRecorder


@dataclass
class BenchmarkResult:
    """Result of running multiple pipeline iterations."""

    iterations: int
    total_ms: float
    avg_ms: float
    min_ms: float
    max_ms: float
    p95_ms: float
    successful_iterations: int


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


def benchmark_dojo_pipeline(iterations: int = 100) -> BenchmarkResult:
    """Run the full dojo pipeline multiple times and collect timing stats.

    Args:
        iterations: number of full pipeline runs.

    Returns:
        BenchmarkResult with timing statistics.
    """
    durations: list[float] = []
    successful = 0

    for _ in range(iterations):
        try:
            results, recorder = run_dojo_pipeline_once()
            # Check that we reached the final state
            if results and results[-1].r1_msg_id == 7:
                duration = recorder.duration_ms("operator_command", "dojo_step_complete")
                durations.append(duration)
                successful += 1
        except Exception:
            pass

    if not durations:
        return BenchmarkResult(
            iterations=iterations, total_ms=0.0, avg_ms=0.0,
            min_ms=0.0, max_ms=0.0, p95_ms=0.0,
            successful_iterations=0,
        )

    durations.sort()
    total = sum(durations)
    p95_idx = min(int(len(durations) * 0.95), len(durations) - 1)

    return BenchmarkResult(
        iterations=iterations,
        total_ms=total,
        avg_ms=total / len(durations),
        min_ms=durations[0],
        max_ms=durations[-1],
        p95_ms=durations[p95_idx],
        successful_iterations=successful,
    )
