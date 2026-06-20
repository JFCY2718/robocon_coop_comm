"""Hikrobot camera frame provider for real 3-LED beacon detection.

Provides:
- HikrobotFrameProvider: BeaconFrameProvider implementation for Hikrobot cameras
- ThreeLedRoiDecoder: decode msg_id from 3 LED ROI brightness values, tracking SEQ
- roi_mean: sample mean brightness from an image ROI
- decode_3led_from_frame: extract raw D0/D1/D2 bits from a frame via ROI sampling

All Hikrobot SDK imports are lazy so the module can be imported without the SDK.
"""

from __future__ import annotations

import time

from .beacon_types import BeaconFrame, DecodedBeacon, msg_name_from_id
from .beacon_frame_provider import BeaconFrameProvider
from .protocol import even_parity

_LED_NAMES_3 = ("D0", "D1", "D2")


def _require_cv2():
    """Lazy-import cv2 and numpy; raises if not installed."""
    import cv2  # type: ignore

    return cv2


def _require_np():
    """Lazy-import numpy; raises if not installed."""
    import numpy as np  # type: ignore

    return np


# ---------------------------------------------------------------------------
# ROI helpers
# ---------------------------------------------------------------------------


def roi_mean(gray, x: int, y: int, size: int) -> float:
    """Sample mean brightness within a square ROI of ``size`` centred at (x, y).

    Args:
        gray: 2-D numpy array (grayscale image), or 3-D BGR image.
        x, y: centre pixel coordinates.
        size: side length of the sampling square.

    Returns:
        Mean pixel value in the ROI, or 0.0 if the ROI is empty.
    """
    np = _require_np()
    half = size // 2
    h, w = gray.shape[:2]
    x1 = max(0, x - half)
    x2 = min(w, x + half)
    y1 = max(0, y - half)
    y2 = min(h, y + half)
    roi = gray[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0
    if roi.ndim == 3:
        cv2 = _require_cv2()
        roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    return float(np.mean(roi))


def decode_3led_from_frame(
    frame: BeaconFrame,
    roi_points: list[tuple[int, int]],
    threshold: int = 120,
    roi_size: int = 24,
) -> dict[str, int]:
    """Extract raw D0/D1/D2 bits from a beacon frame via ROI sampling.

    Args:
        frame: BeaconFrame whose ``image`` is a numpy array (grayscale or BGR).
        roi_points: [(x0,y0), (x1,y1), (x2,y2)] for D0, D1, D2 centres.
        threshold: brightness threshold (0-255). Pixels above → bit=1.
        roi_size: square side length for sampling.

    Returns:
        Dict mapping LED name ("D0","D1","D2") to bit value (0 or 1).
    """
    gray = frame.image
    if gray.ndim == 3:
        cv2 = _require_cv2()
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)

    bits: dict[str, int] = {}
    brightness: dict[str, float] = {}
    for i, (x, y) in enumerate(roi_points):
        name = _LED_NAMES_3[i]
        b = roi_mean(gray, x, y, roi_size)
        bits[name] = 1 if b > threshold else 0
        brightness[name] = b
    return bits


# ---------------------------------------------------------------------------
# ThreeLedRoiDecoder
# ---------------------------------------------------------------------------


