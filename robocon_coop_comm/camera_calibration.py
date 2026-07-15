"""Validated camera calibration input for optional AprilTag pose estimation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class CameraCalibration:
    image_width: int
    image_height: int
    camera_matrix: tuple[tuple[float, float, float], ...]
    dist_coeffs: tuple[float, ...]

    @property
    def pupil_camera_params(self) -> tuple[float, float, float, float]:
        """Return ``(fx, fy, cx, cy)`` expected by pupil-apriltags."""
        return (
            self.camera_matrix[0][0],
            self.camera_matrix[1][1],
            self.camera_matrix[0][2],
            self.camera_matrix[1][2],
        )
    @classmethod
    def from_json(cls, path: str | Path) -> "CameraCalibration":
        with Path(path).open(encoding="utf-8") as handle:
            data = json.load(handle)
        matrix = tuple(tuple(float(value) for value in row) for row in data["camera_matrix"])
        if len(matrix) != 3 or any(len(row) != 3 for row in matrix):
            raise ValueError("camera_matrix must be a 3x3 array")
        width, height = int(data["image_width"]), int(data["image_height"])
        if width <= 0 or height <= 0 or matrix[0][0] <= 0 or matrix[1][1] <= 0:
            raise ValueError("image dimensions and focal lengths must be positive")
        return cls(
            image_width=width,
            image_height=height,
            camera_matrix=matrix,
            dist_coeffs=tuple(float(value) for value in data.get("dist_coeffs", ())),
        )
