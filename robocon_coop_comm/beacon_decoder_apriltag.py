"""AprilTag-guided beacon decoder.

Uses AprilTag detection + homography-based LED ROI projection to decode
3-LED optical beacons from real camera frames.

This is the real-hardware counterpart to ``beacon_decoder.BeaconDecoder``
(which uses the virtual beacon path).  They share the same return type
(``DecodedBeacon``) so both feed into the same downstream pipeline::

    camera → AprilTag detection → ROI projection → LED sampling → DecodedBeacon
                                                                       ↓
                                                            BeaconStabilizer
                                                                       ↓
                                                               R2MissionFSM

Usage::

    from robocon_coop_comm.apriltag_detector import ApriltagDetector
    from robocon_coop_comm.apriltag_roi_mapper import AprilTagRoiMapper
    from robocon_coop_comm.beacon_decoder_apriltag import AprilTagBeaconDecoder

    detector = ApriltagDetector(families="tag36h11")
    mapper = AprilTagRoiMapper.for_3led_below(tag_size_mm=100.0)
    decoder = AprilTagBeaconDecoder(detector, mapper, target_tag_id=0)

    frame = provider.get_frame()
    result = decoder.decode(frame)  # → DecodedBeacon

This module does NOT depend on Hikrobot SDK or ROS2.  It only requires
``pupil-apriltags`` and ``opencv-python`` at decode time (both are lazy).
"""

from __future__ import annotations

from .beacon_types import BeaconFrame, DecodedBeacon, msg_name_from_id
from .hikrobot_frame_provider import roi_mean


class AprilTagBeaconDecoder:
    """Decode 3-LED beacon state via AprilTag-guided ROI sampling.

    Detection pipeline (per frame):
    1. Detect AprilTags → list of ``TagDetection``.
    2. Filter by ``target_tag_id`` (if set).
    3. For the best-matching tag, use ``AprilTagRoiMapper`` to project LED
       positions from the physical tag coordinate system into image pixel coords.
    4. Sample each LED ROI brightness with ``roi_mean``.
    5. Threshold brightness → D0/D1/D2 bits → msg_id (0-7).
    6. Track SEQ toggle when msg_id changes.
    7. Return a ``DecodedBeacon`` compatible with the existing pipeline.

    Args:
        detector: Configured ``ApriltagDetector`` instance.
        mapper: Configured ``AprilTagRoiMapper`` instance (defines LED positions
            and the tag→image coordinate mapping).
        target_tag_id: If set, only decode from tags with this ID.
        threshold: Brightness threshold (0-255).  ROI mean above → LED ON.
    """

    def __init__(
        self,
        detector,
        mapper,
        target_tag_id: int | None = 0,
        threshold: int = 120,
    ) -> None:
        self._detector = detector
        self._mapper = mapper
        self._target_tag_id = target_tag_id
        self._threshold = int(threshold)

        # Internal SEQ tracking (toggles when msg_id changes).
        self._last_msg_id: int | None = None
        self._seq: int = 0

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    def decode(self, frame: BeaconFrame) -> DecodedBeacon:
        """Decode a single camera frame.

        Args:
            frame: ``BeaconFrame`` whose ``image`` is a numpy array
                (grayscale or BGR).

        Returns:
            ``DecodedBeacon``.  If no tag is found or the tag is not the
            expected one, ``valid`` will be ``False`` and ``reason`` will
            explain why.
        """
        image = frame.image
        if image is None:
            return self._no_result("null_image")

        # 1. Detect AprilTags.
        try:
            detections = self._detector.detect(image)
        except Exception as exc:
            return self._no_result(f"apriltag_detect_error: {exc}")

        if not detections:
            return self._no_result("no_tag_detected")

        # 2. Filter / select best tag.
        if self._target_tag_id is not None:
            matching = [d for d in detections if d.tag_id == self._target_tag_id]
            if not matching:
                return self._no_result(
                    f"tag_id_mismatch: wanted {self._target_tag_id}, "
                    f"got {[d.tag_id for d in detections]}"
                )
            # Pick the one with highest decision margin.
            best = max(matching, key=lambda d: d.decision_margin)
        else:
            best = max(detections, key=lambda d: d.decision_margin)

        h, w = image.shape[:2]

        # 3. Project LED ROIs via homography.
        try:
            roi_points, homography = self._mapper.map_rois(
                best.corners, image_shape=(h, w)
            )
        except Exception as exc:
            return self._no_result(f"roi_projection_error: {exc}")

        if not roi_points:
            return self._no_result("homography_failed")

        # 4. Sample LED brightness.
        brightness: dict[str, float] = {}
        for rp in roi_points:
            b = roi_mean(image, rp.x_px, rp.y_px, rp.radius_px * 2)
            brightness[rp.name] = b

        # 5. Threshold → bits → msg_id.
        bits = {
            name: (1 if brightness.get(name, 0.0) > self._threshold else 0)
            for name in ("D0", "D1", "D2")
        }
        d0, d1, d2 = bits["D0"], bits["D1"], bits["D2"]
        msg_id = d0 | (d1 << 1) | (d2 << 2)

        # 6. SEQ tracking.
        if self._last_msg_id is None:
            self._last_msg_id = msg_id
        elif msg_id != self._last_msg_id:
            self._seq ^= 1
            self._last_msg_id = msg_id

        # 7. Build full 8-bit word for protocol validation.
        from .protocol import decode_led_bits, even_parity

        full_bits = {
            "REF": 1,  # synthesised (always-on reference assumption)
            "D0": d0,
            "D1": d1,
            "D2": d2,
            "D3": 0,
            "D4": 0,
            "SEQ": self._seq,
            "PAR": even_parity(d0, d1, d2, 0, 0, self._seq),
        }

        try:
            proto = decode_led_bits(full_bits)
        except ValueError:
            return DecodedBeacon(
                msg_id=msg_id,
                msg_name=msg_name_from_id(msg_id),
                seq=self._seq,
                valid=False,
                confidence=0.0,
                source=frame.source,
                reason="protocol_decode_error",
            )

        # Confidence heuristic: based on how far the brightness values are
        # from the threshold (the further, the more confident).
        margins = [abs(brightness.get(n, 0.0) - self._threshold) for n in ("D0", "D1", "D2")]
        avg_margin = sum(margins) / max(len(margins), 1)
        # Normalise to [0, 1]: margin of 0 → 0.0, margin of 100 → 1.0.
        confidence = min(1.0, max(0.0, avg_margin / 100.0))

        return DecodedBeacon(
            msg_id=proto.msg_id,
            msg_name=proto.msg_name,
            seq=proto.seq,
            valid=proto.valid,
            confidence=round(confidence, 4),
            source=frame.source,
            reason="" if proto.valid else "parity_or_ref_failed",
            raw_bits=dict(proto.bits),
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def reset_seq(self) -> None:
        """Reset the internal SEQ tracker (e.g. after camera reconnect)."""
        self._last_msg_id = None
        self._seq = 0

    def _no_result(self, reason: str) -> DecodedBeacon:
        return DecodedBeacon(
            msg_id=0,
            msg_name=msg_name_from_id(0),
            seq=self._seq,
            valid=False,
            confidence=0.0,
            source="apriltag_decoder",
            reason=reason,
        )
