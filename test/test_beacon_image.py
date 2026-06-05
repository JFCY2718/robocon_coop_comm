import pytest

from robocon_coop_comm.beacon_image import cv2, decode_virtual_beacon_image, draw_virtual_beacon
from robocon_coop_comm.protocol import MsgID


@pytest.mark.skipif(cv2 is None, reason="opencv not installed")
def test_virtual_beacon_image_round_trip():
    img = draw_virtual_beacon(MsgID.INSERT_ALLOWED, seq=1)
    decoded, confidence = decode_virtual_beacon_image(img)
    assert decoded.valid
    assert decoded.msg_id == MsgID.INSERT_ALLOWED
    assert decoded.seq == 1
    assert confidence > 0.5
