#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

OUTPUT=$(python -m robocon_coop_comm.demo_cli <<'EOF'
start
rod
next
pose
next
lock
head
tag
pre
next
weapon
next
clear
next
mf
next
q
EOF
)

echo "$OUTPUT"

PASS=1
for KEY in INSERT_ALLOWED WEAPON_LOCKED R1_CLEAR_MC R1_IN_MF; do
    if ! echo "$OUTPUT" | grep -q "$KEY"; then
        echo "FAIL: missing $KEY"
        PASS=0
    fi
done

if [ "$PASS" -eq 1 ]; then
    echo ""
    echo "demo_cli scripted check passed"
    exit 0
else
    exit 1
fi
