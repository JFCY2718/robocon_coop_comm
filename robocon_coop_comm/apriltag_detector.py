"""AprilTag detector abstraction.

Wraps ``pupil-apriltags`` (or fallback libraries) behind a lazy-import facade
so the module can always be imported — only ``detect()`` triggers the actual
library load.

Usage::

    detector = ApriltagDetector(families="tag36h11")
    detections = detector.detect(gray_image)  # -> list[TagDetection]
"""

from __future__ import annotations

from dataclasses import dataclass, field


class ApriltagNotAvailable(RuntimeError):
    """Raised when no AprilTag detection library can be loaded.

    Install with::

        pip install pupil-apriltags
    """


@dataclass(frozen=True)
class TagDetection:
    """One detected AprilTag."""

    tag_id: int
    family: str
    corners: list[tuple[float, float]]
    center: tuple[float, float]
    decision_margin: float = 0.0
    # Extra fields the underlying library may set.
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class ApriltagDetector:
    """Lazy-loading AprilTag detector.

    Args:
        families: tag family string, e.g. ``"tag36h11"``.
        nthreads: number of threads for detection.
        quad_decimate: decimation factor (1.0 = full resolution).
        quad_sigma: Gaussian blur sigma applied to quad detection.
        refine_edges: whether to refine edges.
        decode_sharpening: sharpening factor for decoding.
    """

    def __init__(
        self,
        families: str = "tag36h11",
        nthreads: int = 1,
        quad_decimate: float = 1.0,
        quad_sigma: float = 0.0,
        refine_edges: bool = True,
        decode_sharpening: float = 0.25,
    ) -> None:
        self._families = families
        self._nthreads = nthreads
        self._quad_decimate = quad_decimate
        self._quad_sigma = quad_sigma
        self._refine_edges = refine_edges
        self._decode_sharpening = decode_sharpening
        self._detector = None  # lazy

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    def detect(self, image) -> list[TagDetection]:
        """Run AprilTag detection on a grayscale/BGR image.

        Args:
            image: numpy array, grayscale (H,W) or BGR (H,W,3).

        Returns:
            List of TagDetection objects (may be empty).
        """
        det = self._get_detector()

        # pupil-apriltags expects grayscale uint8.
        if image.ndim == 3:
            import cv2

            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        raw = det.detect(gray)

        results: list[TagDetection] = []
        for r in raw:
            corners = [tuple(float(v) for v in pt) for pt in r.corners]
            center = (float(r.center[0]), float(r.center[1]))
            results.append(
                TagDetection(
                    tag_id=int(r.tag_id),
                    family=str(r.tag_family),
                    corners=corners,
                    center=center,
                    decision_margin=float(getattr(r, "decision_margin", 0.0)),
                )
            )
        return results

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _get_detector(self):
        if self._detector is not None:
            return self._detector

        try:
            from pupil_apriltags import Detector
        except ImportError as exc:
            raise ApriltagNotAvailable(
                "pupil-apriltags is not installed.\n"
                "Install with:  pip install pupil-apriltags"
            ) from exc

        self._detector = Detector(
            families=self._families,
            nthreads=self._nthreads,
            quad_decimate=self._quad_decimate,
            quad_sigma=self._quad_sigma,
            refine_edges=self._refine_edges,
            decode_sharpening=self._decode_sharpening,
        )
        return self._detector
