"""Virtual LED beacon rendering and fixed-ROI decoding.

This module is intentionally independent from ROS. It is useful before hardware exists:
R1 FSM -> protocol bits -> generated beacon image -> R2 decoder.

When real hardware arrives, keep the protocol and replace fixed ROI decoding with:
AprilTag detection -> perspective transform -> same LED ROI sampling.
"""

from __future__ import annotations

from dataclasses import dataclass

from .protocol import LED_NAMES, DecodedBeacon, decode_led_bits, encode_led_bits

try:  # Optional dependency for non-vision unit tests.
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - tested only when vision dependencies are installed.
    cv2 = None
    np = None


@dataclass(frozen=True)
class BeaconLayout:
    width: int = 720
    height: int = 480
    board_left: int = 130
    board_top: int = 45
    board_right: int = 590
    board_bottom: int = 390
    tag_left: int = 270
    tag_top: int = 75
    tag_right: int = 450
    tag_bottom: int = 255
    led_start_x: int = 176
    led_y: int = 320
    led_gap: int = 52
    led_radius: int = 16
    sample_radius: int = 8


DEFAULT_LAYOUT = BeaconLayout()


def require_vision() -> None:
    if cv2 is None or np is None:
        raise RuntimeError(
            "OpenCV/numpy are required for beacon image demos. "
            "Install with: pip install -e '.[vision]'"
        )


def draw_virtual_beacon(msg_id: int, seq: int, layout: BeaconLayout = DEFAULT_LAYOUT):
    """Draw a virtual R1 beacon image with LED states."""

    require_vision()
    encoded = encode_led_bits(msg_id, seq)
    img = np.zeros((layout.height, layout.width, 3), dtype=np.uint8)

    # Board.
    cv2.rectangle(
        img,
        (layout.board_left, layout.board_top),
        (layout.board_right, layout.board_bottom),
        (35, 35, 35),
        -1,
    )
    cv2.rectangle(
        img,
        (layout.board_left, layout.board_top),
        (layout.board_right, layout.board_bottom),
        (230, 230, 230),
        2,
    )

    # Placeholder AprilTag region. Later replace this with a real generated AprilTag image.
    cv2.rectangle(
        img,
        (layout.tag_left, layout.tag_top),
        (layout.tag_right, layout.tag_bottom),
        (255, 255, 255),
        -1,
    )
    cv2.rectangle(
        img,
        (layout.tag_left + 18, layout.tag_top + 18),
        (layout.tag_right - 18, layout.tag_bottom - 18),
        (0, 0, 0),
        4,
    )
    cv2.putText(
        img,
        "TAG",
        (layout.tag_left + 48, layout.tag_top + 105),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.25,
        (0, 0, 0),
        3,
    )

    # LEDs.
    for i, name in enumerate(LED_NAMES):
        x = layout.led_start_x + i * layout.led_gap
        y = layout.led_y
        on = encoded.bits[name] == 1
        color = (255, 255, 255) if on else (25, 25, 25)
        cv2.circle(img, (x, y), layout.led_radius, color, -1)
        cv2.circle(img, (x, y), layout.led_radius + 2, (150, 150, 150), 1)
        cv2.putText(
            img,
            name,
            (x - 23, y + 46),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (220, 220, 220),
            1,
        )

    cv2.putText(
        img,
        f"msg_id={msg_id} seq={seq}",
        (layout.board_left + 34, layout.board_bottom - 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (255, 255, 255),
        2,
    )
    return img


def _mean_patch_gray(img, x: int, y: int, radius: int) -> float:
    require_vision()
    patch = img[y - radius : y + radius + 1, x - radius : x + radius + 1]
    if patch.size == 0:
        return 0.0
    if patch.ndim == 3:
        patch = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    return float(np.mean(patch))


def decode_virtual_beacon_image(img, layout: BeaconLayout = DEFAULT_LAYOUT) -> tuple[DecodedBeacon, float]:
    """Decode virtual beacon using known LED positions.

    Returns:
        (decoded_beacon, confidence)
    """

    require_vision()
    radius = layout.sample_radius

    # Use REF and local background to create a simple adaptive threshold.
    ref_x = layout.led_start_x
    ref_y = layout.led_y
    ref_brightness = _mean_patch_gray(img, ref_x, ref_y, radius)
    bg_brightness = _mean_patch_gray(img, ref_x, ref_y - 40, radius)
    threshold = bg_brightness + 0.45 * max(10.0, ref_brightness - bg_brightness)

    bits: dict[str, int] = {}
    margins: list[float] = []
    for i, name in enumerate(LED_NAMES):
        x = layout.led_start_x + i * layout.led_gap
        y = layout.led_y
        brightness = _mean_patch_gray(img, x, y, radius)
        bits[name] = 1 if brightness > threshold else 0
        margins.append(abs(brightness - threshold) / 255.0)

    decoded = decode_led_bits(bits)
    confidence = max(0.0, min(1.0, sum(margins) / len(margins) * 3.0))
    if not decoded.valid:
        confidence *= 0.2
    return decoded, confidence