class ThreeLedRoiDecoder:
    """Decodes a 3-LED beacon frame into a vision-level ``DecodedBeacon``.

    Because the 3-LED hardware only exposes D0/D1/D2, this class:

    * samples brightness at three user-supplied ROI positions,
    * computes ``msg_id`` from D0-D2,
    * tracks ``SEQ`` by toggling whenever ``msg_id`` changes (emulating R1's
      event-driven toggle),
    * sets ``D3=0, D4=0`` (3-LED mode limits msg_id to 0-7),
    * computes ``PAR`` from the full 8-bit word,
    * sets ``REF=1`` (synthesised), and
    * passes the result through ``protocol.decode_led_bits`` for validation.

    The output ``DecodedBeacon`` is fully compatible with the existing
    ``BeaconStabilizer`` → ``R2MissionFSM`` pipeline.
    """

    def __init__(self, threshold: int = 120, roi_size: int = 24) -> None:
        self.threshold = threshold
        self.roi_size = roi_size
        self._last_msg_id: int | None = None
        self._seq: int = 0

    def decode(
        self, frame: BeaconFrame, roi_points: list[tuple[int, int]]
    ) -> DecodedBeacon:
        """Decode one frame using 3-LED ROI sampling.

        Args:
            frame: BeaconFrame with ``image`` as numpy array.
            roi_points: [(x0,y0), (x1,y1), (x2,y2)] for D0, D1, D2.

        Returns:
            Vision-level DecodedBeacon.
        """
        bits_3 = decode_3led_from_frame(
            frame, roi_points, self.threshold, self.roi_size
        )

        msg_id = bits_3["D0"] | (bits_3["D1"] << 1) | (bits_3["D2"] << 2)

        # Track SEQ: toggle when msg_id changes (mimics R1 event toggle).
        # On the very first frame, initialise without toggling.
        if self._last_msg_id is None:
            self._last_msg_id = msg_id
        elif msg_id != self._last_msg_id:
            self._seq ^= 1
            self._last_msg_id = msg_id

        # Build full 8-bit dict for protocol.decode_led_bits validation.
        d0, d1, d2 = bits_3["D0"], bits_3["D1"], bits_3["D2"]
        full_bits = {
            "REF": 1,  # synthesised
            "D0": d0,
            "D1": d1,
            "D2": d2,
            "D3": 0,
            "D4": 0,
            "SEQ": self._seq,
            "PAR": even_parity(d0, d1, d2, 0, 0, self._seq),
        }

        # Validate via protocol decoder.
        from .protocol import decode_led_bits

        try:
            protocol_decoded = decode_led_bits(full_bits)
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

        # Confidence: crude but useful — proportion of bright samples near threshold.
        # Here we use a simple heuristic based on msg_id validity.
        confidence = 1.0 if protocol_decoded.valid else 0.3

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

    def reset_seq(self) -> None:
        """Reset SEQ tracking (e.g. after re-connecting camera)."""
        self._last_msg_id = None
        self._seq = 0


# ---------------------------------------------------------------------------
# HikrobotFrameProvider
# ---------------------------------------------------------------------------


