"""Benchmark demo: measures end-to-end dojo pipeline latency.

Usage:
    python -m robocon_coop_comm.demo_benchmark --iterations 100
    python -m robocon_coop_comm.demo_benchmark --iterations 20 --verbose
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the dojo end-to-end pipeline.")
    parser.add_argument("--iterations", type=int, default=100, help="Number of iterations")
    parser.add_argument("--verbose", action="store_true", help="Print trace events")
    args = parser.parse_args()

    from .pipeline_benchmark import benchmark_dojo_pipeline, run_dojo_pipeline_once

    if args.verbose:
        results, recorder = run_dojo_pipeline_once()
        print("Trace events from one run:")
        for e in recorder.events():
            print(f"  {e.name:30s} step={e.step_label:20s} detail={e.detail}")
        print()

    result = benchmark_dojo_pipeline(iterations=args.iterations)

    print(f"benchmark_dojo_pipeline: {result.iterations} iterations")
    print(f"  successful_iterations: {result.successful_iterations}")
    print(f"  avg_ms: {result.avg_ms:.3f}")
    print(f"  min_ms: {result.min_ms:.3f}")
    print(f"  max_ms: {result.max_ms:.3f}")
    print(f"  p95_ms: {result.p95_ms:.3f}")


if __name__ == "__main__":
    main()
