# robocon_coop_comm Task Templates

## Development task template

```text
Please follow docs/PROJECT_RULES.md.

Task:
<describe exact change>

Context:
<only minimal context needed>

Must not change:
- six-led bit order
- old ascii protocol unless requested
- Rscontrol2 0xBC frame format
- FSM safety guards
- real hardware assumptions

Files likely relevant:
<list files>

Acceptance commands:
python -m pytest -q
python tools/sixled_serial_sequence.py --help
python tools/sixled_expected_observed_check.py --help
python tools/sixled_log_summary.py --help

Work on a feature branch.
Make minimal changes.
Add tests.
Update docs.
Do not commit logs/frames/ROI/build artifacts.
Commit, tag if requested, push.
Report using docs/PROJECT_RULES.md format.
```

## Review task template

```text
Please follow docs/PROJECT_RULES.md and docs/ENGINEERING_REVIEW.md.

Review current branch:
<branch or commit>

Do not modify code first.
Check git state, tests, help commands, protocol invariants, artifact safety, and docs.
Report as BLOCKER / WARNING / OK.
```

## Ubuntu handoff template

The current hardware handoff, frozen branch SHAs and execution phases are in
`docs/UBUNTU_HARDWARE_HANDOFF.md`. Use that file as the source of truth for the
four-light hardware-validation phase.

```text
Generate a Windows-to-Ubuntu handoff checklist for the current branch.
Include:
- git fetch/checkout/pull commands
- pytest command
- help commands
- MVS environment commands if relevant
- serial command if relevant
- expected-vs-observed command if relevant
Do not run hardware tests on Windows.
```
