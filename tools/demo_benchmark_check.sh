#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

OUTPUT=$(python -m robocon_coop_comm.demo_benchmark --iterations 20 --warmup-iterations 1)

echo "$OUTPUT"

PASS=1
for KEY in benchmark_dojo_pipeline warmup_iterations measured_iterations successful_iterations cold_start_ms avg_ms p95_ms warm_avg_ms warm_p95_ms; do
    if ! echo "$OUTPUT" | grep -q "$KEY"; then
        echo "FAIL: missing $KEY"
        PASS=0
    fi
done

if [ "$PASS" -eq 1 ]; then
    echo ""
    echo "demo_benchmark check passed"
    exit 0
else
    exit 1
fi
