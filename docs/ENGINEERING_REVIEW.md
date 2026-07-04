# robocon_coop_comm Engineering Review Checklist

Use this when reviewing code changes.

## Git state

- Check `git status`.
- Check branch.
- Check `git remote -v`.
- Check recent commits.
- Check tag at HEAD.
- Do not force push.
- Do not rewrite main.

## Protocol checks

Confirm fixed six-led order remains:

```text
D0  bit0 0x01
D1  bit1 0x02
D2  bit2 0x04
REF bit3 0x08
SEQ bit4 0x10
PAR bit5 0x20
```

For Rscontrol2 protocol, confirm:

```text
BC 00 mask seq 55
mask = value & 0x3F
seq wraps 0~255
```

For ASCII protocol, confirm old behavior remains.

## Tool checks

Check:

```bash
python tools/sixled_serial_sequence.py --help
python tools/sixled_log_summary.py --help
python tools/sixled_expected_observed_check.py --help
```

If Hikrobot SDK is unavailable, do not require real camera tests.

## Test checks

Windows:

```bash
python -m pytest -q
```

Ubuntu:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
```

## Artifact checks

Ensure no real logs, ROI, frames, or build outputs are committed.

Allowed:

```text
.gitkeep
small artificial test fixtures
```

Not allowed:

```text
real data/sixled/logs/*
real data/sixled/frames/*
data/sixled/configs/breadboard_roi.json
```

## Safety checks

Confirm:

- No vision-to-dangerous-action shortcut.
- No bypass of R2MissionFSM.
- No unrequested ROS2 integration.
- No unrequested AprilTag integration.
- No unrequested hardware loop.

## Report categories

Use:

```text
BLOCKER:
WARNING:
OK:
```

Only modify code during a review if the issue is small and unambiguous.
