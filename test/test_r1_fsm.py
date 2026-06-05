from robocon_coop_comm.protocol import MsgID
from robocon_coop_comm.r1_fsm import OperatorCommand, R1MissionFSM, R1Sensors, R1State


def test_insert_allowed_is_guarded_by_sensors():
    fsm = R1MissionFSM()
    sensors = R1Sensors()

    fsm.update(OperatorCommand.START, sensors)
    out = fsm.update(OperatorCommand.NEXT, sensors)
    assert out.msg_id == MsgID.HOLD
    assert fsm.state == R1State.PICK_ROD

    sensors.rod_clamped = True
    out = fsm.update(OperatorCommand.NEXT, sensors)
    assert out.state == R1State.ROD_CLAMPED
    assert out.msg_id == MsgID.R1_ROD_CLAMPED

    sensors.in_assembly_pose = True
    out = fsm.update(OperatorCommand.NEXT, sensors)
    assert out.state == R1State.AT_ASSEMBLY_POSE
    assert out.msg_id == MsgID.R1_AT_ASSEMBLY_POSE

    # Missing pose lock and chassis stop; must not allow insertion.
    out = fsm.update(OperatorCommand.NEXT, sensors)
    assert out.msg_id == MsgID.HOLD
    assert fsm.state == R1State.AT_ASSEMBLY_POSE

    sensors.rod_pose_locked = True
    sensors.chassis_stopped = True
    out = fsm.update(OperatorCommand.NEXT, sensors)
    assert out.state == R1State.INSERT_ALLOWED
    assert out.msg_id == MsgID.INSERT_ALLOWED


def test_full_mc_to_mf_sequence():
    fsm = R1MissionFSM()
    sensors = R1Sensors(
        rod_clamped=True,
        in_assembly_pose=True,
        rod_pose_locked=True,
        chassis_stopped=True,
        weapon_locked=True,
        r1_clear_mc=True,
        r1_in_mf=True,
    )

    fsm.update(OperatorCommand.START, sensors)
    assert fsm.update(OperatorCommand.NEXT, sensors).msg_id == MsgID.R1_ROD_CLAMPED
    assert fsm.update(OperatorCommand.NEXT, sensors).msg_id == MsgID.R1_AT_ASSEMBLY_POSE
    assert fsm.update(OperatorCommand.NEXT, sensors).msg_id == MsgID.INSERT_ALLOWED
    assert fsm.update(OperatorCommand.NEXT, sensors).msg_id == MsgID.WEAPON_LOCKED
    assert fsm.update(OperatorCommand.NEXT, sensors).msg_id == MsgID.R1_CLEAR_MC
    assert fsm.update(OperatorCommand.NEXT, sensors).msg_id == MsgID.R1_IN_MF


def test_estop_forces_error():
    fsm = R1MissionFSM()
    out = fsm.update(OperatorCommand.NEXT, R1Sensors(estop=True))
    assert out.state == R1State.ERROR
    assert out.msg_id == MsgID.ERROR
