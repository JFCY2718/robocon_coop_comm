# R2 Vision Field Verification — Session State

**Date:** 2026-07-20
**Session:** Partial — Phase 0-2 complete, Phase 3 blocked on hardware

## Repository

- Remote: `https://github.com/JFCY2718/robocon_coop_comm`
- Branch: `feature/four-light-optical`
- HEAD: `4d234ec703d35a25cd912d866b570bdd1c6fbbba`

## Phase Status

| Phase | Status | Notes |
|-------|--------|-------|
| 0: Repo & Safety | ✅ OK | Branch correct, minimum commit is ancestor, 280x220 config matches frozen values |
| 1: Ubuntu Software | ✅ OK | pytest 737 passed, ruff clean, all --help OK, dry-run OK |
| 2: MVS Environment | ✅ OK | MVS SDK at /opt/MVS, MvImport OK, ttyACM0 present |
| 3: AprilTag Smoke | ⚠️ BLOCKED | Camera works (MV-CS016-10UC, 1440x1080), but no tag visible — need to place beacon board in view |
| 4: Fixed ROI | ⬜ PENDING | |
| 5: Competition | ⬜ PENDING | |
| 6: LED Gains | ⬜ PENDING | |
| 7: 16-State E-vs-O | ⬜ PENDING | |
| 8: Fault & Safety | ⬜ PENDING | |
| 9: R2 Dry-Run | ⬜ PENDING | |
| 10: Final Report | ⬜ PENDING | |

## Key Findings

1. **MV-CS016-10UC camera** (not MV-CA050-20UC) — USB3 Vision, works with MVS SDK
2. **MV_USB_DEVICE = 4** (not 2) — USB cameras enumerate with tlayer=4 only
3. **MVS GigE+USB combined (5)** does not enumerate USB cameras correctly
4. Image at 5000us/gain0 is dark (mean=17), needs tag+lighting adjustment

## Environment Variables Needed

```bash
export MVCAM_COMMON_RUNENV=/opt/MVS/lib
export PYTHONPATH=/opt/MVS/Samples/64/Python/MvImport:$PYTHONPATH
export LD_LIBRARY_PATH=/opt/MVS/lib/64:/opt/MVS/bin:$LD_LIBRARY_PATH
```

## Stashed Changes

```
stash@{0}: WIP on four-light-optical (pre-pull local modifications)
stash@{1}: On main (local .gitignore)
```

## Resume Instructions

1. Connect camera, place beacon board with tag36h11 ID0 in view
2. Activate venv: `cd ~/rc/robocon_coop_comm && source .venv/bin/activate`
3. Set MVS env vars (see above)
4. Start Phase 3: `python tools/hikrobot_apriltag_smoke.py --family tag36h11 --tag-id 0 --exposure 5000 --gain 0 --log-jsonl /tmp/robocon_r2/logs/tag_smoke.jsonl`
5. Proceed through phases 4-10
