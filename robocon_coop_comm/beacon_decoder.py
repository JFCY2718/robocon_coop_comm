"""Beacon decoder: extracts msg_id from beacon frames.

Uses the existing beacon_image.decode_virtual_beacon_image() for virtual frames.
Real hardware will replace the internal decode logic (AprilTag + ROI sampling)
while keeping the same BeaconDecoder interface.
"""

from __future__ import annotations

from .beacon_types import DecodedBeacon
from .beacon_types import BeaconFrame
from .beacon_types import msg_name_from_id


class BeaconDecoder:
    """Decode a BeaconFrame into a DecodedBeacon.

    This class does NOT call R2 FSM and does NOT make action decisions.
    It only extracts the visual signal.
    """

    def decode(self, frame: BeaconFrame) -> DecodedBeacon:
        """Decode a beacon frame.

        Args:
            frame: a BeaconFrame containing an image.

        Returns:
            DecodedBeacon with decoded fields.
        """
        from .beacon_image import decode_virtual_beacon_image

        try:
            protocol_decoded, confidence = decode_virtual_beacon_image(frame.image)
        except Exception as e:
            return DecodedBeacon(
                msg_id=0,
                msg_name=msg_name_from_id(0),
                seq=0,
                valid=False,
                confidence=0.0,
                source=frame.source,
                reason=f"decode_error: {e}",
            )

        return DecodedBeacon(
            msg_id=protocol_decoded.msg_id,
            msg_name=protocol_decoded.msg_name,
            seq=protocol_decoded.seq,
            valid=protocol_decoded.valid,
            confidence=confidence,
            source=frame.source,
            reason="" if protocol_decoded.valid else "parity_or_ref_failed",
            raw_bits=dict(protocol_decoded.bits),
        )
