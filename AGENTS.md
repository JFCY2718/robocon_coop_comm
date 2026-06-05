# AI Coding Agent Instructions

Project: ROBOCON 2026 R1/R2 cooperative optical communication.

Hard constraints:

1. Do not implement R1/R2 wireless communication.
2. Do not implement contact-based communication for the MC weapon assembly phase.
3. Do not let operator commands directly control R2.
4. Do not let operator commands directly set individual LEDs.
5. R1 operator commands must go through R1MissionFSM guards.
6. R2 must treat R1 beacon messages as event cues and must check local sensors before actions.

Current milestone:

- Keep protocol.py, r1_fsm.py, r2_fsm.py hardware-independent.
- Keep tests passing with `pytest -q`.
- Prefer small, testable modules.
- Use Python 3.10 compatible syntax for Ubuntu 22.04.

Useful commands:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,vision]"
pytest -q
python -m robocon_coop_comm.demo_cli
python -m robocon_coop_comm.demo_cv
```

Next good tasks:

1. Add MCU serial frame encoder/decoder.
2. Add real AprilTag detection module while preserving the same DecodedBeacon output.
3. Replace JSON ROS topics with custom messages after protocol stabilizes.
