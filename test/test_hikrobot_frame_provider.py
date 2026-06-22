"""Tests for HikrobotFrameProvider, ThreeLedRoiDecoder, FakeFrameProvider, and FrameLogger.

All tests run without Hikrobot SDK — only numpy + OpenCV are required.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from robocon_coop_comm.fake_frame_provider import FakeFrameProvider
from robocon_coop_comm.frame_logger import FrameLogger
from robocon_coop_comm.hikrobot_frame_provider import (
    ThreeLedRoiDecoder,
    decode_3led_from_frame,
    roi_mean,
)

# Skip entire module if OpenCV/numpy not available.
cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")


# ---------------------------------------------------------------------------
# roi_mean
# ---------------------------------------------------------------------------


class TestRoiMean:
    def test_bright_roi(self) -> None:
        img = np.full((100, 100), 200, dtype=np.uint8)
        val = roi_mean(img, 50, 50, 10)
        assert val == pytest.approx(200.0, abs=2.0)

    def test_dark_roi(self) -> None:
        img = np.full((100, 100), 10, dtype=np.uint8)
        val = roi_mean(img, 50, 50, 10)
        assert val == pytest.approx(10.0, abs=2.0)

    def test_out_of_bounds(self) -> None:
        img = np.full((100, 100), 128, dtype=np.uint8)
        val = roi_mean(img, -10, -10, 20)
        assert val >= 0.0

    def test_bgr_input(self) -> None:
        img = np.full((100, 100, 3), 150, dtype=np.uint8)
        val = roi_mean(img, 50, 50, 10)
        assert val == pytest.approx(150.0, abs=3.0)

    def test_mixed_roi(self) -> None:
        img = np.zeros((100, 100), dtype=np.uint8)
        img[40:60, 40:60] = 200
        val = roi_mean(img, 50, 50, 30)
        # Centre area is 200, but ROI includes some 0 border
        assert 40.0 < val < 120.0


# ---------------------------------------------------------------------------
# decode_3led_from_frame
# ---------------------------------------------------------------------------


class TestDecode3LedFromFrame:
    def test_all_bright(self) -> None:
        from robocon_coop_comm.beacon_types import BeaconFrame

        img = np.full((200, 200), 200, dtype=np.uint8)
        frame = BeaconFrame(image=img, source="test", frame_id=0)
        bits = decode_3led_from_frame(
            frame, [(50, 100), (100, 100), (150, 100)], threshold=120, roi_size=20
        )
        assert bits == {"D0": 1, "D1": 1, "D2": 1}

    def test_all_dark(self) -> None:
        from robocon_coop_comm.beacon_types import BeaconFrame

        img = np.full((200, 200), 10, dtype=np.uint8)
        frame = BeaconFrame(image=img, source="test", frame_id=0)
        bits = decode_3led_from_frame(
            frame, [(50, 100), (100, 100), (150, 100)], threshold=120, roi_size=20
        )
        assert bits == {"D0": 0, "D1": 0, "D2": 0}

    def test_bgr_frame(self) -> None:
        from robocon_coop_comm.beacon_types import BeaconFrame

        img = np.full((200, 200, 3), 200, dtype=np.uint8)
        frame = BeaconFrame(image=img, source="test", frame_id=0)
        bits = decode_3led_from_frame(
            frame, [(50, 100), (100, 100), (150, 100)], threshold=120, roi_size=20
        )
        assert bits == {"D0": 1, "D1": 1, "D2": 1}


# ---------------------------------------------------------------------------
# FakeFrameProvider
# ---------------------------------------------------------------------------


class TestFakeFrameProvider:
    def test_generates_frame(self) -> None:
        p = FakeFrameProvider(msg_id=4, seq=1)
        frame = p.get_frame()
        assert frame.source == "fake_camera"
        assert frame.image is not None
        assert frame.image.ndim == 2  # grayscale
        assert frame.image.shape == (480, 640)

    def test_frame_id_increments(self) -> None:
        p = FakeFrameProvider()
        f1 = p.get_frame()
        f2 = p.get_frame()
        assert f2.frame_id == f1.frame_id + 1

    def test_update_changes_led_state(self) -> None:
        p = FakeFrameProvider(msg_id=0, seq=0)

        # msg_id=0: all LEDs off
        f0 = p.get_frame()
        bits_off = decode_3led_from_frame(f0, p.roi_points, threshold=120, roi_size=24)
        assert bits_off["D0"] == 0
        assert bits_off["D1"] == 0
        assert bits_off["D2"] == 0

        # msg_id=7: all 3 LEDs on
        p.update(msg_id=7, seq=1)
        f7 = p.get_frame()
        bits_on = decode_3led_from_frame(f7, p.roi_points, threshold=120, roi_size=24)
        assert bits_on["D0"] == 1
        assert bits_on["D1"] == 1
        assert bits_on["D2"] == 1

    def test_roi_points_are_consistent(self) -> None:
        p = FakeFrameProvider(width=640, height=480, led_radius=12)
        assert len(p.roi_points) == 3
        for x, y in p.roi_points:
            assert 0 <= x < 640
            assert 0 <= y < 480

    def test_custom_size(self) -> None:
        p = FakeFrameProvider(width=320, height=240)
        frame = p.get_frame()
        assert frame.image.shape == (240, 320)


# ---------------------------------------------------------------------------
# ThreeLedRoiDecoder
# ---------------------------------------------------------------------------


class TestThreeLedRoiDecoder:
    def test_decode_msg_id_4(self) -> None:
        provider = FakeFrameProvider(msg_id=4, seq=1)
        decoder = ThreeLedRoiDecoder(threshold=120, roi_size=24)
        frame = provider.get_frame()
        result = decoder.decode(frame, provider.roi_points)

        assert result.valid is True
        assert result.msg_id == 4
        assert result.msg_name == "INSERT_ALLOWED"
        assert result.seq == 0  # first decode, seq starts at 0

    def test_decode_msg_id_2(self) -> None:
        provider = FakeFrameProvider(msg_id=2, seq=1)
        decoder = ThreeLedRoiDecoder(threshold=120, roi_size=24)
        frame = provider.get_frame()
        result = decoder.decode(frame, provider.roi_points)

        assert result.valid is True
        assert result.msg_id == 2
        assert result.msg_name == "R1_ROD_CLAMPED"

    def test_decode_msg_id_0(self) -> None:
        provider = FakeFrameProvider(msg_id=0, seq=0)
        decoder = ThreeLedRoiDecoder(threshold=120, roi_size=24)
        frame = provider.get_frame()
        result = decoder.decode(frame, provider.roi_points)

        assert result.valid is True
        assert result.msg_id == 0
        assert result.msg_name == "IDLE"

    def test_decode_msg_id_7(self) -> None:
        provider = FakeFrameProvider(msg_id=7, seq=1)
        decoder = ThreeLedRoiDecoder(threshold=120, roi_size=24)
        frame = provider.get_frame()
        result = decoder.decode(frame, provider.roi_points)

        assert result.valid is True
        assert result.msg_id == 7
        assert result.msg_name == "R1_IN_MF"

    def test_seq_toggles_on_msg_id_change(self) -> None:
        provider = FakeFrameProvider(msg_id=4, seq=0)
        decoder = ThreeLedRoiDecoder(threshold=120, roi_size=24)

        r1 = decoder.decode(provider.get_frame(), provider.roi_points)
        assert r1.seq == 0

        # Same msg_id → seq stays same
        r2 = decoder.decode(provider.get_frame(), provider.roi_points)
        assert r2.seq == 0

        # Change msg_id → seq toggles
        provider.update(msg_id=5, seq=1)
        r3 = decoder.decode(provider.get_frame(), provider.roi_points)
        assert r3.seq == 1

        # Change back → seq toggles again
        provider.update(msg_id=4, seq=0)
        r4 = decoder.decode(provider.get_frame(), provider.roi_points)
        assert r4.seq == 0

    def test_reset_seq(self) -> None:
        provider = FakeFrameProvider(msg_id=4, seq=0)
        decoder = ThreeLedRoiDecoder(threshold=120, roi_size=24)

        decoder.decode(provider.get_frame(), provider.roi_points)
        provider.update(msg_id=5, seq=1)
        decoder.decode(provider.get_frame(), provider.roi_points)
        assert decoder._seq == 1

        decoder.reset_seq()
        assert decoder._seq == 0
        assert decoder._last_msg_id is None

    def test_raw_bits_present(self) -> None:
        provider = FakeFrameProvider(msg_id=4, seq=1)
        decoder = ThreeLedRoiDecoder(threshold=120, roi_size=24)
        frame = provider.get_frame()
        result = decoder.decode(frame, provider.roi_points)

        assert result.raw_bits is not None
        assert "REF" in result.raw_bits
        assert "D0" in result.raw_bits
        assert "D1" in result.raw_bits
        assert "D2" in result.raw_bits
        assert "SEQ" in result.raw_bits
        assert "PAR" in result.raw_bits

    def test_non_3led_msg_id_clamped(self) -> None:
        """msg_id > 7 requires D3 which is always 0 in 3-LED mode."""
        provider = FakeFrameProvider(msg_id=5, seq=0)  # 5 = 0b101 (D0=1, D1=0, D2=1)
        decoder = ThreeLedRoiDecoder(threshold=120, roi_size=24)
        frame = provider.get_frame()
        result = decoder.decode(frame, provider.roi_points)
        assert result.msg_id == 5
        assert result.valid is True


# ---------------------------------------------------------------------------
# FrameLogger
# ---------------------------------------------------------------------------


class TestFrameLogger:
    def test_csv_write_and_read(self) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".csv", mode="w", delete=False
        ) as tmp:
            tmp_path = tmp.name

        try:
            logger = FrameLogger(tmp_path, format="csv")
            logger.log(
                timestamp=1000000.0,
                msg_id=4,
                seq=1,
                valid=True,
                confidence=0.95,
                latency_ms=12.3,
            )
            logger.log(
                timestamp=1000000.1,
                msg_id=5,
                seq=0,
                valid=False,
                confidence=0.30,
                latency_ms=15.7,
            )
            logger.close()

            content = Path(tmp_path).read_text()
            lines = content.strip().split("\n")
            assert len(lines) == 3  # header + 2 records
            assert "timestamp" in lines[0]
            assert "4" in lines[1]
            assert "5" in lines[2]
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_jsonl_write_and_read(self) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".jsonl", mode="w", delete=False
        ) as tmp:
            tmp_path = tmp.name

        try:
            logger = FrameLogger(tmp_path, format="jsonl")
            logger.log(
                timestamp=1000000.0,
                msg_id=4,
                seq=1,
                valid=True,
                confidence=0.95,
                latency_ms=12.3,
            )
            logger.log(
                timestamp=1000000.1,
                msg_id=5,
                seq=0,
                valid=False,
                confidence=0.30,
                latency_ms=15.7,
                extra={"brightness_D0": 200, "brightness_D1": 15},
            )
            logger.close()

            content = Path(tmp_path).read_text()
            lines = content.strip().split("\n")
            assert len(lines) == 2

            rec0 = json.loads(lines[0])
            assert rec0["msg_id"] == 4
            assert rec0["valid"] is True

            rec1 = json.loads(lines[1])
            assert rec1["msg_id"] == 5
            assert rec1["brightness_D0"] == 200
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_csv_extra_columns(self) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".csv", mode="w", delete=False
        ) as tmp:
            tmp_path = tmp.name

        try:
            logger = FrameLogger(tmp_path, format="csv", extra_columns=["extra_col"])
            logger.log(
                msg_id=1, seq=0, valid=True, confidence=1.0, latency_ms=5.0,
                extra={"extra_col": "hello"},
            )
            logger.close()

            content = Path(tmp_path).read_text()
            assert "hello" in content
            # header must include extra_col
            assert "extra_col" in content.split("\n")[0]
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_csv_extra_columns_header_row_match(self) -> None:
        """Header row and data row MUST have the same column count."""
        with tempfile.NamedTemporaryFile(
            suffix=".csv", mode="w", delete=False
        ) as tmp:
            tmp_path = tmp.name

        try:
            sixled_cols = [
                "pattern", "bitmask",
                "D0", "D1", "D2", "REF", "SEQ", "PAR",
                "D0_mean", "D1_mean", "D2_mean", "REF_mean", "SEQ_mean", "PAR_mean",
            ]
            logger = FrameLogger(tmp_path, format="csv", extra_columns=sixled_cols)
            logger.log(
                msg_id=0, seq=0, valid=True, confidence=0.5, latency_ms=10.0,
                extra={
                    "pattern": "111111", "bitmask": "0x3F",
                    "D0": 1, "D1": 1, "D2": 1, "REF": 1, "SEQ": 1, "PAR": 1,
                    "D0_mean": 50.0, "D1_mean": 50.0, "D2_mean": 50.0,
                    "REF_mean": 50.0, "SEQ_mean": 50.0, "PAR_mean": 50.0,
                },
            )
            logger.close()

            content = Path(tmp_path).read_text()
            lines = content.strip().split("\n")
            assert len(lines) == 2  # header + 1 record

            header_cols = lines[0].split(",")
            data_cols = lines[1].split(",")
            assert len(header_cols) == len(data_cols), (
                f"header has {len(header_cols)} cols, data has {len(data_cols)} cols"
            )
            # Verify no row[None] would be produced by csv.DictReader
            import csv, io
            reader = csv.DictReader(io.StringIO(content))
            row = next(reader)
            assert None not in row, f"row[None] detected: {row.get(None)}"
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_invalid_format(self) -> None:
        with pytest.raises(ValueError, match="Unsupported format"):
            FrameLogger("/tmp/test.log", format="xml")

    def test_context_manager(self) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".csv", mode="w", delete=False
        ) as tmp:
            tmp_path = tmp.name

        try:
            with FrameLogger(tmp_path, format="csv") as logger:
                logger.log(
                    msg_id=1, seq=0, valid=True, confidence=1.0, latency_ms=5.0,
                )
            # File should be flushed and closed after context exit.
            content = Path(tmp_path).read_text()
            assert len(content.strip().split("\n")) == 2
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_default_timestamp(self) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".jsonl", mode="w", delete=False
        ) as tmp:
            tmp_path = tmp.name

        try:
            logger = FrameLogger(tmp_path, format="jsonl")
            logger.log(
                msg_id=0, seq=0, valid=True, confidence=1.0, latency_ms=1.0,
            )
            logger.close()

            rec = json.loads(Path(tmp_path).read_text().strip())
            assert rec["timestamp"] > 0  # auto-filled
        finally:
            Path(tmp_path).unlink(missing_ok=True)
