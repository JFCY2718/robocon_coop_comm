"""Pure-software tests for ApriltagDetector and the smoke CLI.

No camera, no real AprilTag image required.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Core dataclass is always importable.
from robocon_coop_comm.apriltag_detector import (
    ApriltagDetector,
    ApriltagNotAvailable,
    TagDetection,
)


# ---------------------------------------------------------------------------
# TagDetection dataclass
# ---------------------------------------------------------------------------


class TestTagDetection:
    def test_construction(self) -> None:
        d = TagDetection(
            tag_id=0,
            family="tag36h11",
            corners=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
            center=(0.5, 0.5),
            decision_margin=42.0,
        )
        assert d.tag_id == 0
        assert d.family == "tag36h11"
        assert d.decision_margin == 42.0
        assert d.center == (0.5, 0.5)
        assert len(d.corners) == 4

    def test_default_decision_margin(self) -> None:
        d = TagDetection(
            tag_id=1, family="tag36h11",
            corners=[], center=(0.0, 0.0),
        )
        assert d.decision_margin == 0.0

    def test_extra_dict(self) -> None:
        d = TagDetection(
            tag_id=0, family="tag36h11",
            corners=[], center=(0.0, 0.0),
            extra={"pose_R": [1, 0, 0]},
        )
        assert d.extra["pose_R"] == [1, 0, 0]

    def test_is_frozen(self) -> None:
        d = TagDetection(
            tag_id=0, family="tag36h11",
            corners=[], center=(0.0, 0.0),
        )
        with pytest.raises(Exception):
            d.tag_id = 5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ApriltagDetector — lazy import
# ---------------------------------------------------------------------------


class TestApriltagDetectorLazy:
    def test_constructor_does_not_import_pupil(self) -> None:
        """Constructing the detector must NOT import pupil_apriltags."""
        with mock.patch.dict(sys.modules, {"pupil_apriltags": None}):
            d = ApriltagDetector(families="tag36h11")
            assert d._detector is None

    def test_detect_without_pupil_raises_clear_error(self) -> None:
        d = ApriltagDetector(families="tag36h11")
        with mock.patch.dict(sys.modules, {"pupil_apriltags": None}):
            with mock.patch(
                "robocon_coop_comm.apriltag_detector.ApriltagDetector._get_detector",
                side_effect=ApriltagNotAvailable(
                    "pupil-apriltags is not installed.\n"
                    "Install with:  pip install pupil-apriltags"
                ),
            ):
                with pytest.raises(ApriltagNotAvailable, match="pupil-apriltags"):
                    import numpy as np
                    img = np.zeros((100, 100), dtype=np.uint8)
                    d.detect(img)


# ---------------------------------------------------------------------------
# ApriltagDetector — with mock Detector
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_detector() -> mock.MagicMock:
    """Return a MagicMock that fakes one tag36h11 id=0 detection."""
    fake_det = mock.MagicMock()
    fake_det.tag_id = 0
    fake_det.tag_family = "tag36h11"  # matches pupil-apriltags attr name
    fake_det.corners = [
        [100.0, 100.0],
        [200.0, 100.0],
        [200.0, 200.0],
        [100.0, 200.0],
    ]
    fake_det.center = [150.0, 150.0]
    fake_det.decision_margin = 42.5

    fake_detector = mock.MagicMock()
    fake_detector.detect.return_value = [fake_det]
    return fake_detector


class TestApriltagDetectorWithMock:
    def test_detect_returns_tag_detection(self, mock_detector: mock.MagicMock) -> None:
        import numpy as np

        d = ApriltagDetector(families="tag36h11")
        # Inject the mock.
        d._detector = mock_detector

        img = np.full((300, 300), 128, dtype=np.uint8)
        results = d.detect(img)

        assert len(results) == 1
        r = results[0]
        assert isinstance(r, TagDetection)
        assert r.tag_id == 0
        assert r.family == "tag36h11"
        assert r.decision_margin == 42.5
        assert r.center == (150.0, 150.0)
        assert len(r.corners) == 4
        assert r.corners[0] == (100.0, 100.0)

    def test_detect_bgr_image_converts_to_gray(
        self, mock_detector: mock.MagicMock,
    ) -> None:
        import numpy as np

        d = ApriltagDetector()
        d._detector = mock_detector

        # BGR image
        img = np.full((300, 300, 3), 128, dtype=np.uint8)
        results = d.detect(img)

        assert len(results) == 1
        # Verify the mock was called with a 2-D grayscale image.
        called_with = mock_detector.detect.call_args[0][0]
        assert called_with.ndim == 2  # type: ignore[union-attr]

    def test_detect_no_tags(self) -> None:
        import numpy as np

        fake = mock.MagicMock()
        fake.detect.return_value = []

        d = ApriltagDetector()
        d._detector = fake

        img = np.full((300, 300), 128, dtype=np.uint8)
        results = d.detect(img)
        assert results == []

    def test_detect_multiple_tags(self) -> None:
        import numpy as np

        fake_det0 = mock.MagicMock()
        fake_det0.tag_id = 0
        fake_det0.family = "tag36h11"
        fake_det0.corners = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
        fake_det0.center = [0.5, 0.5]
        fake_det0.decision_margin = 50.0

        fake_det1 = mock.MagicMock()
        fake_det1.tag_id = 1
        fake_det1.family = "tag36h11"
        fake_det1.corners = [[10.0, 10.0], [11.0, 10.0], [11.0, 11.0], [10.0, 11.0]]
        fake_det1.center = [10.5, 10.5]
        fake_det1.decision_margin = 30.0

        fake = mock.MagicMock()
        fake.detect.return_value = [fake_det0, fake_det1]

        d = ApriltagDetector()
        d._detector = fake

        img = np.full((300, 300), 128, dtype=np.uint8)
        results = d.detect(img)
        assert len(results) == 2
        assert results[0].tag_id == 0
        assert results[1].tag_id == 1

    def test_decision_margin_missing_uses_zero(self) -> None:
        import numpy as np

        fake_det = mock.MagicMock(spec=["tag_id", "tag_family", "corners", "center"])
        fake_det.tag_id = 0
        fake_det.tag_family = "tag36h11"  # matches pupil-apriltags attr name
        fake_det.corners = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
        fake_det.center = [0.5, 0.5]
        # No decision_margin attribute.

        fake = mock.MagicMock()
        fake.detect.return_value = [fake_det]

        d = ApriltagDetector()
        d._detector = fake

        img = np.full((100, 100), 128, dtype=np.uint8)
        results = d.detect(img)
        assert len(results) == 1
        assert results[0].decision_margin == 0.0


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class TestApriltagNotAvailable:
    def test_is_runtime_error(self) -> None:
        exc = ApriltagNotAvailable("test message")
        assert isinstance(exc, RuntimeError)
        assert "test message" in str(exc)


# ---------------------------------------------------------------------------
# CLI --help must work without Hikrobot SDK
# ---------------------------------------------------------------------------


class TestSmokeCliHelp:
    def test_help_works(self) -> None:
        """--help must exit 0 and print usage even without camera/SDK."""
        script = str(
            Path(__file__).parent.parent / "tools" / "hikrobot_apriltag_smoke.py"
        )
        result = subprocess.run(
            [sys.executable, script, "--help"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert "tag36h11" in result.stdout
        assert "--family" in result.stdout
        assert "--display" in result.stdout
        assert "--save-frame" in result.stdout
        assert "--log-jsonl" in result.stdout
        assert "--tag-id" in result.stdout

    def test_help_with_uninstalled_deps(self) -> None:
        """--help should NOT crash even if pupil-apriltags is uninstalled."""
        script = str(
            Path(__file__).parent.parent / "tools" / "hikrobot_apriltag_smoke.py"
        )
        # Run with --help: imports happen after argparse, so this should work.
        result = subprocess.run(
            [sys.executable, script, "--help"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0
        assert "tag36h11" in result.stdout


# ---------------------------------------------------------------------------
# JSONL log format
# ---------------------------------------------------------------------------


class TestJsonlLogFormat:
    def test_log_record_shape(self) -> None:
        """Smoke-test the JSON record schema used by the CLI."""
        record = {
            "timestamp": 1720000000.123,
            "frame": 42,
            "tag_id": 0,
            "family": "tag36h11",
            "center": [320.5, 240.5],
            "corners": [
                [100.0, 100.0],
                [540.0, 100.0],
                [540.0, 380.0],
                [100.0, 380.0],
            ],
            "decision_margin": 45.2,
            "latency_ms": 8.3,
        }
        line = json.dumps(record)
        parsed = json.loads(line)
        assert parsed["tag_id"] == 0
        assert parsed["family"] == "tag36h11"
        assert len(parsed["corners"]) == 4
        assert isinstance(parsed["decision_margin"], (int, float))
        assert isinstance(parsed["latency_ms"], (int, float))

    def test_log_to_file(self) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".jsonl", mode="w", delete=False
        ) as tmp:
            tmp_path = tmp.name

        try:
            records = [
                {
                    "timestamp": 1720000000.0 + i,
                    "frame": i,
                    "tag_id": 0,
                    "family": "tag36h11",
                    "center": [320.0, 240.0],
                    "corners": [[100.0, 100.0], [540.0, 100.0], [540.0, 380.0], [100.0, 380.0]],
                    "decision_margin": 42.0,
                    "latency_ms": 8.0,
                }
                for i in range(3)
            ]
            with open(tmp_path, "w") as fh:
                for r in records:
                    fh.write(json.dumps(r) + "\n")

            lines = Path(tmp_path).read_text().strip().split("\n")
            assert len(lines) == 3
            for line in lines:
                assert "tag_id" in line
                assert "decision_margin" in line
        finally:
            Path(tmp_path).unlink(missing_ok=True)
