"""Benchmark demo: measures end-to-end dojo pipeline latency.

Usage:
    python -m robocon_coop_comm.demo_benchmark --iterations 100 --warmup-iterations 1
    python -m robocon_coop_comm.demo_benchmark --iterations 20 --warmup-iterations 1 --trace-out /tmp/trace.json
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the dojo end-to-end pipeline.")
    parser.add_argument("--iterations", type=int, default=100, help="Number of measured iterations")
    parser.add_argument("--warmup-iterations", type=int, default=1, help="Number of warmup iterations")
    parser.add_argument("--trace-out", type=str, default=None, help="Export Chrome Trace JSON to path")
    parser.add_argument("--verbose", action="store_true", help="Print trace events")
    args = parser.parse_args()

    from .pipeline_benchmark import benchmark_dojo_pipeline, run_dojo_pipeline_once

    if args.verbose:
        results, recorder = run_dojo_pipeline_once()
        print("Trace events from one run:")
        for e in recorder.events():
            print(f"  {e.name:30s} step={e.step_label:20s} detail={e.detail}")
        print()

    if args.trace_out:
        _, recorder = run_dojo_pipeline_once()
        from .trace_export import write_chrome_trace
        write_chrome_trace(args.trace_out, recorder.events())
        print(f"trace_out: {args.trace_out}")
        print()

    result = benchmark_dojo_pipeline(
        iterations=args.iterations,
        warmup_iterations=args.warmup_iterations,
    )

    print(f"benchmark_dojo_pipeline: {result.iterations} iterations")
    print(f"  warmup_iterations: {result.warmup_iterations}")
    print(f"  measured_iterations: {result.measured_iterations}")
    print(f"  successful_iterations: {result.successful_iterations}")
    if result.cold_start_ms is not None:
        print(f"  cold_start_ms: {result.cold_start_ms:.3f}")
    else:
        print("  cold_start_ms: N/A")
    print(f"  avg_ms: {result.avg_ms:.3f}")
    print(f"  min_ms: {result.min_ms:.3f}")
    print(f"  max_ms: {result.max_ms:.3f}")
    print(f"  p95_ms: {result.p95_ms:.3f}")
    if result.warm_avg_ms is not None:
        print(f"  warm_avg_ms: {result.warm_avg_ms:.3f}")
    if result.warm_p95_ms is not None:
        print(f"  warm_p95_ms: {result.warm_p95_ms:.3f}")


if __name__ == "__main__":
    main()
