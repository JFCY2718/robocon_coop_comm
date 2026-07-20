# R2 Vision Field Verification — Session State

**Date:** 2026-07-20
**Session:** Partial — Phase 0-2 complete, Phase 3 blocked on hardware placement

## Quick Resume

```bash
cd ~/rc/robocon_coop_comm && source .venv/bin/activate
git pull --ff-only origin feature/four-light-optical
export MVCAM_COMMON_RUNENV=/opt/MVS/lib
export PYTHONPATH=/opt/MVS/Samples/64/Python/MvImport:$PYTHONPATH
export LD_LIBRARY_PATH=/opt/MVS/lib/64:/opt/MVS/bin:$LD_LIBRARY_PATH
```

Then place beacon board (280×220mm, tag36h11 ID0) in camera view and continue from Phase 3.

**Full guide**: `docs/R2_VISION_FIELD_HANDOFF.md` ← READ THIS FIRST

## Repository

- Remote: `https://github.com/JFCY2718/robocon_coop_comm`
- Branch: `feature/four-light-optical`
- HEAD: `989bf23` (pushed)

## Phase Status

| Phase | Status |
|-------|--------|
| 0: Repo & Safety | ✅ OK |
| 1: Ubuntu Software | ✅ OK (737 passed) |
| 2: MVS Environment | ✅ OK (MV-CS016-10UC) |
| 3: AprilTag Smoke | ⚠️ BLOCKER — camera works, tag not in view |
| 4-10 | ⬜ PENDING |

## Key Discoveries

1. Camera: **MV-CS016-10UC** (1440×1080), not MV-CA050-20UC
2. MVS USB tlayer: **MV_USB_DEVICE = 4** (not 2!)
3. Gain ceiling: **15** for MV-CS016-10UC (0x80000102 above)
4. Baseline image at 5000µs/gain0 is dim (mean=17)

## Stashed

```
stash@{0}: WIP on four-light-optical (pre-pull local modifications)
stash@{1}: On main (local .gitignore)
```
