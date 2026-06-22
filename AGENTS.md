# AI Coding Agent Instructions

Project: ROBOCON 2026 R1/R2 cooperative optical communication.

Hard constraints:

1. Do not implement R1/R2 wireless communication.
2. Do not implement contact-based communication for the MC weapon assembly phase.
3. Do not let operator commands directly control R2.
4. Do not let operator commands directly set individual LEDs.
5. R1 operator commands must go through R1MissionFSM guards.
6. R2 must treat R1 beacon messages as event cues and must check local sensors before actions.
7. Do NOT claim M3 or real-hardware acceptance until real camera + STM32 logs verify it.
8. Mock / unit-test results are NOT real camera results.
9. Vision messages (beacons) must NOT bypass local safety conditions.
10. FSM output is ActionIntent only — never drive motors/hardware directly.
11. ESTOP > ABORT > HOLD > ERROR > normal mission events.

Current phase (2026-06-22):

- **Round FSM-A completed**: R1/R2 Mission FSM safety hardening.
- **Round 4A**: Hikrobot real camera 6-LED breadboard bitmask smoke/stability test.
- pytest: 556 passed.
- STM32 6 LEDs confirmed working (PA0-PA5, D0=bit0 … PAR=bit5).
- MVS SDK import OK. OpenCV ROI window opens.
- Breadboard ROI: `data/sixled/configs/breadboard_roi.json` (temporary, not final).
- Do NOT modify AprilTag, ROS2, or competition semantics during Round 4A.
- Current goal: verify STM32 6LED on/off → camera → OpenCV ROI → Python bitmask.

Recent Round FSM-A additions:

- `beacon_types.py`: BeaconEvent (vision→FSM bridge), ActionIntent (FSM output enum)
- `r2_fsm.py`: confidence/staleness/local_estop guards, RETRY_RESET recovery
- `r1_fsm.py`: ABORT state, local_estop, RETRY recovery
- `demo_fsm_safety.py`: 26-scenario FSM safety simulation
- `docs/FSM_SAFETY_DESIGN.md`: full FSM safety architecture doc
- `docs/R1_R2_MISSION_FSM.md`: FSM state/guard/transition tables
- `docs/HANDOFF_TO_NEXT_CC_SESSION.md`: handoff guide for next session

Useful commands:

```bash
source .venv/bin/activate
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
python -m robocon_coop_comm.demo_fsm_safety

python tools/hikrobot_6led_live.py --help
python tools/sixled_log_summary.py --help

# MVS SDK env (each new terminal):
export MVCAM_COMMON_RUNENV=/opt/MVS/lib
export PYTHONPATH=/opt/MVS/Samples/64/Python/MvImport:$PYTHONPATH
export LD_LIBRARY_PATH=/opt/MVS/lib/64:/opt/MVS/bin:$LD_LIBRARY_PATH

# ROI calibration:
python tools/hikrobot_6led_live.py --save-roi data/sixled/configs/breadboard_roi.json --threshold 40 --exposure 12000 --gain 0 --timeout 5000

# Realtime decode:
python tools/hikrobot_6led_live.py --roi-file data/sixled/configs/breadboard_roi.json --threshold 40 --exposure 12000 --gain 0 --timeout 5000 --log data/sixled/logs/round4a_t40_e12000.csv --protocol

# Log summary:
python tools/sixled_log_summary.py data/sixled/logs/round4a_t40_e12000.csv
```

Key docs:

- `docs/FSM_SAFETY_DESIGN.md` — FSM safety architecture (NEW)
- `docs/R1_R2_MISSION_FSM.md` — R1/R2 FSM details (NEW)
- `docs/HANDOFF_TO_NEXT_CC_SESSION.md` — handoff guide (NEW)
- `docs/HIKROBOT_6LED_BREADBOARD_TEST.md` — full breadboard test guide
- `docs/HIKROBOT_REAL_CAMERA.md` — camera setup + SDK config
- `firmware/README_SIXLED_TEST.md` — STM32 test firmware guide

Next good tasks:

1. Complete Round 4A bitmask verification (0x00 through 0x3F).
2. Gather real camera logs → `sixled_log_summary.py` → tune threshold/exposure.
3. If link is stable, move to round 4B (sequential bitmask switching with STM32).
4. After hardware link proven stable, integrate BeaconEvent into R2 vision pipeline.
5. Add R2 FSM timeout detection (no message for N seconds → HOLD).
6. Expand R2 FSM states for MF and Battle zones.
