"""Physical geometry for the R1 six-LED beacon board.

All board dimensions are expressed in millimetres.  Image projection code is
kept separate so millimetres and pixels cannot be mixed accidentally.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


LED_ORDER = ("D0", "D1", "D2", "D3", "REF", "PAR")


@dataclass(frozen=True)
class BeaconGeometry:
    """Planar beacon geometry in a board-centred, X-right/Y-up frame."""

    board_width_mm: float = 280.0
    board_height_mm: float = 220.0
    tag_size_mm: float = 150.0
    tag_center_mm: tuple[float, float] = (-55.0, 0.0)
    led_centers_mm: tuple[tuple[str, float, float], ...] = (
        ("D0", 40.0, 70.0),
        ("D1", 80.0, 70.0),
        ("D2", 120.0, 70.0),
        ("D3", 40.0, 20.0),
        ("REF", 80.0, 20.0),
        ("PAR", 120.0, 20.0),
    )
    led_cap_radius_mm: float = 11.2
    roi_radius_scale: float = 0.65

    def __post_init__(self) -> None:
        if self.tag_size_mm <= 0 or self.led_cap_radius_mm <= 0:
            raise ValueError("tag_size_mm and led_cap_radius_mm must be positive")
        if not 0.0 < self.roi_radius_scale <= 1.0:
            raise ValueError("roi_radius_scale must be in (0, 1]")
        names = tuple(item[0] for item in self.led_centers_mm)
        if names != LED_ORDER:
            raise ValueError(f"LED order must be {LED_ORDER}, got {names}")

    @property
    def roi_radius_mm(self) -> float:
        """Sampling radius inside the lamp cap, in millimetres."""
        return self.led_cap_radius_mm * self.roi_radius_scale

    @property
    def led_centers_tag_mm(self) -> tuple[tuple[str, float, float], ...]:
        """LED centres relative to the AprilTag centre, in millimetres."""
        tag_x, tag_y = self.tag_center_mm
        return tuple((name, x - tag_x, y - tag_y) for name, x, y in self.led_centers_mm)

    @classmethod
    def from_json(cls, path: str | Path) -> "BeaconGeometry":
        """Load overrides from a JSON layout file.

        ``led_centers_mm`` may be a mapping keyed by LED name or a sequence of
        ``[name, x, y]`` entries.  Missing fields retain competition defaults.
        """
        with Path(path).open(encoding="utf-8") as handle:
            data = json.load(handle)

        values: dict = dict(data)
        if "tag_center_mm" in values:
            values["tag_center_mm"] = tuple(values["tag_center_mm"])
        if "led_centers_mm" in values:
            leds = values["led_centers_mm"]
            if isinstance(leds, dict):
                values["led_centers_mm"] = tuple(
                    (name, float(leds[name][0]), float(leds[name][1])) for name in LED_ORDER
                )
            else:
                values["led_centers_mm"] = tuple(
                    (str(name), float(x), float(y)) for name, x, y in leds
                )
        return cls(**values)
