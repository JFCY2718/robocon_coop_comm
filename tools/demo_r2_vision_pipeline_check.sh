#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

OUTPUT=$(python -m robocon_coop_comm.demo_r2_vision_pipeline)

echo "$OUTPUT"

PASS=1
for KEY in R1_ROD_CLAMPED R1_AT_ASSEMBLY_POSE INSERT_ALLOWED WEAPON_LOCKED R1_CLEAR_MC R1_IN_MF stable "R2 state" action_hint; do
    if ! echo "$OUTPUT" | grep -q "$KEY"; then
        echo "FAIL: missing $KEY"
        PASS=0
    fi
done

if [ "$PASS" -eq 1 ]; then
    echo ""
    echo "demo_r2_vision_pipeline check passed"
    exit 0
else
    exit 1
fi
