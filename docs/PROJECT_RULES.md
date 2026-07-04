# robocon_coop_comm Project Rules

## Repository role

robocon_coop_comm handles:

- R1/R2 cooperation communication.
- Six-led beacon visual communication.
- Hikrobot camera decoding.
- Round 4B expected-vs-observed validation.
- R1/R2 Mission FSM safety shell.
- Tests and documentation for the visual communication pipeline.

It is not the R1 F407 firmware repository. Firmware GPIO output lives in
Rscontrol2.

## Fixed six-led bit order

Do not change this order unless explicitly requested:

| LED | Bit | Hex |
|---|---:|---:|
| D0 | bit0 | 0x01 |
| D1 | bit1 | 0x02 |
| D2 | bit2 | 0x04 |
| REF | bit3 | 0x08 |
| SEQ | bit4 | 0x10 |
| PAR | bit5 | 0x20 |

Current code formats six-led `pattern` strings in LED order, D0 first and PAR
last:

```text
0   -> 0x00 -> 000000 -> all off
63  -> 0x3F -> 111111 -> all on
1   -> 0x01 -> 100000 -> D0
2   -> 0x02 -> 010000 -> D1
4   -> 0x04 -> 001000 -> D2
8   -> 0x08 -> 000100 -> REF
16  -> 0x10 -> 000010 -> SEQ
32  -> 0x20 -> 000001 -> PAR
```

If a task uses visual left-to-right notation instead, state the notation
explicitly before changing docs or tests.

## Supported serial protocols

`tools/sixled_serial_sequence.py` supports:

```text
--protocol ascii
--protocol rscontrol2
```

Default:

```text
ascii
```

ASCII protocol:

```text
send "63\n"
send "0\n"
send "1\n"
```

Used for older STM32F103 breadboard firmware.

Rscontrol2 protocol:

```text
bytes([0xBC, 0x00, mask & 0x3F, seq, 0x55])
```

Used for the Rscontrol2 F407 beacon frame.

Because the Rscontrol2 beacon timeout is 1000ms, use:

```bash
--hold-sec 5 --refresh-sec 0.2
```

## Core tools

```text
tools/hikrobot_6led_live.py
tools/sixled_log_summary.py
tools/sixled_serial_sequence.py
tools/sixled_expected_observed_check.py
```

## Common tests

On Ubuntu with ROS2 installed, use:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
```

On Windows:

```bash
python -m pytest -q
```

If Windows console encoding fails while printing help text, rerun with UTF-8
enabled:

```powershell
$env:PYTHONUTF8='1'; python -m pytest -q
```

Help checks:

```bash
python tools/hikrobot_6led_live.py --help
python tools/sixled_log_summary.py --help
python tools/sixled_serial_sequence.py --help
python tools/sixled_expected_observed_check.py --help
```

## Hardware validation rule

Do not claim real hardware success unless tested on Ubuntu with:

- Hikrobot camera.
- Real F407 or STM32 board.
- Real serial port.
- Real observed log.
- Expected-vs-observed checker output.

Mock, dry-run, replay, synthetic images, and unit tests are not real hardware
validation.

## Safety rules

1. Do not implement R1/R2 wireless communication unless explicitly requested.
2. Do not implement contact-based communication for the MC weapon assembly phase.
3. Do not let operator commands directly control R2.
4. Do not let operator commands directly set individual LEDs.
5. R1 operator commands must go through R1MissionFSM guards.
6. R2 must treat R1 beacon messages as event cues and must check local sensors before actions.
7. Vision messages must not directly drive dangerous actions.
8. R2 actions must go through R2MissionFSM guards.
9. Do not bypass FSM safety checks.
10. Do not connect ROS2, AprilTag, or real action loops unless explicitly requested.
11. Do not change mission semantics without tests and docs.
12. FSM output is ActionIntent only; never drive motors or hardware directly from FSM output.
13. ESTOP > ABORT > HOLD > ERROR > normal mission events.

## Do not commit

Do not commit:

```text
data/sixled/logs/*
data/sixled/frames/*
data/sixled/configs/breadboard_roi.json
build/
Debug/
Release/
*.elf
*.bin
*.hex
*.map
*.o
```

`.gitkeep` files and small artificial test fixtures are allowed.

## Windows / Ubuntu workflow

Windows:

- Code changes.
- Docs.
- Unit tests.
- Dry-run.
- Commit/tag/push.

Ubuntu:

- MVS SDK.
- Hikrobot camera.
- Serial hardware.
- F407 / STM32 real tests.
- Round 4B validation.

## Completion report format

Every task must report:

```text
1. remote
2. branch
3. commit hash
4. tag, if created
5. push status
6. modified files
7. pytest result
8. help command results
9. dry-run result if relevant
10. confirmation no logs/frames/ROI/build artifacts were committed
11. remaining hardware checks for the user
```

## Existing Project Notes

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
