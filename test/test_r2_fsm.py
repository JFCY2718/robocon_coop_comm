from robocon_coop_comm.protocol import MsgID, decode_led_bits, encode_led_bits
from robocon_coop_comm.r2_fsm import R2MissionFSM, R2Sensors, R2State


def beacon(msg_id, seq=0):
    return decode_led_bits(encode_led_bits(msg_id, seq).bits)


def test_r2_only_inserts_when_local_ready():
    fsm = R2MissionFSM()
    sensors = R2Sensors(head_grabbed=False, r1_tag_visible=True, pre_insert_pose_ok=True)
    out = fsm.update(beacon(MsgID.INSERT_ALLOWED), sensors)
    assert fsm.state != R2State.INSERTING
    assert out.action_hint == "wait_local_ready"

    sensors.head_grabbed = True
    out = fsm.update(beacon(MsgID.INSERT_ALLOWED, seq=1), sensors)
    assert fsm.state == R2State.INSERTING
    assert out.action_hint == "insert_head"


def test_r2_sequence_to_enter_mf_ready():
    fsm = R2MissionFSM()
    sensors = R2Sensors(head_grabbed=True, r1_tag_visible=True, pre_insert_pose_ok=True)

    assert fsm.update(beacon(MsgID.R1_ROD_CLAMPED), sensors).action_hint == "grab_head"
    assert fsm.update(beacon(MsgID.R1_AT_ASSEMBLY_POSE, 1), sensors).action_hint == "search_r1_tag"
    assert fsm.update(beacon(MsgID.INSERT_ALLOWED, 0), sensors).action_hint == "insert_head"

    sensors.insertion_motion_done = True
    assert fsm.update(beacon(MsgID.WEAPON_LOCKED, 1), sensors).action_hint == "release_head_and_retreat"
    assert fsm.update(beacon(MsgID.R1_CLEAR_MC, 0), sensors).action_hint == "leave_mc"
    assert fsm.update(beacon(MsgID.R1_IN_MF, 1), sensors).action_hint == "enter_mf"
    assert fsm.state == R2State.READY_TO_ENTER_MF
