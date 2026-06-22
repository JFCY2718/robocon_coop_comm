#!/usr/bin/env python3
"""FSM safety simulation demo — no real hardware, no real motors.

Exercises R1MissionFSM and R2MissionFSM through key safety scenarios:
- Normal flow: START → MC assembly → MF
- ESTOP / local_estop override
- HOLD / ABORT / ERROR safety gates
- Invalid / unknown / low-confidence / stale beacons
- RETRY_RESET recovery
- Duplicate seq debounce

Usage:
    python -m robocon_coop_comm.demo_fsm_safety
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass

from .beacon_types import BeaconEvent
from .protocol import MsgID, DecodedBeacon
from .r1_fsm import OperatorCommand, R1MissionFSM, R1Sensors, R1State
from .r2_fsm import R2MissionFSM, R2Sensors, R2State


# ---------------------------------------------------------------------------
# scenario runner
# ---------------------------------------------------------------------------


@dataclass
class ScenarioResult:
    name: str
    passed: bool
    detail: str


_PASS = 0
_FAIL = 0


def _ok(name: str, detail: str = "") -> ScenarioResult:
    global _PASS
    _PASS += 1
    return ScenarioResult(name, True, detail)


def _fail(name: str, detail: str = "") -> ScenarioResult:
    global _FAIL
    _FAIL += 1
    return ScenarioResult(name, False, detail)


# ---------------------------------------------------------------------------
# R1 scenarios
# ---------------------------------------------------------------------------


def _r1_normal_flow() -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    fsm = R1MissionFSM()
    sensors = R1Sensors(
        rod_clamped=True, in_assembly_pose=True,
        rod_pose_locked=True, chassis_stopped=True,
        weapon_locked=True, r1_clear_mc=True, r1_in_mf=True,
    )

    fsm.update(OperatorCommand.START, sensors)
    out = fsm.update(OperatorCommand.NEXT, sensors)
    if out.state == R1State.ROD_CLAMPED:
        results.append(_ok("R1 START→PICK_ROD→ROD_CLAMPED"))
    else:
        results.append(_fail("R1 START→PICK_ROD→ROD_CLAMPED", f"got {out.state}"))

    out = fsm.update(OperatorCommand.NEXT, sensors)
    if out.state == R1State.AT_ASSEMBLY_POSE:
        results.append(_ok("R1 ROD_CLAMPED→AT_ASSEMBLY_POSE"))
    else:
        results.append(_fail("R1 ROD_CLAMPED→AT_ASSEMBLY_POSE", f"got {out.state}"))

    out = fsm.update(OperatorCommand.NEXT, sensors)
    if out.state == R1State.INSERT_ALLOWED:
        results.append(_ok("R1 AT_ASSEMBLY_POSE→INSERT_ALLOWED"))
    else:
        results.append(_fail("R1 AT_ASSEMBLY_POSE→INSERT_ALLOWED", f"got {out.state}"))

    out = fsm.update(OperatorCommand.NEXT, sensors)
    if out.state == R1State.WEAPON_LOCKED:
        results.append(_ok("R1 INSERT_ALLOWED→WEAPON_LOCKED"))
    else:
        results.append(_fail("R1 INSERT_ALLOWED→WEAPON_LOCKED", f"got {out.state}"))

    out = fsm.update(OperatorCommand.NEXT, sensors)
    if out.state == R1State.R1_CLEAR_MC:
        results.append(_ok("R1 WEAPON_LOCKED→R1_CLEAR_MC"))
    else:
        results.append(_fail("R1 WEAPON_LOCKED→R1_CLEAR_MC", f"got {out.state}"))

    out = fsm.update(OperatorCommand.NEXT, sensors)
    if out.state == R1State.R1_IN_MF:
        results.append(_ok("R1 R1_CLEAR_MC→R1_IN_MF"))
    else:
        results.append(_fail("R1 R1_CLEAR_MC→R1_IN_MF", f"got {out.state}"))

    return results


def _r1_estop_override() -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    fsm = R1MissionFSM()
    sensors = _sensors_r1(estop=True)
    out = fsm.update(OperatorCommand.NEXT, sensors)
    if out.state == R1State.ERROR and out.msg_id == MsgID.ERROR:
        results.append(_ok("R1 ESTOP→ERROR"))
    else:
        results.append(_fail("R1 ESTOP→ERROR", f"got {out.state}"))
    return results


def _r1_local_estop() -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    fsm = _fsm_at_r1(R1State.INSERT_ALLOWED)
    sensors = _sensors_r1(local_estop=True)
    out = fsm.update(OperatorCommand.NEXT, sensors)
    if out.reason == "local_estop":
        results.append(_ok("R1 local_estop override"))
    else:
        results.append(_fail("R1 local_estop override", f"reason={out.reason}"))
    return results


def _r1_hold_gate() -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    fsm = R1MissionFSM()
    fsm.update(OperatorCommand.HOLD, R1Sensors())
    out = fsm.update(OperatorCommand.NEXT, _sensors_r1(rod_clamped=True))
    if out.reason == "hold_requires_reset":
        results.append(_ok("R1 HOLD blocks NEXT"))
    else:
        results.append(_fail("R1 HOLD blocks NEXT", f"reason={out.reason}"))
    return results


def _r1_abort_gate() -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    fsm = R1MissionFSM()
    fsm.update(OperatorCommand.ABORT, R1Sensors())
    if fsm.state != R1State.ABORT:
        results.append(_fail("R1 ABORT sets ABORT state", f"got {fsm.state}"))
        return results
    out = fsm.update(OperatorCommand.NEXT, _sensors_r1(rod_clamped=True))
    if out.reason == "abort_requires_retry":
        results.append(_ok("R1 ABORT blocks NEXT"))
    else:
        results.append(_fail("R1 ABORT blocks NEXT", f"reason={out.reason}"))

    fsm.update(OperatorCommand.RETRY, R1Sensors())
    if fsm.state == R1State.WAIT_START:
        results.append(_ok("R1 RETRY from ABORT→WAIT_START"))
    else:
        results.append(_fail("R1 RETRY from ABORT", f"got {fsm.state}"))
    return results


# ---------------------------------------------------------------------------
# R2 scenarios
# ---------------------------------------------------------------------------


def _r2_normal_flow() -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    fsm = R2MissionFSM()
    sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)

    out = fsm.update(_b(MsgID.R1_ROD_CLAMPED, 0), sensors)
    if out.state == R2State.PREPARE_HEAD:
        results.append(_ok("R2 R1_ROD_CLAMPED→PREPARE_HEAD"))
    else:
        results.append(_fail("R2 R1_ROD_CLAMPED→PREPARE_HEAD", f"got {out.state}"))

    out = fsm.update(_b(MsgID.R1_AT_ASSEMBLY_POSE, 1), sensors)
    if out.state == R2State.SEARCH_R1_TAG:
        results.append(_ok("R2 PREPARE_HEAD→SEARCH_R1_TAG"))
    else:
        results.append(_fail("R2 PREPARE_HEAD→SEARCH_R1_TAG", f"got {out.state}"))

    out = fsm.update(_b(MsgID.INSERT_ALLOWED, 0), sensors)
    if out.state == R2State.INSERTING:
        results.append(_ok("R2 SEARCH_R1_TAG→INSERTING"))
    else:
        results.append(_fail("R2 SEARCH_R1_TAG→INSERTING", f"got {out.state}"))

    sensors.insertion_motion_done = True
    out = fsm.update(_b(MsgID.WEAPON_LOCKED, 1), sensors)
    if out.state == R2State.HEAD_RELEASED:
        results.append(_ok("R2 INSERTING→HEAD_RELEASED"))
    else:
        results.append(_fail("R2 INSERTING→HEAD_RELEASED", f"got {out.state}"))

    out = fsm.update(_b(MsgID.R1_CLEAR_MC, 0), sensors)
    if out.state == R2State.READY_TO_LEAVE_MC:
        results.append(_ok("R2 HEAD_RELEASED→READY_TO_LEAVE_MC"))
    else:
        results.append(_fail("R2 HEAD_RELEASED→READY_TO_LEAVE_MC", f"got {out.state}"))

    out = fsm.update(_b(MsgID.R1_IN_MF, 1), sensors)
    if out.state == R2State.READY_TO_ENTER_MF:
        results.append(_ok("R2 READY_TO_LEAVE_MC→READY_TO_ENTER_MF"))
    else:
        results.append(_fail("R2 READY_TO_LEAVE_MC→READY_TO_ENTER_MF", f"got {out.state}"))

    return results


def _r2_estop_override() -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    fsm = R2MissionFSM()
    sensors = R2Sensors(estop=True)
    out = fsm.update(_b(MsgID.INSERT_ALLOWED, 0), sensors)
    if out.reason == "estop" and fsm.state == R2State.ERROR:
        results.append(_ok("R2 ESTOP override"))
    else:
        results.append(_fail("R2 ESTOP override", f"reason={out.reason}"))
    return results


def _r2_local_estop() -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    fsm = _fsm_at_r2(R2State.INSERTING)
    sensors = R2Sensors(local_estop=True)
    out = fsm.update(_b(MsgID.INSERT_ALLOWED, 0), sensors)
    if out.reason == "local_estop":
        results.append(_ok("R2 local_estop override"))
    else:
        results.append(_fail("R2 local_estop override", f"reason={out.reason}"))
    return results


def _r2_hold_gate() -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    fsm = R2MissionFSM()
    fsm.update(_b(MsgID.HOLD, 0), R2Sensors())
    sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
    out = fsm.update(_b(MsgID.INSERT_ALLOWED, 1), sensors)
    if out.action_hint == "hold_active":
        results.append(_ok("R2 HOLD safety gate blocks INSERT_ALLOWED"))
    else:
        results.append(_fail("R2 HOLD safety gate", f"action={out.action_hint}"))
    return results


def _r2_invalid_beacon() -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    fsm = R2MissionFSM()
    invalid = _b_invalid()
    out = fsm.update(invalid, R2Sensors())
    if out.action_hint == "ignore" and "invalid" in out.reason:
        results.append(_ok("R2 invalid beacon ignored"))
    else:
        results.append(_fail("R2 invalid beacon", f"action={out.action_hint}"))
    return results


def _r2_unknown_msg() -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    fsm = R2MissionFSM()
    unknown = DecodedBeacon(msg_id=99, seq=0, valid=True, bits={})
    out = fsm.update(unknown, R2Sensors())
    if out.action_hint == "ignore" and "unknown" in out.reason:
        results.append(_ok("R2 unknown msg ignored"))
    else:
        results.append(_fail("R2 unknown msg", f"action={out.action_hint}"))
    return results


def _r2_low_confidence() -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    fsm = R2MissionFSM(min_confidence=0.7)

    class _LowBeacon:
        valid = True
        msg_id = MsgID.R1_ROD_CLAMPED
        seq = 0
        confidence = 0.3
        timestamp = None

    out = fsm.update(_LowBeacon(), R2Sensors())
    if out.action_hint == "ignore" and out.reason == "low_confidence":
        results.append(_ok("R2 low confidence ignored"))
    else:
        results.append(_fail("R2 low confidence", f"action={out.action_hint}"))
    return results


def _r2_stale_beacon() -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    fsm = R2MissionFSM(max_age_s=2.0)

    class _StaleBeacon:
        valid = True
        msg_id = MsgID.R1_ROD_CLAMPED
        seq = 0
        confidence = 0.9
        timestamp = 0.0

    out = fsm.update(_StaleBeacon(), R2Sensors())
    if out.action_hint == "ignore" and out.reason == "stale_beacon":
        results.append(_ok("R2 stale beacon ignored"))
    else:
        results.append(_fail("R2 stale beacon", f"action={out.action_hint}"))
    return results


def _r2_retry_reset() -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    fsm = _fsm_at_r2(R2State.HOLD)
    out = fsm.update(_b(MsgID.RETRY_RESET, 0), R2Sensors())
    if fsm.state == R2State.WAIT_R1:
        results.append(_ok("R2 RETRY_RESET from HOLD"))
    else:
        results.append(_fail("R2 RETRY_RESET from HOLD", f"got {fsm.state}"))
    return results


def _r2_duplicate_seq() -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)
    fsm = R2MissionFSM()
    fsm.update(_b(MsgID.INSERT_ALLOWED, 0), sensors)  # first time → INSERTING
    out = fsm.update(_b(MsgID.INSERT_ALLOWED, 0), sensors)  # same seq → continue
    if out.action_hint == "continue_insert":
        results.append(_ok("R2 duplicate seq debounce"))
    else:
        results.append(_fail("R2 duplicate seq debounce", f"action={out.action_hint}"))
    return results


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _sensors_r1(**kwargs: bool) -> R1Sensors:
    defaults: dict[str, bool] = {
        "rod_clamped": False, "in_assembly_pose": False,
        "rod_pose_locked": False, "chassis_stopped": False,
        "weapon_locked": False, "r1_clear_mc": False, "r1_in_mf": False,
        "estop": False, "local_estop": False,
    }
    defaults.update(kwargs)
    return R1Sensors(**defaults)


def _fsm_at_r1(state: R1State) -> R1MissionFSM:
    fsm = R1MissionFSM()
    fsm.state = state
    return fsm


def _fsm_at_r2(state: R2State) -> R2MissionFSM:
    fsm = R2MissionFSM()
    fsm.state = state
    return fsm


def _b(msg_id: int, seq: int = 0) -> DecodedBeacon:
    """Build a valid protocol DecodedBeacon."""
    from .protocol import decode_led_bits, encode_led_bits
    return decode_led_bits(encode_led_bits(msg_id, seq).bits)


def _b_invalid() -> DecodedBeacon:
    from .protocol import decode_led_bits
    return decode_led_bits({"REF": 0, "D0": 0, "D1": 0, "D2": 0, "D3": 0, "D4": 0, "SEQ": 0, "PAR": 0})


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    global _PASS, _FAIL
    _PASS = 0
    _FAIL = 0

    all_scenarios: list[tuple[str, callable]] = [
        # R1
        ("R1 — Normal flow", _r1_normal_flow),
        ("R1 — ESTOP override", _r1_estop_override),
        ("R1 — local_estop", _r1_local_estop),
        ("R1 — HOLD safety gate", _r1_hold_gate),
        ("R1 — ABORT safety gate + RETRY", _r1_abort_gate),
        # R2
        ("R2 — Normal flow", _r2_normal_flow),
        ("R2 — ESTOP override", _r2_estop_override),
        ("R2 — local_estop", _r2_local_estop),
        ("R2 — HOLD safety gate", _r2_hold_gate),
        ("R2 — Invalid beacon ignored", _r2_invalid_beacon),
        ("R2 — Unknown msg ignored", _r2_unknown_msg),
        ("R2 — Low confidence ignored", _r2_low_confidence),
        ("R2 — Stale beacon ignored", _r2_stale_beacon),
        ("R2 — RETRY_RESET recovery", _r2_retry_reset),
        ("R2 — Duplicate seq debounce", _r2_duplicate_seq),
    ]

    print("=" * 60)
    print("  ROBOCON 2026 — FSM Safety Simulation Demo")
    print("  NO real hardware. NO real motors. Software-only.")
    print("=" * 60)

    for title, fn in all_scenarios:
        print(f"\n── {title} ──")
        try:
            results = fn()
            for r in results:
                status = "✅" if r.passed else "❌"
                line = f"  {status} {r.name}"
                if r.detail and not r.passed:
                    line += f"  ({r.detail})"
                print(line)
        except Exception:
            print(f"  ❌ EXCEPTION: {traceback.format_exc()}")
            _FAIL += 1

    print(f"\n{'=' * 60}")
    total = _PASS + _FAIL
    print(f"  Results: {_PASS} passed, {_FAIL} failed, {total} total")
    print("=" * 60)

    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