class HikrobotFrameProvider(BeaconFrameProvider):
    """Real Hikrobot camera frame provider.

    Opens the first available Hikrobot USB/GigE camera and provides frames
    as ``BeaconFrame`` objects.  All Hikrobot SDK imports are lazy so the
    module can be imported without the SDK installed.

    Usage::

        provider = HikrobotFrameProvider()
        try:
            while True:
                frame = provider.get_frame()
                if frame is not None:
                    process(frame)
        finally:
            provider.close()
    """

    def __init__(
        self,
        exposure_time: float = 10000.0,
        gain: float = 5.0,
        timeout_ms: int = 1000,
    ) -> None:
        self._exposure_time = exposure_time
        self._gain = gain
        self._timeout_ms = timeout_ms
        self._cam = None
        self._payload_size: int = 0
        self._frame_id: int = 0

    # ------------------------------------------------------------------
    # camera lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the first Hikrobot camera and start grabbing."""
        if self._cam is not None:
            return

        import ctypes

        try:
            from MvCameraControl_class import (  # type: ignore
                MvCamera,
                MV_ACCESS_Exclusive,
                MV_CC_DEVICE_INFO,
                MV_CC_DEVICE_INFO_LIST,
                MV_FRAME_OUT_INFO_EX,
                MV_GIGE_DEVICE,
                MV_USB_DEVICE,
                MVCC_INTVALUE,
            )
        except ImportError as exc:
            raise RuntimeError(
                "Hikrobot MVS SDK not found.  Ensure MvCameraControl_class is on PYTHONPATH.\n"
                "Typical setup:\n"
                "  export MVCAM_COMMON_RUNENV=/opt/MVS/lib\n"
                "  export PYTHONPATH=/opt/MVS/Samples/64/Python/MvImport:$PYTHONPATH\n"
                "  export LD_LIBRARY_PATH=/opt/MVS/lib/64:/opt/MVS/bin:$LD_LIBRARY_PATH"
            ) from exc

        self._MvCamera = MvCamera
        self._ctypes = ctypes
        self._MV_FRAME_OUT_INFO_EX = MV_FRAME_OUT_INFO_EX

        # --- enumerate ---
        device_list = MV_CC_DEVICE_INFO_LIST()
        tlayer_type = MV_GIGE_DEVICE | MV_USB_DEVICE
        ret = MvCamera.MV_CC_EnumDevices(tlayer_type, device_list)
        self._check_ret(ret, "MV_CC_EnumDevices")
        if device_list.nDeviceNum == 0:
            raise RuntimeError("No Hikrobot camera found.")

        # --- pick first device ---
        dev_info = ctypes.cast(
            device_list.pDeviceInfo[0],
            ctypes.POINTER(MV_CC_DEVICE_INFO),
        ).contents

        cam = MvCamera()
        ret = cam.MV_CC_CreateHandle(dev_info)
        self._check_ret(ret, "MV_CC_CreateHandle")
        ret = cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
        self._check_ret(ret, "MV_CC_OpenDevice")

        # --- configure ---
        cam.MV_CC_SetEnumValue("TriggerMode", 0)  # continuous
        cam.MV_CC_SetFloatValue("ExposureTime", self._exposure_time)
        cam.MV_CC_SetFloatValue("Gain", self._gain)

        ret = cam.MV_CC_StartGrabbing()
        self._check_ret(ret, "MV_CC_StartGrabbing")

        # --- payload size ---
        st_param = MVCC_INTVALUE()
        ctypes.memset(ctypes.byref(st_param), 0, ctypes.sizeof(MVCC_INTVALUE))
        ret = cam.MV_CC_GetIntValue("PayloadSize", st_param)
        self._check_ret(ret, "MV_CC_GetIntValue(PayloadSize)")

        self._cam = cam
        self._payload_size = int(st_param.nCurValue)

    def close(self) -> None:
        """Stop grabbing and release the camera."""
        cam = self._cam
        if cam is None:
            return
        try:
            cam.MV_CC_StopGrabbing()
        except Exception:
            pass
        try:
            cam.MV_CC_CloseDevice()
        except Exception:
            pass
        try:
            cam.MV_CC_DestroyHandle()
        except Exception:
            pass
        self._cam = None
        self._payload_size = 0

    @property
    def is_open(self) -> bool:
        return self._cam is not None

    # ------------------------------------------------------------------
    # BeaconFrameProvider interface
    # ------------------------------------------------------------------

    def get_frame(self) -> BeaconFrame | None:
        """Grab one frame from the camera.

        Returns:
            BeaconFrame with grayscale image, or None if grab timed out.
        """
        if self._cam is None:
            self.open()

        ctypes = self._ctypes
        cam = self._cam
        payload_size = self._payload_size
        FrameInfo = self._MV_FRAME_OUT_INFO_EX

        data_buf = (ctypes.c_ubyte * payload_size)()
        frame_info = FrameInfo()
        ctypes.memset(
            ctypes.byref(frame_info), 0, ctypes.sizeof(FrameInfo)
        )

        ret = cam.MV_CC_GetOneFrameTimeout(
            data_buf, payload_size, frame_info, self._timeout_ms
        )
        if ret != 0:
            return None

        width = int(frame_info.nWidth)
        height = int(frame_info.nHeight)
        frame_len = int(frame_info.nFrameLen)

        if width <= 0 or height <= 0 or frame_len <= 0:
            return None

        np = _require_np()
        raw = np.frombuffer(data_buf, dtype=np.uint8, count=min(frame_len, payload_size))

        need = width * height
        if raw.size < need:
            return None

        gray = raw[:need].reshape((height, width)).copy()
        frame = BeaconFrame(
            image=gray,
            source="hikrobot_camera",
            frame_id=self._frame_id,
            timestamp=time.time(),
        )
        self._frame_id += 1
        return frame

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_ret(ret: int, name: str) -> None:
        if ret != 0:
            raise RuntimeError(f"{name} failed, ret=0x{ret:x}")
