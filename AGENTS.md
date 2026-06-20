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

Current phase (2026-06-20):

- **Round 4A**: Hikrobot real camera 6-LED breadboard bitmask smoke/stability test.
- pytest: 484 passed.
- STM32 6 LEDs confirmed working (PA0-PA5, D0=bit0 … PAR=bit5).
- MVS SDK import OK. OpenCV ROI window opens.
- Breadboard ROI: `data/sixled/configs/breadboard_roi.json` (temporary, not final).
- Do NOT modify AprilTag, ROS2, FSM, or competition semantics during Round 4A.
- Current goal: verify STM32 6LED on/off → camera → OpenCV ROI → Python bitmask.

Useful commands:

```bash
source .venv/bin/activate
pytest -q
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

Key docs for Round 4A:

- `docs/HIKROBOT_6LED_BREADBOARD_TEST.md` — full breadboard test guide
- `docs/HIKROBOT_REAL_CAMERA.md` — camera setup + SDK config
- `firmware/README_SIXLED_TEST.md` — STM32 test firmware guide

Next good tasks:

1. Complete Round 4A bitmask verification (0x00 through 0x3F).
2. Gather real camera logs → `sixled_log_summary.py` → tune threshold/exposure.
3. If link is stable, move to round 4B (sequential bitmask switching with STM32).
4. After hardware link proven stable, integrate with R2 FSM pipeline in controlled steps.
