"""Frame-level debug logger: CSV or JSONL output.

Writes one record per decoded frame, recording timestamp, msg_id, seq,
confidence, valid, and latency_ms.  Useful for real-camera debugging and
bit-error-rate analysis.
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path


class FrameLogger:
    """Log decoded beacon frames to CSV or JSONL.

    Usage::

        logger = FrameLogger("/tmp/beacon_log.csv", format="csv")
        logger.log(
            timestamp=time.time(),
            msg_id=4, seq=1,
            valid=True, confidence=0.95,
            latency_ms=12.3,
            extra={"brightness_D0": 200, "brightness_D1": 15},
        )
        logger.close()
    """

    CSV_HEADER = [
        "timestamp",
        "msg_id",
        "seq",
        "valid",
        "confidence",
        "latency_ms",
    ]

    def __init__(self, path: str | Path, format: str = "csv") -> None:
        path = Path(path)
        self._format = format.lower()
        if self._format not in ("csv", "jsonl"):
            raise ValueError(f"Unsupported format: {format!r}; use 'csv' or 'jsonl'")
        self._path = path
        self._fh = open(path, "w", newline="") if self._format == "csv" else open(path, "w")
        self._csv_writer = None
        if self._format == "csv":
            self._csv_writer = csv.writer(self._fh)
            self._csv_writer.writerow(self.CSV_HEADER)

    def log(
        self,
        *,
        timestamp: float | None = None,
        msg_id: int,
        seq: int,
        valid: bool,
        confidence: float,
        latency_ms: float,
        extra: dict | None = None,
    ) -> None:
        """Write one frame record.

        Args:
            timestamp: epoch seconds; uses ``time.time()`` if None.
            msg_id: decoded message id.
            seq: decoded sequence bit.
            valid: whether the decode passed validation.
            confidence: 0.0 – 1.0.
            latency_ms: frame-grab → decode latency in milliseconds.
            extra: additional key-value pairs to include in the record.
        """
        if timestamp is None:
            timestamp = time.time()
        if self._format == "csv":
            row = [f"{timestamp:.6f}", msg_id, seq, int(valid), f"{confidence:.4f}", f"{latency_ms:.3f}"]
            if extra:
                for k, v in extra.items():
                    row.append(str(v))
            self._csv_writer.writerow(row)  # type: ignore[union-attr]
        else:
            record = {
                "timestamp": timestamp,
                "msg_id": msg_id,
                "seq": seq,
                "valid": valid,
                "confidence": confidence,
                "latency_ms": latency_ms,
            }
            if extra:
                record.update(extra)
            self._fh.write(json.dumps(record) + "\n")
        self._fh.flush()

    def close(self) -> None:
        """Flush and close the output file."""
        if not self._fh.closed:
            self._fh.close()

    def __enter__(self) -> "FrameLogger":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
