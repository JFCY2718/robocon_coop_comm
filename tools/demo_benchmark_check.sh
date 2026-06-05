#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

OUTPUT=$(python -m robocon_coop_comm.demo_benchmark --iterations 20)

echo "$OUTPUT"

PASS=1
for KEY in benchmark_dojo_pipeline avg_ms p95_ms successful_iterations; do
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
